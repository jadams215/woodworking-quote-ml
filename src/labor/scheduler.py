"""Greedy scheduler for labor assignments and capacity planning."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from .schema import (
    ComplexityLevel,
    Employee,
    Job,
    QualityRisk,
    SchedulerConfig,
    SkillName,
    SKILL_FIELD_MAP,
    TaskBlock,
)


WEEKDAY_MAP = {
    0: "mon",
    1: "tue",
    2: "wed",
    3: "thu",
    4: "fri",
    5: "sat",
    6: "sun",
}


@dataclass
class ScheduledTask:
    task: TaskBlock
    employee_id: str
    start_date: date
    end_date: date
    adjusted_hours: float
    training_required: bool
    due_date_met: bool


def adjust_duration(
    base_hours: float,
    complexity_level: ComplexityLevel,
    speed_multiplier: float,
    rework_rate_pct: float,
    quality_risk: QualityRisk,
    config: SchedulerConfig,
    training_required: bool,
) -> float:
    """Apply complexity, speed, rework, and training factors."""
    complexity_factor = config.resolved_complexity_factors()[complexity_level]
    risk_factor = config.resolved_risk_factors()[quality_risk]
    training_factor = config.training_penalty if training_required else 1.0
    adjusted = base_hours * speed_multiplier * complexity_factor * training_factor
    rework_buffer = base_hours * (rework_rate_pct / 100.0) * risk_factor
    return max(adjusted + rework_buffer, 0.1)


def is_employee_eligible(
    employee: Employee,
    required_skill: SkillName,
    config: SchedulerConfig,
) -> Tuple[bool, bool, str]:
    """Return (eligible, training_required, reason)."""
    skill_field = SKILL_FIELD_MAP[required_skill]
    rating = getattr(employee.skills, skill_field)
    if rating.proficiency_score >= config.proficiency_threshold:
        return True, False, "qualified"
    if config.allow_training:
        return True, True, "training_required"
    return False, False, "below_threshold"


def _daily_capacity(employee: Employee) -> float:
    days = employee.availability.days_available
    return employee.availability.hours_per_week / max(len(days), 1)


def _is_day_available(employee: Employee, day: date) -> bool:
    return WEEKDAY_MAP[day.weekday()] in employee.availability.days_available


def _allocate_hours(
    employee: Employee,
    calendar: Dict[date, float],
    start_date: date,
    hours: float,
) -> Tuple[date, date, Dict[date, float]]:
    """Allocate hours sequentially and return (start, end, allocations)."""
    allocations: Dict[date, float] = {}
    remaining = hours
    current = start_date
    daily_capacity = _daily_capacity(employee)

    while remaining > 0:
        if _is_day_available(employee, current):
            used = calendar.get(current, 0.0)
            available = max(daily_capacity - used, 0.0)
            if available > 0:
                chunk = min(available, remaining)
                allocations[current] = allocations.get(current, 0.0) + chunk
                remaining -= chunk
        current += timedelta(days=1)

    end_date = max(allocations.keys())
    return min(allocations.keys()), end_date, allocations


def schedule_jobs(
    employees: List[Employee],
    jobs: List[Job],
    config: Optional[SchedulerConfig] = None,
) -> Dict[str, Dict]:
    """Generate a greedy schedule with risk flags and assignment metadata."""
    config = config or SchedulerConfig()

    employee_map = {emp.employee_id: emp for emp in employees}
    calendars: Dict[str, Dict[date, float]] = {emp.employee_id: {} for emp in employees}
    last_skill: Dict[str, Optional[SkillName]] = {emp.employee_id: None for emp in employees}

    schedule: Dict[str, Dict] = {"jobs": {}, "employees": {}, "risk_flags": []}
    for emp in employees:
        schedule["employees"][emp.employee_id] = {
            "employee_name": emp.name,
            "assignments": [],
        }

    all_tasks: List[TaskBlock] = []
    for job in jobs:
        schedule["jobs"][job.job_id] = {
            "job_name": job.job_name,
            "customer": job.customer,
            "tasks": [],
        }
        all_tasks.extend(job.tasks)

    tasks_by_id = {task.task_id: task for task in all_tasks}
    unscheduled = set(tasks_by_id.keys())
    completed_tasks: Dict[str, date] = {}

    def ready_tasks() -> List[TaskBlock]:
        ready = []
        for task_id in list(unscheduled):
            task = tasks_by_id[task_id]
            if all(dep in completed_tasks for dep in task.precedence):
                ready.append(task)
        ready.sort(key=lambda t: (t.earliest_start_date, t.due_date))
        return ready

    while unscheduled:
        ready = ready_tasks()
        if not ready:
            schedule["risk_flags"].append(
                {"type": "dependency_cycle", "message": "Unresolved task dependencies"}
            )
            break

        task = ready[0]
        unscheduled.remove(task.task_id)

        earliest = task.earliest_start_date
        if task.precedence:
            dep_end = max(completed_tasks[dep] for dep in task.precedence)
            earliest = max(earliest, dep_end + timedelta(days=1))

        best_option = None
        for emp in employees:
            eligible, training_required, reason = is_employee_eligible(emp, task.required_skill, config)
            if not eligible:
                continue

            skill_field = SKILL_FIELD_MAP[task.required_skill]
            rating = getattr(emp.skills, skill_field)

            adjusted_hours = adjust_duration(
                task.base_hours,
                task.complexity_level,
                rating.speed_multiplier,
                emp.reliability.rework_rate_pct,
                rating.quality_risk,
                config,
                training_required,
            )

            start, end, allocations = _allocate_hours(
                emp, calendars[emp.employee_id], earliest, adjusted_hours
            )

            due_ok = end <= task.due_date
            cost = adjusted_hours * emp.hourly_rate
            context_penalty = 0 if last_skill[emp.employee_id] == task.required_skill else 1

            score = (0 if due_ok else 1, end, cost, context_penalty)
            option = {
                "employee": emp,
                "start": start,
                "end": end,
                "allocations": allocations,
                "adjusted_hours": adjusted_hours,
                "training_required": training_required,
                "due_ok": due_ok,
                "score": score,
                "reason": reason,
            }

            if best_option is None or option["score"] < best_option["score"]:
                best_option = option

        if not best_option:
            schedule["risk_flags"].append(
                {
                    "type": "unassigned_task",
                    "task_id": task.task_id,
                    "job_id": task.job_id,
                    "reason": "no_qualified_labor",
                }
            )
            continue

        emp = best_option["employee"]
        for day, hours in best_option["allocations"].items():
            calendars[emp.employee_id][day] = calendars[emp.employee_id].get(day, 0.0) + hours

        last_skill[emp.employee_id] = task.required_skill
        completed_tasks[task.task_id] = best_option["end"]

        schedule["jobs"][task.job_id]["tasks"].append(
            {
                "task_id": task.task_id,
                "name": task.name,
                "employee_id": emp.employee_id,
                "start_date": best_option["start"].isoformat(),
                "end_date": best_option["end"].isoformat(),
                "adjusted_hours": round(best_option["adjusted_hours"], 2),
                "training_required": best_option["training_required"],
                "due_date_met": best_option["due_ok"],
            }
        )

        for day, hours in best_option["allocations"].items():
            schedule["employees"][emp.employee_id]["assignments"].append(
                {
                    "date": day.isoformat(),
                    "task_id": task.task_id,
                    "job_id": task.job_id,
                    "hours": round(hours, 2),
                    "skill": task.required_skill.value,
                }
            )

        if not best_option["due_ok"]:
            schedule["risk_flags"].append(
                {
                    "type": "late_task",
                    "task_id": task.task_id,
                    "job_id": task.job_id,
                    "due_date": task.due_date.isoformat(),
                    "scheduled_end": best_option["end"].isoformat(),
                }
            )

        if best_option["training_required"]:
            schedule["risk_flags"].append(
                {
                    "type": "training_pairing",
                    "task_id": task.task_id,
                    "job_id": task.job_id,
                    "employee_id": emp.employee_id,
                }
            )

    return schedule

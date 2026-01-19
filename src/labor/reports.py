"""Reporting helpers for labor schedules, gaps, cost, and insights."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Dict, List, Tuple

from .schema import Employee, Job, SchedulerConfig, SkillName, SKILL_FIELD_MAP


def build_schedule_report(schedule: Dict[str, Dict]) -> Dict[str, Dict]:
    """Return schedule data ready to write to schedule.json."""
    return schedule


def _horizon_window(jobs: List[Job]) -> Tuple[date, date]:
    min_date = min(task.earliest_start_date for job in jobs for task in job.tasks)
    max_date = max(task.due_date for job in jobs for task in job.tasks)
    return min_date, max_date


def build_gaps_report(
    employees: List[Employee],
    jobs: List[Job],
    schedule: Dict[str, Dict],
    config: SchedulerConfig | None = None,
) -> Dict[str, Dict]:
    """Summarize bottlenecks and unassigned tasks."""
    config = config or SchedulerConfig()

    required_hours = defaultdict(float)
    for job in jobs:
        for task in job.tasks:
            required_hours[task.required_skill] += task.base_hours

    horizon_start, horizon_end = _horizon_window(jobs)
    weeks = max((horizon_end - horizon_start).days / 7.0, 1.0)

    capacity_hours = defaultdict(float)
    for emp in employees:
        for skill_name in SkillName:
            skill_field = SKILL_FIELD_MAP[skill_name]
            rating = getattr(emp.skills, skill_field)
            if rating.proficiency_score >= config.proficiency_threshold:
                capacity_hours[skill_name] += emp.availability.hours_per_week * weeks

    bottlenecks = []
    for skill_name, hours in required_hours.items():
        capacity = capacity_hours.get(skill_name, 0.0)
        if hours > capacity:
            bottlenecks.append(
                {
                    "skill": skill_name.value,
                    "required_hours": round(hours, 2),
                    "capacity_hours": round(capacity, 2),
                    "shortfall_hours": round(hours - capacity, 2),
                }
            )

    unassigned = [
        flag
        for flag in schedule.get("risk_flags", [])
        if flag.get("type") == "unassigned_task"
    ]

    late_tasks = [
        flag
        for flag in schedule.get("risk_flags", [])
        if flag.get("type") == "late_task"
    ]

    return {
        "bottlenecks": bottlenecks,
        "unassigned_tasks": unassigned,
        "late_tasks": late_tasks,
        "notes": [
            f"horizon_start={horizon_start.isoformat()}",
            f"horizon_end={horizon_end.isoformat()}",
        ],
    }


def build_cost_report(
    employees: List[Employee],
    schedule: Dict[str, Dict],
) -> Dict[str, Dict]:
    """Aggregate labor cost by job, role, and employee."""
    employee_rate = {emp.employee_id: emp.hourly_rate for emp in employees}
    employee_role = {emp.employee_id: emp.role_title for emp in employees}

    job_costs = defaultdict(float)
    employee_costs = defaultdict(float)
    role_costs = defaultdict(float)

    for emp_id, data in schedule.get("employees", {}).items():
        for assignment in data.get("assignments", []):
            hours = float(assignment["hours"])
            cost = hours * employee_rate.get(emp_id, 0.0)
            job_costs[assignment["job_id"]] += cost
            employee_costs[emp_id] += cost
            role_costs[employee_role.get(emp_id, "unknown")] += cost

    return {
        "labor_costs_by_job": {job: round(cost, 2) for job, cost in job_costs.items()},
        "labor_costs_by_employee": {
            emp: round(cost, 2) for emp, cost in employee_costs.items()
        },
        "labor_costs_by_role": {
            role: round(cost, 2) for role, cost in role_costs.items()
        },
        "outsourcing_triggers": [
            flag
            for flag in schedule.get("risk_flags", [])
            if flag.get("type") in {"unassigned_task", "late_task"}
        ],
    }


def build_labor_insights(
    gaps_report: Dict[str, Dict],
    cost_report: Dict[str, Dict],
    schedule: Dict[str, Dict],
) -> List[str]:
    """Generate concise insights for user-facing summaries."""
    insights: List[str] = []

    if gaps_report.get("bottlenecks"):
        top = gaps_report["bottlenecks"][0]
        insights.append(
            f"Bottleneck: {top['skill']} short by {top['shortfall_hours']} hours."
        )

    late_tasks = gaps_report.get("late_tasks", [])
    if late_tasks:
        task = late_tasks[0]
        insights.append(
            f"Delay driver: {task['task_id']} ends {task['scheduled_end']} after {task['due_date']}."
        )

    unassigned = gaps_report.get("unassigned_tasks", [])
    if unassigned:
        task = unassigned[0]
        insights.append(
            f"High risk: {task['task_id']} has no qualified labor assigned."
        )

    if cost_report.get("labor_costs_by_employee"):
        lowest = min(cost_report["labor_costs_by_employee"].items(), key=lambda x: x[1])
        insights.append(
            f"Lowest cost contributor: {lowest[0]} at ${lowest[1]:.2f} in assigned labor."
        )

    if not insights:
        insights.append("Schedule is balanced with current staffing assumptions.")

    return insights

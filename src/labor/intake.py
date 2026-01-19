"""Intake flow helpers for employees and pipeline jobs."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from .schema import Employee, Job, SkillName, TaskBlock, ComplexityLevel


EMPLOYEE_INTAKE_QUESTIONS: List[Dict[str, Any]] = [
    {
        "section": "identity_logistics",
        "title": "Identity and logistics",
        "questions": [
            {"id": "name", "prompt": "Name", "type": "text"},
            {"id": "role_title", "prompt": "Role title", "type": "text"},
            {
                "id": "employment_type",
                "prompt": "Employment type (full_time/part_time/contract)",
                "type": "select",
                "options": ["full_time", "part_time", "contract"],
            },
            {"id": "hourly_rate", "prompt": "Hourly loaded rate", "type": "number"},
            {
                "id": "availability",
                "prompt": "Typical weekly availability (hours, days)",
                "type": "object",
            },
            {"id": "constraints", "prompt": "Constraints", "type": "list"},
        ],
    },
    {
        "section": "skills_strengths",
        "title": "Skills and strengths",
        "prompt": "Rate your confidence and speed for each task. Add notes if needed.",
        "questions": [
            {"id": "rough_cutting_milling", "label": "Rough cutting / milling"},
            {"id": "joinery", "label": "Joinery"},
            {"id": "assembly_glueups", "label": "Assembly and glue-ups"},
            {"id": "sanding_prep", "label": "Sanding and prep"},
            {"id": "finishing", "label": "Finishing"},
            {"id": "cnc_setup_operation", "label": "CNC setup and operation"},
            {"id": "cad_cam", "label": "CAD/CAM"},
            {"id": "install_on_site", "label": "Install/on-site work"},
            {"id": "packing_crating", "label": "Packing/crating"},
            {"id": "troubleshooting_rework", "label": "Troubleshooting/rework"},
        ],
        "skill_fields": ["proficiency_score", "speed_multiplier", "quality_risk", "experience_examples"],
    },
    {
        "section": "experience_history",
        "title": "Experience history",
        "questions": [
            {"id": "top_job_types", "prompt": "Top 3 job types done most"},
            {"id": "max_complexity", "prompt": "Max complexity (low/med/high)"},
            {"id": "max_complexity_examples", "prompt": "Examples"},
            {"id": "materials_familiarity", "prompt": "Materials familiarity"},
            {"id": "finish_familiarity", "prompt": "Finish familiarity"},
            {
                "id": "cnc_experience",
                "prompt": "CNC experience (years, typical ops, comfort level)",
            },
        ],
    },
    {
        "section": "weaknesses_preferences",
        "title": "Weaknesses and preferences",
        "questions": [
            {"id": "tasks_avoid", "prompt": "Tasks they avoid or are slow at"},
            {"id": "tasks_best", "prompt": "Tasks they do best"},
            {"id": "error_modes", "prompt": "Known error modes"},
            {"id": "training_needs", "prompt": "Training needs"},
        ],
    },
    {
        "section": "reliability_overhead",
        "title": "Reliability and overhead factors",
        "questions": [
            {"id": "rework_rate_pct", "prompt": "Rework rate estimate (0-10%)"},
            {"id": "punctuality_rating", "prompt": "Punctuality/reliability rating (1-5)"},
            {"id": "supervision_need", "prompt": "Need supervision? (none/light/medium/heavy)"},
        ],
    },
]


def get_employee_intake_questions() -> List[Dict[str, Any]]:
    """Return the canonical wizard-style intake questions."""
    return EMPLOYEE_INTAKE_QUESTIONS


def normalize_employee_intake(payload: Dict[str, Any]) -> Employee:
    """Normalize and validate an employee intake payload."""
    return Employee.model_validate(payload)


def save_employees(path: str | Path, employees: List[Employee]) -> None:
    """Persist employees to JSON."""
    path = Path(path)
    data = [employee.model_dump(mode="json") for employee in employees]
    path.write_text(json.dumps(data, indent=2))


def load_employees(path: str | Path) -> List[Employee]:
    """Load employees from JSON."""
    path = Path(path)
    data = json.loads(path.read_text())
    return [Employee.model_validate(item) for item in data]


TASK_SKILL_MAP: Dict[str, SkillName] = {
    "material_prep_hours": SkillName.rough_cutting_milling,
    "cutting_hours": SkillName.rough_cutting_milling,
    "cnc_hours": SkillName.cnc_setup_operation,
    "assembly_hours": SkillName.assembly_glueups,
    "sanding_hours": SkillName.sanding_prep,
    "finishing_hours": SkillName.finishing,
    "install_hours": SkillName.install_on_site,
    "packing_shipping_hours": SkillName.packing_crating,
}


def build_tasks_from_job_hours(job_payload: Dict[str, Any]) -> Job:
    """
    Build a Job object from a summary payload that includes hour blocks.

    Expected payload keys:
      job_id, job_name, customer, target_ship_date,
      earliest_start_date (optional),
      complexity_level (optional),
      material_prep_hours, cutting_hours, cnc_hours, assembly_hours,
      sanding_hours, finishing_hours, install_hours, packing_shipping_hours
    """
    earliest_raw = job_payload.get("earliest_start_date")
    earliest = date.fromisoformat(earliest_raw) if earliest_raw else date.today()
    complexity = ComplexityLevel(job_payload.get("complexity_level", "med"))

    tasks: List[TaskBlock] = []
    for key, skill in TASK_SKILL_MAP.items():
        hours = float(job_payload.get(key, 0) or 0)
        if hours <= 0:
            continue
        task_id = f"{job_payload['job_id']}_{key}"
        tasks.append(
            TaskBlock(
                task_id=task_id,
                job_id=job_payload["job_id"],
                name=key.replace("_hours", "").replace("_", " ").title(),
                required_skill=skill,
                complexity_level=complexity,
                earliest_start_date=earliest,
                due_date=date.fromisoformat(job_payload["target_ship_date"]),
                precedence=[],
                base_hours=hours,
            )
        )

    return Job(
        job_id=job_payload["job_id"],
        job_name=job_payload["job_name"],
        customer=job_payload["customer"],
        target_ship_date=date.fromisoformat(job_payload["target_ship_date"]),
        tasks=tasks,
    )


def load_jobs(path: str | Path) -> List[Job]:
    """Load jobs from a JSON file."""
    path = Path(path)
    data = json.loads(path.read_text())
    return [Job.model_validate(item) for item in data]

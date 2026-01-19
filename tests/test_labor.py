import sys
from datetime import date
from pathlib import Path
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.labor.schema import (
    ComplexityLevel,
    Employee,
    EmploymentType,
    HoursAvailability,
    Job,
    QualityRisk,
    ReliabilityOverhead,
    SchedulerConfig,
    SkillName,
    SkillRating,
    SkillsProfile,
    TaskBlock,
    CNCExperience,
    ExperienceHistory,
    WeaknessesPreferences,
    SupervisionNeed,
)
from src.labor.scheduler import adjust_duration, schedule_jobs
from src.labor.reports import build_gaps_report, build_cost_report


def _skill(proficiency: int, speed: float, risk: QualityRisk) -> SkillRating:
    return SkillRating(
        proficiency_score=proficiency,
        speed_multiplier=speed,
        quality_risk=risk,
        experience_examples="",
    )


def _base_employee(employee_id: str, rate: float, proficiency: int) -> Employee:
    skills = SkillsProfile(
        rough_cutting_milling=_skill(proficiency, 1.0, QualityRisk.low),
        joinery=_skill(proficiency, 1.0, QualityRisk.low),
        assembly_glueups=_skill(proficiency, 1.0, QualityRisk.low),
        sanding_prep=_skill(proficiency, 1.0, QualityRisk.low),
        finishing=_skill(proficiency, 1.0, QualityRisk.low),
        cnc_setup_operation=_skill(proficiency, 1.0, QualityRisk.low),
        cad_cam=_skill(proficiency, 1.0, QualityRisk.low),
        install_on_site=_skill(proficiency, 1.0, QualityRisk.low),
        packing_crating=_skill(proficiency, 1.0, QualityRisk.low),
        troubleshooting_rework=_skill(proficiency, 1.0, QualityRisk.low),
    )
    return Employee(
        employee_id=employee_id,
        name="Test Worker",
        role_title="Carpenter",
        employment_type=EmploymentType.full_time,
        hourly_rate=rate,
        availability=HoursAvailability(hours_per_week=40, days_available=["mon", "tue", "wed", "thu", "fri"]),
        constraints=[],
        skills=skills,
        experience=ExperienceHistory(
            top_job_types=["tables"],
            max_complexity=ComplexityLevel.med,
            max_complexity_examples="",
            materials_familiarity=["ply"],
            finish_familiarity=["poly"],
            cnc_experience=CNCExperience(years=0, typical_ops=[], comfort_level=1),
        ),
        weaknesses=WeaknessesPreferences(),
        reliability=ReliabilityOverhead(rework_rate_pct=0, punctuality_rating=5, supervision_need=SupervisionNeed.none),
    )


class TestLaborScheduler(unittest.TestCase):
    def test_adjust_duration(self):
        config = SchedulerConfig()
        adjusted = adjust_duration(
            base_hours=10,
            complexity_level=ComplexityLevel.high,
            speed_multiplier=1.0,
            rework_rate_pct=5.0,
            quality_risk=QualityRisk.high,
            config=config,
            training_required=False,
        )
        self.assertAlmostEqual(adjusted, 12.75, places=2)

    def test_gap_detection_structure(self):
        employee = _base_employee("emp_1", 25.0, proficiency=5)
        task = TaskBlock(
            task_id="job_1_cutting",
            job_id="job_1",
            name="Cutting",
            required_skill=SkillName.rough_cutting_milling,
            complexity_level=ComplexityLevel.med,
            earliest_start_date=date(2026, 2, 1),
            due_date=date(2026, 2, 2),
            precedence=[],
            base_hours=8,
        )
        job = Job(
            job_id="job_1",
            job_name="Test Job",
            customer="Test Customer",
            target_ship_date=date(2026, 2, 2),
            tasks=[task],
        )
        schedule = schedule_jobs([employee], [job])
        gaps = build_gaps_report([employee], [job], schedule)
        self.assertIn("bottlenecks", gaps)
        self.assertIn("unassigned_tasks", gaps)

    def test_cost_calculation(self):
        employee = _base_employee("emp_2", 20.0, proficiency=5)
        task = TaskBlock(
            task_id="job_2_assembly",
            job_id="job_2",
            name="Assembly",
            required_skill=SkillName.assembly_glueups,
            complexity_level=ComplexityLevel.med,
            earliest_start_date=date(2026, 2, 1),
            due_date=date(2026, 2, 3),
            precedence=[],
            base_hours=10,
        )
        job = Job(
            job_id="job_2",
            job_name="Cost Job",
            customer="Test Customer",
            target_ship_date=date(2026, 2, 3),
            tasks=[task],
        )
        schedule = schedule_jobs([employee], [job])
        costs = build_cost_report([employee], schedule)
        self.assertAlmostEqual(costs["labor_costs_by_job"]["job_2"], 200.0, places=2)


if __name__ == "__main__":
    unittest.main()

"""Schemas for labor intake, pipeline tasks, and scheduling outputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmploymentType(str, Enum):
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"


class QualityRisk(str, Enum):
    low = "low"
    med = "med"
    high = "high"


class ComplexityLevel(str, Enum):
    low = "low"
    med = "med"
    high = "high"


class SupervisionNeed(str, Enum):
    none = "none"
    light = "light"
    medium = "medium"
    heavy = "heavy"


class SkillName(str, Enum):
    rough_cutting_milling = "rough_cutting_milling"
    joinery = "joinery"
    assembly_glueups = "assembly_glueups"
    sanding_prep = "sanding_prep"
    finishing = "finishing"
    cnc_setup_operation = "cnc_setup_operation"
    cad_cam = "cad_cam"
    install_on_site = "install_on_site"
    packing_crating = "packing_crating"
    troubleshooting_rework = "troubleshooting_rework"


class SkillRating(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proficiency_score: int = Field(ge=0, le=5)
    speed_multiplier: float = Field(gt=0, le=2.5)
    quality_risk: QualityRisk
    experience_examples: str = ""


class HoursAvailability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hours_per_week: float = Field(gt=0)
    days_available: List[str]

    @field_validator("days_available")
    @classmethod
    def validate_days_available(cls, value: List[str]) -> List[str]:
        valid = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
        if not value:
            raise ValueError("days_available must include at least one day")
        invalid = [day for day in value if day not in valid]
        if invalid:
            raise ValueError(f"invalid day entries: {invalid}")
        return value


class SkillsProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rough_cutting_milling: SkillRating
    joinery: SkillRating
    assembly_glueups: SkillRating
    sanding_prep: SkillRating
    finishing: SkillRating
    cnc_setup_operation: SkillRating
    cad_cam: SkillRating
    install_on_site: SkillRating
    packing_crating: SkillRating
    troubleshooting_rework: SkillRating


class CNCExperience(BaseModel):
    model_config = ConfigDict(extra="forbid")

    years: float = Field(ge=0)
    typical_ops: List[str] = Field(default_factory=list)
    comfort_level: int = Field(ge=0, le=5)


class ExperienceHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_job_types: List[str] = Field(min_length=1, max_length=3)
    max_complexity: ComplexityLevel
    max_complexity_examples: str = ""
    materials_familiarity: List[str] = Field(default_factory=list)
    finish_familiarity: List[str] = Field(default_factory=list)
    cnc_experience: CNCExperience


class WeaknessesPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tasks_avoid: List[str] = Field(default_factory=list)
    tasks_best: List[str] = Field(default_factory=list)
    error_modes: List[str] = Field(default_factory=list)
    training_needs: List[str] = Field(default_factory=list)


class ReliabilityOverhead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rework_rate_pct: float = Field(ge=0, le=10)
    punctuality_rating: int = Field(ge=1, le=5)
    supervision_need: SupervisionNeed


class Employee(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    role_title: str = Field(min_length=1)
    employment_type: EmploymentType
    hourly_rate: float = Field(gt=0)
    availability: HoursAvailability
    constraints: List[str] = Field(default_factory=list)
    skills: SkillsProfile
    experience: ExperienceHistory
    weaknesses: WeaknessesPreferences
    reliability: ReliabilityOverhead


class TaskBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    required_skill: SkillName
    complexity_level: ComplexityLevel
    earliest_start_date: date
    due_date: date
    precedence: List[str] = Field(default_factory=list)
    base_hours: float = Field(gt=0)


class Job(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1)
    job_name: str = Field(min_length=1)
    customer: str = Field(min_length=1)
    target_ship_date: date
    tasks: List[TaskBlock]


@dataclass
class SchedulerConfig:
    proficiency_threshold: int = 3
    allow_training: bool = True
    training_penalty: float = 1.25
    complexity_factors: Optional[Dict[ComplexityLevel, float]] = None
    risk_rework_factors: Optional[Dict[QualityRisk, float]] = None

    def resolved_complexity_factors(self) -> Dict[ComplexityLevel, float]:
        return self.complexity_factors or {
            ComplexityLevel.low: 0.9,
            ComplexityLevel.med: 1.0,
            ComplexityLevel.high: 1.2,
        }

    def resolved_risk_factors(self) -> Dict[QualityRisk, float]:
        return self.risk_rework_factors or {
            QualityRisk.low: 0.5,
            QualityRisk.med: 1.0,
            QualityRisk.high: 1.5,
        }


SKILL_FIELD_MAP: Dict[SkillName, str] = {
    SkillName.rough_cutting_milling: "rough_cutting_milling",
    SkillName.joinery: "joinery",
    SkillName.assembly_glueups: "assembly_glueups",
    SkillName.sanding_prep: "sanding_prep",
    SkillName.finishing: "finishing",
    SkillName.cnc_setup_operation: "cnc_setup_operation",
    SkillName.cad_cam: "cad_cam",
    SkillName.install_on_site: "install_on_site",
    SkillName.packing_crating: "packing_crating",
    SkillName.troubleshooting_rework: "troubleshooting_rework",
}

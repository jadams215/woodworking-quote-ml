"""Project model -- a body of work for a customer, optionally linked to a quote."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProjectStatus(str, enum.Enum):
    """Lifecycle states for a project."""

    planning = "planning"
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_customer_id", "customer_id"),
        Index("ix_projects_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status", create_type=True),
        nullable=False,
        server_default=ProjectStatus.planning.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    # -- Relationships --
    customer: Mapped["Customer"] = relationship(
        "Customer", back_populates="projects", lazy="selectin"
    )
    quotes: Mapped[list["Quote"]] = relationship(
        "Quote", back_populates="project",
        foreign_keys="Quote.project_id", lazy="selectin",
    )
    completed_records: Mapped[list["CompletedProject"]] = relationship(
        "CompletedProject", back_populates="project", lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<Project id={self.id} name={self.name!r} "
            f"status={self.status.value}>"
        )

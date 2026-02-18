"""Price book snapshot -- immutable blob of all cost tables frozen at quote-send time.

When a quote transitions out of draft, a snapshot of every referenced pricing
table is serialized to JSONB and hashed with SHA-256.  The snapshot is
write-once: it must never be updated or deleted so that any historical quote
can be recalculated to the exact cent.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PriceBookSnapshot(Base):
    __tablename__ = "price_book_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sha256_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # -- Market multipliers (added in migration 003) --
    market_multipliers: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, server_default="{}"
    )

    # -- Relationships --
    creator: Mapped["User | None"] = relationship(
        "User", back_populates="created_snapshots", lazy="selectin"
    )
    quotes: Mapped[list["Quote"]] = relationship(
        "Quote", back_populates="snapshot", lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<PriceBookSnapshot id={self.id} "
            f"hash={self.sha256_hash[:12]}...>"
        )

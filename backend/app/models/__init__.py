"""SQLAlchemy ORM models for the woodworking quoting system v2.

All model modules are imported here so that Alembic's ``target_metadata``
(which reads ``Base.metadata``) can auto-detect every table.
"""

from app.database import Base  # noqa: F401

from app.models import (  # noqa: F401
    audit,
    catalog,
    customer,
    market_index,
    price_book,
    project,
    quote,
    tracking,
    user,
)

__all__ = ["Base"]

"""SQLAlchemy ORM models for Agent Alpha."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import bcrypt
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class User(Base):
    """Application user with role-based access control and password auth.

    Roles: ``admin``, ``user``, ``viewer``

    Usage::

        user = User(username="alice", display_name="Alice")
        user.set_password("secret123")
        assert user.check_password("secret123") is True
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    username: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(
        String(128), nullable=True, default=None
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="user"
    )
    team: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def set_password(self, password: str) -> None:
        """Hash and store the password using bcrypt."""
        self.password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def check_password(self, password: str) -> bool:
        """Verify a password against the stored hash."""
        if self.password_hash is None:
            return False
        return bcrypt.checkpw(
            password.encode("utf-8"),
            self.password_hash.encode("utf-8"),
        )

    def __repr__(self) -> str:
        return f"<User {self.username!r} role={self.role!r}>"

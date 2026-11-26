"""ORM models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; everything stored is UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


# Permissions a non-admin user can be granted. Admins implicitly have all.
PERMISSIONS = ("integrations", "tasks")
DEFAULT_PERMISSIONS = list(PERMISSIONS)

INTEGRATION_KINDS = ("gmail", "discord", "anthropic")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # The built-in `admin` account: cannot be deleted or demoted.
    is_root: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    default_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def has_admin(self) -> bool:
        return self.is_root or self.is_admin

    def can(self, permission: str) -> bool:
        return self.has_admin() or permission in (self.permissions or [])


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    # SHA-256 of the cookie token; the raw token is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(128))
    # Non-secret settings (hosts, ports, email address, flags...).
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Fernet-encrypted secret (app password, webhook URL, API key).
    secret: Mapped[str] = mapped_column(Text)
    # Runtime state (IMAP cursor, last poll, last error).
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    gmail_integration_id: Mapped[int] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Ordered list of {"type": ..., "config": {...}}.
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Email(Base):
    __tablename__ = "emails"
    __table_args__ = (
        UniqueConstraint("integration_id", "uidvalidity", "uid"),
        Index("ix_emails_integration_sender", "integration_id", "sender_addr"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    integration_id: Mapped[int] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"), index=True
    )
    uidvalidity: Mapped[int] = mapped_column(Integer)
    uid: Mapped[int] = mapped_column(Integer)
    message_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sender: Mapped[str] = mapped_column(String(512), default="")
    # Bare lowercased address from `sender`, for sender-history filters.
    sender_addr: Mapped[str] = mapped_column(String(320), default="", server_default="")
    recipients: Mapped[str] = mapped_column(Text, default="")
    subject: Mapped[str] = mapped_column(Text, default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class TaskRun(Base):
    __tablename__ = "task_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id", ondelete="CASCADE"), index=True)
    task_name: Mapped[str] = mapped_column(String(128))
    # completed: every step ran; partial: ran to the end past a step error;
    # stopped: a filter ended the chain; error.
    status: Mapped[str] = mapped_column(String(16))
    log: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiUsage(Base):
    """One billed Anthropic model attempt. A call that fell back to another
    model writes one row per model, since each bills at its own rates."""

    __tablename__ = "api_usage"
    __table_args__ = (Index("ix_api_usage_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    model: Mapped[str] = mapped_column(String(128))
    # message | declined (a fallback took over) | refused
    kind: Mapped[str] = mapped_column(String(16), default="message")
    # Step type that made the call (filter_agent, webhook_agent).
    source: Mapped[str] = mapped_column(String(32), default="")
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    task_name: Mapped[str] = mapped_column(String(128), default="")
    email_id: Mapped[int | None] = mapped_column(
        ForeignKey("emails.id", ondelete="SET NULL"), nullable=True
    )
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_5m_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_1h_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    inference_geo: Mapped[str | None] = mapped_column(String(16), nullable=True)
    billed: Mapped[bool] = mapped_column(Boolean, default=True)
    # Cost in nano-dollars (1e-9 USD) at the prices in effect when recorded;
    # NULL when the model's price was unknown.
    cost_nanousd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

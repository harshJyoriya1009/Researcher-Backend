"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-25

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("default_model", sa.String(100), nullable=False, server_default="gpt-4o-mini"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "research_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False, server_default="New research chat"),
        sa.Column("model", sa.String(100), nullable=False, server_default="gpt-4o-mini"),
        sa.Column("pinned", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_research_sessions_user_id", "research_sessions", ["user_id"])

    message_role = postgresql.ENUM("user", "assistant", "system", name="message_role")
    message_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", postgresql.ENUM("user", "assistant", "system", name="message_role", create_type=False), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("citations", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])

    document_type = postgresql.ENUM("pdf", "docx", "txt", name="document_type")
    document_type.create(op.get_bind(), checkfirst=True)
    document_status = postgresql.ENUM("uploading", "processing", "ready", "error", name="document_status")
    document_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", postgresql.ENUM("pdf", "docx", "txt", name="document_type", create_type=False), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("uploading", "processing", "ready", "error", name="document_status", create_type=False),
            nullable=False,
            server_default="uploading",
        ),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("chunk_count", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"])

    op.create_table(
        "research_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("faithfulness", sa.Float, nullable=True),
        sa.Column("relevance", sa.Float, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        sa.Column("total_tokens", sa.Integer, nullable=True),
        sa.Column("used_retrieval", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("retrieved_chunk_ids", postgresql.JSONB, nullable=True),
        sa.Column("guardrail_passed", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_research_reports_session_id", "research_reports", ["session_id"])


def downgrade() -> None:
    op.drop_table("research_reports")
    op.drop_table("documents")
    postgresql.ENUM(name="document_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="document_type").drop(op.get_bind(), checkfirst=True)
    op.drop_table("messages")
    postgresql.ENUM(name="message_role").drop(op.get_bind(), checkfirst=True)
    op.drop_table("research_sessions")
    op.drop_table("users")

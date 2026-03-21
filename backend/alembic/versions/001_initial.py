"""
NEXUS SDLC - Initial Migration
Auto-generated Alembic migration for all tables
"""

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    """Create all NEXUS SDLC tables."""

    # users
    op.create_table("users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("role", sa.String(20), nullable=False, default="analyst"),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, default=False),
        sa.Column("employee_id", sa.String(50), nullable=True),
        sa.Column("oauth_provider", sa.String(50), nullable=True),
        sa.Column("oauth_subject", sa.String(255), nullable=True),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, default=0),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(), nullable=True),
        sa.Column("api_key_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("api_key_prefix", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])

    # refresh_tokens
    op.create_table("refresh_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("jti", sa.String(36), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # revoked_tokens
    op.create_table("revoked_tokens",
        sa.Column("jti", sa.String(36), primary_key=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )

    # requests
    op.create_table("requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("requestor_name", sa.String(200), nullable=False),
        sa.Column("requestor_email", sa.String(200), nullable=False),
        sa.Column("requestor_employee_id", sa.String(50), nullable=True),
        sa.Column("request_type", sa.String(50), nullable=False),
        sa.Column("source_channel", sa.String(50), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("raw_description", sa.Text(), nullable=False),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("ai_details", sa.Text(), nullable=True),
        sa.Column("ai_next_action", sa.Text(), nullable=True),
        sa.Column("ai_tags", sa.Text(), nullable=True),
        sa.Column("ai_confidence_score", sa.Float(), nullable=False, default=0.0),
        sa.Column("ai_sentiment", sa.String(50), nullable=True),
        sa.Column("ai_rag_context", sa.Text(), nullable=True),
        sa.Column("ai_quality_score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, default="Draft"),
        sa.Column("reviewed_by", sa.String(200), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.String(200), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("is_overdue", sa.Boolean(), nullable=False, default=False),
        sa.Column("agent_pipeline_run", sa.String(100), nullable=True),
        sa.Column("agent_processing_ms", sa.Integer(), nullable=True),
        sa.Column("langsmith_trace_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # follow_ups, audit_logs, agent_executions, knowledge_chunks
    op.create_table("follow_ups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(36), sa.ForeignKey("requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(200), nullable=False),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=False, default=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table("audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(36), sa.ForeignKey("requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("field_name", sa.String(100), nullable=True),
        sa.Column("langsmith_trace_id", sa.String(100), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("correlation_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table("agent_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(36), sa.ForeignKey("requests.id", ondelete="CASCADE"), nullable=True),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("framework", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("input_data", sa.Text(), nullable=True),
        sa.Column("output_data", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("langsmith_trace_id", sa.String(100), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, default=0),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    for table in ["agent_executions", "audit_logs", "follow_ups", "revoked_tokens", "refresh_tokens", "requests", "users"]:
        op.drop_table(table)

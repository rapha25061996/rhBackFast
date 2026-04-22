"""Add presence app tables (pr_presence, pr_work_schedule).

Revision ID: e4f5a6b7c8d9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-22 09:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pr_work_schedule",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("break_start", sa.Time(), nullable=True),
        sa.Column("break_end", sa.Time(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["user_management_user.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_pr_work_schedule_user"),
    )
    op.create_index("ix_pr_work_schedule_user_id", "pr_work_schedule", ["user_id"])

    op.create_table(
        "pr_presence",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date_scan", sa.Date(), nullable=False),
        sa.Column("heure_scan", sa.Time(), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("scan_type", sa.String(length=16), nullable=False),
        sa.Column("is_late", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["user_management_user.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "date_scan", "scan_type", name="uq_presence_user_day_type"),
    )
    op.create_index("ix_pr_presence_user_id", "pr_presence", ["user_id"])
    op.create_index("ix_pr_presence_date_scan", "pr_presence", ["date_scan"])
    op.create_index("ix_pr_presence_user_date", "pr_presence", ["user_id", "date_scan"])


def downgrade() -> None:
    op.drop_index("ix_pr_presence_user_date", table_name="pr_presence")
    op.drop_index("ix_pr_presence_date_scan", table_name="pr_presence")
    op.drop_index("ix_pr_presence_user_id", table_name="pr_presence")
    op.drop_table("pr_presence")
    op.drop_index("ix_pr_work_schedule_user_id", table_name="pr_work_schedule")
    op.drop_table("pr_work_schedule")
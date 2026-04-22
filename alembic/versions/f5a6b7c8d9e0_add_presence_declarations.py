"""Add presence declaration tables (pr_absence_declaration, pr_late_declaration).

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-04-22 14:50:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pr_absence_declaration",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date_debut", sa.Date(), nullable=False),
        sa.Column("date_fin", sa.Date(), nullable=False),
        sa.Column("absence_type", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("justificatif_url", sa.String(length=512), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user_management_user.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"], ["user_management_user.id"], ondelete="SET NULL"
        ),
        sa.CheckConstraint(
            "date_fin >= date_debut", name="ck_absence_decl_dates_ordre"
        ),
    )
    op.create_index(
        "ix_pr_absence_declaration_user_id",
        "pr_absence_declaration",
        ["user_id"],
    )
    op.create_index(
        "ix_pr_absence_declaration_date_debut",
        "pr_absence_declaration",
        ["date_debut"],
    )
    op.create_index(
        "ix_pr_absence_declaration_date_fin",
        "pr_absence_declaration",
        ["date_fin"],
    )
    op.create_index(
        "ix_pr_absence_declaration_status",
        "pr_absence_declaration",
        ["status"],
    )
    op.create_index(
        "ix_pr_absence_declaration_reviewed_by_id",
        "pr_absence_declaration",
        ["reviewed_by_id"],
    )
    op.create_index(
        "ix_pr_absence_decl_user_range",
        "pr_absence_declaration",
        ["user_id", "date_debut", "date_fin"],
    )

    op.create_table(
        "pr_late_declaration",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date_retard", sa.Date(), nullable=False),
        sa.Column("expected_arrival_time", sa.Time(), nullable=True),
        sa.Column("reason_type", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user_management_user.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"], ["user_management_user.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_pr_late_declaration_user_id",
        "pr_late_declaration",
        ["user_id"],
    )
    op.create_index(
        "ix_pr_late_declaration_date_retard",
        "pr_late_declaration",
        ["date_retard"],
    )
    op.create_index(
        "ix_pr_late_declaration_status",
        "pr_late_declaration",
        ["status"],
    )
    op.create_index(
        "ix_pr_late_declaration_reviewed_by_id",
        "pr_late_declaration",
        ["reviewed_by_id"],
    )
    op.create_index(
        "ix_pr_late_decl_user_date",
        "pr_late_declaration",
        ["user_id", "date_retard"],
    )


def downgrade() -> None:
    op.drop_index("ix_pr_late_decl_user_date", table_name="pr_late_declaration")
    op.drop_index(
        "ix_pr_late_declaration_reviewed_by_id", table_name="pr_late_declaration"
    )
    op.drop_index("ix_pr_late_declaration_status", table_name="pr_late_declaration")
    op.drop_index(
        "ix_pr_late_declaration_date_retard", table_name="pr_late_declaration"
    )
    op.drop_index("ix_pr_late_declaration_user_id", table_name="pr_late_declaration")
    op.drop_table("pr_late_declaration")

    op.drop_index(
        "ix_pr_absence_decl_user_range", table_name="pr_absence_declaration"
    )
    op.drop_index(
        "ix_pr_absence_declaration_reviewed_by_id",
        table_name="pr_absence_declaration",
    )
    op.drop_index(
        "ix_pr_absence_declaration_status", table_name="pr_absence_declaration"
    )
    op.drop_index(
        "ix_pr_absence_declaration_date_fin", table_name="pr_absence_declaration"
    )
    op.drop_index(
        "ix_pr_absence_declaration_date_debut", table_name="pr_absence_declaration"
    )
    op.drop_index(
        "ix_pr_absence_declaration_user_id", table_name="pr_absence_declaration"
    )
    op.drop_table("pr_absence_declaration")

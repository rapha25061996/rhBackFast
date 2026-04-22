"""Add presence declaration tables + lookup tables.

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
    # Lookup: absence types
    op.create_table(
        "pr_absence_type",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
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
    )
    op.create_index(
        "ix_pr_absence_type_code",
        "pr_absence_type",
        ["code"],
        unique=True,
    )

    # Lookup: late reason types
    op.create_table(
        "pr_late_reason_type",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
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
    )
    op.create_index(
        "ix_pr_late_reason_type_code",
        "pr_late_reason_type",
        ["code"],
        unique=True,
    )

    # Absence declarations
    op.create_table(
        "pr_absence_declaration",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("absence_type_id", sa.Integer(), nullable=False),
        sa.Column("date_debut", sa.Date(), nullable=False),
        sa.Column("date_fin", sa.Date(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("justificatif_url", sa.String(length=512), nullable=True),
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
            ["absence_type_id"], ["pr_absence_type.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "date_fin IS NULL OR date_fin >= date_debut",
            name="ck_absence_decl_dates_ordre",
        ),
    )
    op.create_index(
        "ix_pr_absence_declaration_user_id",
        "pr_absence_declaration",
        ["user_id"],
    )
    op.create_index(
        "ix_pr_absence_declaration_absence_type_id",
        "pr_absence_declaration",
        ["absence_type_id"],
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
        "ix_pr_absence_decl_user_range",
        "pr_absence_declaration",
        ["user_id", "date_debut", "date_fin"],
    )

    # Late declarations
    op.create_table(
        "pr_late_declaration",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("reason_type_id", sa.Integer(), nullable=False),
        sa.Column("date_retard", sa.Date(), nullable=False),
        sa.Column("expected_arrival_time", sa.Time(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
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
            ["reason_type_id"],
            ["pr_late_reason_type.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_pr_late_declaration_user_id",
        "pr_late_declaration",
        ["user_id"],
    )
    op.create_index(
        "ix_pr_late_declaration_reason_type_id",
        "pr_late_declaration",
        ["reason_type_id"],
    )
    op.create_index(
        "ix_pr_late_declaration_date_retard",
        "pr_late_declaration",
        ["date_retard"],
    )
    op.create_index(
        "ix_pr_late_decl_user_date",
        "pr_late_declaration",
        ["user_id", "date_retard"],
    )


def downgrade() -> None:
    op.drop_index("ix_pr_late_decl_user_date", table_name="pr_late_declaration")
    op.drop_index(
        "ix_pr_late_declaration_date_retard", table_name="pr_late_declaration"
    )
    op.drop_index(
        "ix_pr_late_declaration_reason_type_id", table_name="pr_late_declaration"
    )
    op.drop_index("ix_pr_late_declaration_user_id", table_name="pr_late_declaration")
    op.drop_table("pr_late_declaration")

    op.drop_index(
        "ix_pr_absence_decl_user_range", table_name="pr_absence_declaration"
    )
    op.drop_index(
        "ix_pr_absence_declaration_date_fin", table_name="pr_absence_declaration"
    )
    op.drop_index(
        "ix_pr_absence_declaration_date_debut", table_name="pr_absence_declaration"
    )
    op.drop_index(
        "ix_pr_absence_declaration_absence_type_id",
        table_name="pr_absence_declaration",
    )
    op.drop_index(
        "ix_pr_absence_declaration_user_id", table_name="pr_absence_declaration"
    )
    op.drop_table("pr_absence_declaration")

    op.drop_index("ix_pr_late_reason_type_code", table_name="pr_late_reason_type")
    op.drop_table("pr_late_reason_type")

    op.drop_index("ix_pr_absence_type_code", table_name="pr_absence_type")
    op.drop_table("pr_absence_type")

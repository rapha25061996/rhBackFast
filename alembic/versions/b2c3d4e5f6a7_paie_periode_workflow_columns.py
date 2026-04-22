"""Add workflow columns to paie_periode.

Ajoute 5 colonnes nullables à ``paie_periode`` pour brancher la période de paie
sur le workflow dynamique partagé avec ``conge_app`` (tables
``cg_etape_processus`` / ``cg_statut_processus``) :

- ``etape_courante_id`` (FK → cg_etape_processus.id, ON DELETE SET NULL)
- ``statut_global_id``  (FK → cg_statut_processus.id, ON DELETE SET NULL)
- ``responsable_id``    (FK → rh_employe.id, ON DELETE SET NULL)
- ``date_soumission``   (DATETIME)
- ``date_decision_finale`` (DATETIME)

Les colonnes existantes (``statut`` texte, ``approuve_par_id``, etc.) sont
conservées pour la rétro-compatibilité. Les anciennes périodes restent
lisibles et le champ ``statut`` sera synchronisé automatiquement par le
service de workflow lors des transitions.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-19 15:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Colonnes nullables
    op.add_column(
        "paie_periode",
        sa.Column("etape_courante_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "paie_periode",
        sa.Column("statut_global_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "paie_periode",
        sa.Column("responsable_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "paie_periode",
        sa.Column("date_soumission", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "paie_periode",
        sa.Column("date_decision_finale", sa.DateTime(), nullable=True),
    )

    # 2. Foreign keys
    op.create_foreign_key(
        "fk_paie_periode_etape_courante",
        "paie_periode",
        "cg_etape_processus",
        ["etape_courante_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_paie_periode_statut_global",
        "paie_periode",
        "cg_statut_processus",
        ["statut_global_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_paie_periode_responsable",
        "paie_periode",
        "rh_employe",
        ["responsable_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. Indexes pour faciliter les requêtes (" mes périodes à valider ", etc.)
    op.create_index(
        "ix_paie_periode_etape_courante_id",
        "paie_periode",
        ["etape_courante_id"],
    )
    op.create_index(
        "ix_paie_periode_statut_global_id",
        "paie_periode",
        ["statut_global_id"],
    )
    op.create_index(
        "ix_paie_periode_responsable_id",
        "paie_periode",
        ["responsable_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_paie_periode_responsable_id", table_name="paie_periode")
    op.drop_index("ix_paie_periode_statut_global_id", table_name="paie_periode")
    op.drop_index("ix_paie_periode_etape_courante_id", table_name="paie_periode")

    op.drop_constraint(
        "fk_paie_periode_responsable", "paie_periode", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_paie_periode_statut_global", "paie_periode", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_paie_periode_etape_courante", "paie_periode", type_="foreignkey"
    )

    op.drop_column("paie_periode", "date_decision_finale")
    op.drop_column("paie_periode", "date_soumission")
    op.drop_column("paie_periode", "responsable_id")
    op.drop_column("paie_periode", "statut_global_id")
    op.drop_column("paie_periode", "etape_courante_id")

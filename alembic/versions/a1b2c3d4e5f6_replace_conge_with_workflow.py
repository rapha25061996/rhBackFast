"""Replace conge module with workflow-based version.

Revision ID: a1b2c3d4e5f6
Revises: d7a92dd58145
Create Date: 2026-04-19 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "d7a92dd58145"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the old conge tables and create the new workflow-based schema."""

    # 1. Drop old conge tables (order matters for FKs).
    op.execute("DROP TABLE IF EXISTS cg_historique_conge CASCADE")
    op.execute("DROP TABLE IF EXISTS cg_demande_conge CASCADE")
    op.execute("DROP TABLE IF EXISTS cg_solde_conge CASCADE")
    op.execute("DROP TABLE IF EXISTS cg_type_conge CASCADE")
    op.execute("DROP TABLE IF EXISTS cg_jour_ferie CASCADE")

    # 2. cg_type_conge
    op.create_table(
        "cg_type_conge",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("nom", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("nb_jours_max_par_an", sa.Float(), nullable=False, server_default="0"),
        sa.Column("report_autorise", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("necessite_validation", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_cg_type_conge_code", "cg_type_conge", ["code"], unique=True)

    # 3. cg_solde_conge
    op.create_table(
        "cg_solde_conge",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("employe_id", sa.Integer(), nullable=False),
        sa.Column("type_conge_id", sa.Integer(), nullable=False),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("alloue", sa.Float(), nullable=False, server_default="0"),
        sa.Column("utilise", sa.Float(), nullable=False, server_default="0"),
        sa.Column("restant", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reporte", sa.Float(), nullable=False, server_default="0"),
        sa.Column("date_expiration", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["employe_id"], ["rh_employe.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["type_conge_id"], ["cg_type_conge.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("employe_id", "type_conge_id", "annee", name="uq_solde_employe_type_annee"),
    )
    op.create_index("ix_cg_solde_conge_employe_id", "cg_solde_conge", ["employe_id"])
    op.create_index("ix_cg_solde_conge_type_conge_id", "cg_solde_conge", ["type_conge_id"])
    op.create_index("ix_cg_solde_conge_annee", "cg_solde_conge", ["annee"])

    # 4. cg_statut_processus
    op.create_table(
        "cg_statut_processus",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("code_statut", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_cg_statut_processus_code_statut", "cg_statut_processus", ["code_statut"], unique=True)

    # 5. cg_etape_processus
    op.create_table(
        "cg_etape_processus",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("code_processus", sa.String(length=50), nullable=False),
        sa.Column("ordre", sa.Integer(), nullable=False),
        sa.Column("nom_etape", sa.String(length=100), nullable=False),
        sa.Column("poste_id", sa.Integer(), nullable=True),
        sa.Column("is_responsable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["poste_id"], ["rh_service_group.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("code_processus", "ordre", name="uq_etape_processus_ordre"),
    )
    op.create_index("ix_cg_etape_processus_code_processus", "cg_etape_processus", ["code_processus"])
    op.create_index("ix_cg_etape_processus_poste_id", "cg_etape_processus", ["poste_id"])

    # 6. cg_action_etape_processus
    op.create_table(
        "cg_action_etape_processus",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("etape_id", sa.Integer(), nullable=False),
        sa.Column("nom_action", sa.String(length=50), nullable=False),
        sa.Column("statut_cible_id", sa.Integer(), nullable=False),
        sa.Column("etape_suivante_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["etape_id"], ["cg_etape_processus.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["statut_cible_id"], ["cg_statut_processus.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["etape_suivante_id"], ["cg_etape_processus.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_cg_action_etape_processus_etape_id", "cg_action_etape_processus", ["etape_id"])

    # 7. cg_demande_conge
    op.create_table(
        "cg_demande_conge",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("employe_id", sa.Integer(), nullable=False),
        sa.Column("type_conge_id", sa.Integer(), nullable=False),
        sa.Column("date_debut", sa.Date(), nullable=False),
        sa.Column("demi_journee_debut", sa.String(length=10), nullable=True),
        sa.Column("date_fin", sa.Date(), nullable=False),
        sa.Column("demi_journee_fin", sa.String(length=10), nullable=True),
        sa.Column("nb_jours_ouvres", sa.Float(), nullable=False, server_default="0"),
        sa.Column("etape_courante_id", sa.Integer(), nullable=False),
        sa.Column("responsable_id", sa.Integer(), nullable=True),
        sa.Column("statut_global_id", sa.Integer(), nullable=False),
        sa.Column("date_soumission", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("date_decision_finale", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["employe_id"], ["rh_employe.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["type_conge_id"], ["cg_type_conge.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["etape_courante_id"], ["cg_etape_processus.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["responsable_id"], ["rh_employe.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["statut_global_id"], ["cg_statut_processus.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "demi_journee_debut IS NULL OR demi_journee_debut IN ('matin', 'apres-midi')",
            name="ck_demi_journee_debut",
        ),
        sa.CheckConstraint(
            "demi_journee_fin IS NULL OR demi_journee_fin IN ('matin', 'apres-midi')",
            name="ck_demi_journee_fin",
        ),
        sa.CheckConstraint("date_fin >= date_debut", name="ck_demande_dates_ordre"),
    )
    op.create_index("ix_cg_demande_conge_employe_id", "cg_demande_conge", ["employe_id"])
    op.create_index("ix_cg_demande_conge_type_conge_id", "cg_demande_conge", ["type_conge_id"])
    op.create_index("ix_cg_demande_conge_etape_courante_id", "cg_demande_conge", ["etape_courante_id"])
    op.create_index("ix_cg_demande_conge_statut_global_id", "cg_demande_conge", ["statut_global_id"])
    op.create_index("ix_cg_demande_conge_date_debut", "cg_demande_conge", ["date_debut"])
    op.create_index("ix_cg_demande_conge_date_fin", "cg_demande_conge", ["date_fin"])

    # 8. cg_demande_attribution
    op.create_table(
        "cg_demande_attribution",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("demande_type", sa.String(length=50), nullable=False),
        sa.Column("demande_id", sa.Integer(), nullable=False),
        sa.Column("etape_id", sa.Integer(), nullable=False),
        sa.Column("valideur_attribue_id", sa.Integer(), nullable=False),
        sa.Column("date_attribution", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("statut", sa.String(length=30), nullable=False, server_default="en_attente"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["etape_id"], ["cg_etape_processus.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["valideur_attribue_id"], ["rh_employe.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "statut IN ('en_attente', 'prise_en_charge', 'traitee')",
            name="ck_attribution_statut",
        ),
    )
    op.create_index("idx_attribution_demande", "cg_demande_attribution", ["demande_type", "demande_id"])
    op.create_index("ix_cg_demande_attribution_etape_id", "cg_demande_attribution", ["etape_id"])
    op.create_index("ix_cg_demande_attribution_valideur_attribue_id", "cg_demande_attribution", ["valideur_attribue_id"])
    op.create_index("ix_cg_demande_attribution_statut", "cg_demande_attribution", ["statut"])

    # 9. cg_historique_demande
    op.create_table(
        "cg_historique_demande",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("demande_type", sa.String(length=50), nullable=False),
        sa.Column("demande_id", sa.Integer(), nullable=False),
        sa.Column("etape_id", sa.Integer(), nullable=False),
        sa.Column("action_id", sa.Integer(), nullable=False),
        sa.Column("nouveau_statut_id", sa.Integer(), nullable=False),
        sa.Column("valideur_id", sa.Integer(), nullable=False),
        sa.Column("commentaire", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["etape_id"], ["cg_etape_processus.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["action_id"], ["cg_action_etape_processus.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["nouveau_statut_id"], ["cg_statut_processus.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["valideur_id"], ["rh_employe.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_historique_demande", "cg_historique_demande", ["demande_type", "demande_id"])


def downgrade() -> None:
    """Drop the new conge tables and recreate empty old ones (reversible)."""

    op.drop_index("idx_historique_demande", table_name="cg_historique_demande")
    op.drop_table("cg_historique_demande")

    op.drop_index("ix_cg_demande_attribution_statut", table_name="cg_demande_attribution")
    op.drop_index("ix_cg_demande_attribution_valideur_attribue_id", table_name="cg_demande_attribution")
    op.drop_index("ix_cg_demande_attribution_etape_id", table_name="cg_demande_attribution")
    op.drop_index("idx_attribution_demande", table_name="cg_demande_attribution")
    op.drop_table("cg_demande_attribution")

    op.drop_index("ix_cg_demande_conge_date_fin", table_name="cg_demande_conge")
    op.drop_index("ix_cg_demande_conge_date_debut", table_name="cg_demande_conge")
    op.drop_index("ix_cg_demande_conge_statut_global_id", table_name="cg_demande_conge")
    op.drop_index("ix_cg_demande_conge_etape_courante_id", table_name="cg_demande_conge")
    op.drop_index("ix_cg_demande_conge_type_conge_id", table_name="cg_demande_conge")
    op.drop_index("ix_cg_demande_conge_employe_id", table_name="cg_demande_conge")
    op.drop_table("cg_demande_conge")

    op.drop_index("ix_cg_action_etape_processus_etape_id", table_name="cg_action_etape_processus")
    op.drop_table("cg_action_etape_processus")

    op.drop_index("ix_cg_etape_processus_poste_id", table_name="cg_etape_processus")
    op.drop_index("ix_cg_etape_processus_code_processus", table_name="cg_etape_processus")
    op.drop_table("cg_etape_processus")

    op.drop_index("ix_cg_statut_processus_code_statut", table_name="cg_statut_processus")
    op.drop_table("cg_statut_processus")

    op.drop_index("ix_cg_solde_conge_annee", table_name="cg_solde_conge")
    op.drop_index("ix_cg_solde_conge_type_conge_id", table_name="cg_solde_conge")
    op.drop_index("ix_cg_solde_conge_employe_id", table_name="cg_solde_conge")
    op.drop_table("cg_solde_conge")

    op.drop_index("ix_cg_type_conge_code", table_name="cg_type_conge")
    op.drop_table("cg_type_conge")

    # Recreate empty legacy tables so the downgrade leaves a valid previous state.
    op.create_table(
        "cg_jour_ferie",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pays_code", sa.String(length=2), nullable=False),
        sa.Column("nom", sa.String(length=200), nullable=False),
        sa.Column("date_ferie", sa.Date(), nullable=False),
        sa.Column("type_date", sa.String(length=20), nullable=False),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("est_personnalise", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("pays_code", "nom", "annee", name="uq_pays_nom_annee"),
    )

    op.create_table(
        "cg_type_conge",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nom", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("nb_jours_max_par_an", sa.Float(), nullable=False, server_default="0"),
        sa.Column("report_autorise", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("necessite_validation", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("niveaux_validation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("couleur", sa.String(length=7), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_cg_type_conge_code", "cg_type_conge", ["code"], unique=True)

    op.create_table(
        "cg_solde_conge",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employe_id", sa.Integer(), nullable=False),
        sa.Column("type_conge_id", sa.Integer(), nullable=False),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("alloue", sa.Float(), nullable=False, server_default="0"),
        sa.Column("utilise", sa.Float(), nullable=False, server_default="0"),
        sa.Column("restant", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reporte", sa.Float(), nullable=False, server_default="0"),
        sa.Column("date_expiration", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["employe_id"], ["rh_employe.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["type_conge_id"], ["cg_type_conge.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "cg_demande_conge",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employe_id", sa.Integer(), nullable=False),
        sa.Column("type_conge_id", sa.Integer(), nullable=False),
        sa.Column("date_debut", sa.Date(), nullable=False),
        sa.Column("date_fin", sa.Date(), nullable=False),
        sa.Column("est_demi_journee", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("periode_demi_journee", sa.String(length=20), nullable=True),
        sa.Column("nb_jours_demandes", sa.Float(), nullable=False, server_default="0"),
        sa.Column("nb_jours_ouvrables", sa.Float(), nullable=False, server_default="0"),
        sa.Column("raison", sa.Text(), nullable=False),
        sa.Column("statut", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("niveau_validation_actuel", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("date_soumission", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("date_decision_finale", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["employe_id"], ["rh_employe.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["type_conge_id"], ["cg_type_conge.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "cg_historique_conge",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("demande_conge_id", sa.Integer(), nullable=False),
        sa.Column("niveau_validation", sa.Integer(), nullable=False),
        sa.Column("valideur_id", sa.Integer(), nullable=True),
        sa.Column("poste_valideur_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("date_action", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("commentaire", sa.Text(), nullable=True),
        sa.Column("delegue_a_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["demande_conge_id"], ["cg_demande_conge.id"], ondelete="CASCADE"),
    )

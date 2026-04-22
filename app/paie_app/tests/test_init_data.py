"""Tests d'idempotence du script d'initialisation du workflow paie."""
import pytest
from sqlalchemy import func, select

from app.conge_app.models import (
    ActionEtapeProcessus,
    EtapeProcessus,
    StatutProcessus,
)
from app.paie_app.init_data import init_paie_workflow_defaults
from app.paie_app.constants import (
    CodeProcessusPaie,
    CodeStatutPaie,
    NomActionPaie,
)


class TestPaieInitData:
    @pytest.mark.asyncio
    async def test_init_creates_full_workflow(self, db):
        await init_paie_workflow_defaults(db)

        # Statuts
        codes = {s.value for s in CodeStatutPaie}
        existing = {
            r.code_statut
            for r in (await db.execute(select(StatutProcessus))).scalars().all()
        }
        assert codes.issubset(existing)

        # 4 étapes pour PAIE
        etapes = (
            await db.execute(
                select(EtapeProcessus)
                .where(EtapeProcessus.code_processus == CodeProcessusPaie.PAIE.value)
                .order_by(EtapeProcessus.ordre.asc())
            )
        ).scalars().all()
        assert [e.nom_etape for e in etapes] == [
            "Calcul RH",
            "Validation Chef de service",
            "Validation Direction",
            "Paiement",
        ]
        assert etapes[1].is_responsable is True

        # Actions attendues par étape
        names_by_ordre: dict[int, set[str]] = {}
        for e in etapes:
            actions = (
                await db.execute(
                    select(ActionEtapeProcessus).where(
                        ActionEtapeProcessus.etape_id == e.id
                    )
                )
            ).scalars().all()
            names_by_ordre[e.ordre] = {a.nom_action for a in actions}

        assert names_by_ordre[1] == {NomActionPaie.PRET_A_VALIDER.value}
        assert names_by_ordre[2] == {
            NomActionPaie.APPROUVER.value,
            NomActionPaie.REJETER.value,
            NomActionPaie.DEMANDER_MODIF.value,
        }
        assert names_by_ordre[3] == {
            NomActionPaie.APPROUVER.value,
            NomActionPaie.REJETER.value,
            NomActionPaie.DEMANDER_MODIF.value,
        }
        assert names_by_ordre[4] == {NomActionPaie.MARQUER_PAYE.value}

    @pytest.mark.asyncio
    async def test_init_is_idempotent(self, db):
        await init_paie_workflow_defaults(db)
        count_etapes_1 = (
            await db.execute(select(func.count(EtapeProcessus.id)))
        ).scalar()
        count_actions_1 = (
            await db.execute(select(func.count(ActionEtapeProcessus.id)))
        ).scalar()

        # Deuxième run → aucun doublon créé
        await init_paie_workflow_defaults(db)
        count_etapes_2 = (
            await db.execute(select(func.count(EtapeProcessus.id)))
        ).scalar()
        count_actions_2 = (
            await db.execute(select(func.count(ActionEtapeProcessus.id)))
        ).scalar()

        assert count_etapes_2 == count_etapes_1
        assert count_actions_2 == count_actions_1

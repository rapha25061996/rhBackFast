"""Unit tests for SoldeService."""
import pytest

from app.conge_app.services import SoldeService


class TestSoldeService:
    @pytest.mark.asyncio
    async def test_ensure_solde_creates(self, db, workflow_setup):
        setup = workflow_setup
        solde = await SoldeService.ensure_solde(
            db, setup["employe"].id, setup["type_ca"].id, 2026, alloue_par_defaut=30.0
        )
        assert solde.alloue == 30.0
        assert solde.restant == 30.0

    @pytest.mark.asyncio
    async def test_debit_reduces_restant(self, db, workflow_setup):
        setup = workflow_setup
        solde = await SoldeService.debit(
            db, setup["employe"].id, setup["type_ca"].id, 2025, 5.0
        )
        assert solde.utilise == 5.0
        assert solde.restant == 15.0

    @pytest.mark.asyncio
    async def test_debit_insufficient_raises(self, db, workflow_setup):
        setup = workflow_setup
        with pytest.raises(ValueError):
            await SoldeService.debit(
                db, setup["employe"].id, setup["type_ca"].id, 2025, 100.0
            )

    @pytest.mark.asyncio
    async def test_can_debit_threshold(self, db, workflow_setup):
        setup = workflow_setup
        solde = setup["solde"]
        assert SoldeService.can_debit(solde, 20.0) is True
        assert SoldeService.can_debit(solde, 20.01) is False

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, db, workflow_setup):
        setup = workflow_setup
        solde = await SoldeService.upsert(
            db, setup["employe"].id, setup["type_ca"].id, 2025, alloue=25.0, reporte=2.0
        )
        assert solde.alloue == 25.0
        assert solde.reporte == 2.0
        assert solde.restant == 27.0

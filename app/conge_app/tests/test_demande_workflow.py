"""Tests d'intégration : création de demande + parcours complet du workflow."""
from datetime import date

import pytest

from app.conge_app.constants import CodeStatut
from app.conge_app.schemas import DemandeCongeCreate
from app.conge_app.services import (
    DemandeCongeService,
    SoldeService,
    WorkflowService,
)
from app.conge_app.services.workflow_service import WorkflowPermissionError


class TestDemandeWorkflow:
    @pytest.mark.asyncio
    async def test_create_demande_computes_days_and_starts_workflow(
        self, db, workflow_setup
    ):
        setup = workflow_setup
        payload = DemandeCongeCreate(
            employe_id=setup["employe"].id,
            type_conge_id=setup["type_ca"].id,
            date_debut=date(2025, 1, 6),
            date_fin=date(2025, 1, 10),
        )
        demande = await DemandeCongeService.create_demande(
            db, payload, country_code="FR", language="fr"
        )
        assert demande.id is not None
        assert demande.nb_jours_ouvres == 5.0
        assert demande.etape_courante_id == setup["etape_resp"].id
        assert (
            demande.statut_global_id
            == setup["statuts"][CodeStatut.EN_ATTENTE.value].id
        )
        assert demande.responsable_id == setup["responsable"].id

    @pytest.mark.asyncio
    async def test_create_demande_rejects_insufficient_balance(
        self, db, workflow_setup
    ):
        setup = workflow_setup
        # Le solde est de 20 jours, on demande 25 (5 semaines pleines).
        payload = DemandeCongeCreate(
            employe_id=setup["employe"].id,
            type_conge_id=setup["type_ca"].id,
            date_debut=date(2025, 1, 6),
            date_fin=date(2025, 2, 7),
        )
        with pytest.raises(PermissionError):
            await DemandeCongeService.create_demande(
                db, payload, country_code="FR", language="fr"
            )

    @pytest.mark.asyncio
    async def test_create_demande_unknown_employe(self, db, workflow_setup):
        setup = workflow_setup
        payload = DemandeCongeCreate(
            employe_id=999,
            type_conge_id=setup["type_ca"].id,
            date_debut=date(2025, 1, 6),
            date_fin=date(2025, 1, 10),
        )
        with pytest.raises(LookupError):
            await DemandeCongeService.create_demande(
                db, payload, country_code="FR", language="fr"
            )

    @pytest.mark.asyncio
    async def test_full_workflow_approve_debits_solde(self, db, workflow_setup):
        setup = workflow_setup
        payload = DemandeCongeCreate(
            employe_id=setup["employe"].id,
            type_conge_id=setup["type_ca"].id,
            date_debut=date(2025, 1, 6),
            date_fin=date(2025, 1, 10),
        )
        demande = await DemandeCongeService.create_demande(
            db, payload, country_code="FR", language="fr"
        )

        # Étape 1 : responsable approuve → passe à l'étape RH
        demande = await WorkflowService.apply_action(
            db,
            demande,
            action_id=setup["action_resp_appr"].id,
            valideur_employe_id=setup["responsable"].id,
            commentaire="OK",
        )
        assert demande.etape_courante_id == setup["etape_rh"].id
        assert demande.date_decision_finale is None

        # Étape 2 : RH approuve → workflow terminé, solde débité
        demande = await WorkflowService.apply_action(
            db,
            demande,
            action_id=setup["action_rh_appr"].id,
            valideur_employe_id=setup["rh_user"].id,
            commentaire="Validé RH",
        )
        assert demande.date_decision_finale is not None
        assert (
            demande.statut_global_id
            == setup["statuts"][CodeStatut.VALIDE.value].id
        )

        solde = await SoldeService.get_solde(
            db, setup["employe"].id, setup["type_ca"].id, 2025
        )
        assert solde is not None
        assert solde.utilise == 5.0
        assert solde.restant == 15.0

    @pytest.mark.asyncio
    async def test_reject_does_not_debit_solde(self, db, workflow_setup):
        setup = workflow_setup
        payload = DemandeCongeCreate(
            employe_id=setup["employe"].id,
            type_conge_id=setup["type_ca"].id,
            date_debut=date(2025, 1, 6),
            date_fin=date(2025, 1, 10),
        )
        demande = await DemandeCongeService.create_demande(
            db, payload, country_code="FR", language="fr"
        )
        demande = await WorkflowService.apply_action(
            db,
            demande,
            action_id=setup["action_resp_rej"].id,
            valideur_employe_id=setup["responsable"].id,
            commentaire="Refusé",
        )
        assert demande.date_decision_finale is not None
        assert (
            demande.statut_global_id
            == setup["statuts"][CodeStatut.REJETE.value].id
        )
        solde = await SoldeService.get_solde(
            db, setup["employe"].id, setup["type_ca"].id, 2025
        )
        assert solde.utilise == 0.0
        assert solde.restant == 20.0

    @pytest.mark.asyncio
    async def test_non_valideur_cannot_apply_action(self, db, workflow_setup):
        setup = workflow_setup
        payload = DemandeCongeCreate(
            employe_id=setup["employe"].id,
            type_conge_id=setup["type_ca"].id,
            date_debut=date(2025, 1, 6),
            date_fin=date(2025, 1, 10),
        )
        demande = await DemandeCongeService.create_demande(
            db, payload, country_code="FR", language="fr"
        )
        with pytest.raises(WorkflowPermissionError):
            await WorkflowService.apply_action(
                db,
                demande,
                action_id=setup["action_resp_appr"].id,
                # C'est le demandeur lui-même, pas le responsable.
                valideur_employe_id=setup["employe"].id,
            )

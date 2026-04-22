"""Tests d'intégration pour le workflow dynamique de la paie."""
import pytest

from app.conge_app.services.attribution_service import AttributionService
from app.paie_app.services.paie_workflow_service import (
    PaieWorkflowPermissionError,
    PaieWorkflowService,
    PaieWorkflowStateError,
)
from app.paie_app.constants import (
    CodeStatutPaie,
    DemandeTypePaie,
    PeriodeStatutTexte,
    StatutAttribution,
)


class TestPaieWorkflow:
    @pytest.mark.asyncio
    async def test_submit_positions_periode_at_first_step(
        self, db, paie_workflow_setup
    ):
        setup = paie_workflow_setup
        periode = setup["periode"]

        periode = await PaieWorkflowService.submit_periode(
            db, periode, responsable_id=setup["employes"]["chef"].id
        )
        await db.commit()

        assert periode.etape_courante_id == setup["etapes"]["calcul"].id
        assert (
            periode.statut_global_id
            == setup["statuts"][CodeStatutPaie.EN_ATTENTE.value].id
        )
        assert periode.responsable_id == setup["employes"]["chef"].id
        assert periode.date_soumission is not None
        assert periode.date_decision_finale is None
        # Le statut texte doit être synchronisé (PROCESSING)
        assert periode.statut == PeriodeStatutTexte.PROCESSING.value

        # Attribution créée pour l'employé RH (seul sur le poste)
        attributions = await AttributionService.list_attributions_for_step(
            db,
            demande_id=periode.id,
            etape_id=setup["etapes"]["calcul"].id,
            demande_type=DemandeTypePaie.PERIODE_PAIE.value,
        )
        assert len(attributions) == 1
        assert attributions[0].valideur_attribue_id == setup["employes"]["rh"].id
        # Seul valideur → directement prise_en_charge
        assert attributions[0].statut == StatutAttribution.PRISE_EN_CHARGE.value

    @pytest.mark.asyncio
    async def test_submit_twice_raises(self, db, paie_workflow_setup):
        setup = paie_workflow_setup
        periode = setup["periode"]
        await PaieWorkflowService.submit_periode(db, periode)
        await db.commit()
        with pytest.raises(PaieWorkflowStateError):
            await PaieWorkflowService.submit_periode(db, periode)

    @pytest.mark.asyncio
    async def test_full_workflow_until_paid(self, db, paie_workflow_setup):
        setup = paie_workflow_setup
        periode = setup["periode"]

        # 1. Soumission
        periode = await PaieWorkflowService.submit_periode(
            db, periode, responsable_id=setup["employes"]["chef"].id
        )
        await db.commit()

        # 2. RH → PRET_A_VALIDER (passe à Validation chef service)
        periode = await PaieWorkflowService.apply_action(
            db,
            periode=periode,
            action_id=setup["actions"]["calcul_ready"].id,
            valideur_employe_id=setup["employes"]["rh"].id,
            commentaire="Calcul OK",
        )
        await db.commit()
        assert periode.etape_courante_id == setup["etapes"]["chef"].id
        assert (
            periode.statut_global_id
            == setup["statuts"][CodeStatutPaie.EN_COURS.value].id
        )
        assert periode.date_decision_finale is None

        # L'attribution chef de service (is_responsable) doit pointer sur le
        # responsable désigné lors de la soumission.
        attributions = await AttributionService.list_attributions_for_step(
            db,
            demande_id=periode.id,
            etape_id=setup["etapes"]["chef"].id,
            demande_type=DemandeTypePaie.PERIODE_PAIE.value,
        )
        assert len(attributions) == 1
        assert attributions[0].valideur_attribue_id == setup["employes"]["chef"].id
        assert attributions[0].statut == StatutAttribution.PRISE_EN_CHARGE.value

        # 3. Chef → APPROUVER (passe à Direction)
        periode = await PaieWorkflowService.apply_action(
            db,
            periode=periode,
            action_id=setup["actions"]["chef_appr"].id,
            valideur_employe_id=setup["employes"]["chef"].id,
            commentaire="Accord chef",
        )
        await db.commit()
        assert periode.etape_courante_id == setup["etapes"]["direction"].id

        # 4. Direction → APPROUVER (passe à Paiement, statut VALIDE)
        periode = await PaieWorkflowService.apply_action(
            db,
            periode=periode,
            action_id=setup["actions"]["dir_appr"].id,
            valideur_employe_id=setup["employes"]["direction"].id,
            commentaire="Accord direction",
        )
        await db.commit()
        assert periode.etape_courante_id == setup["etapes"]["paiement"].id
        assert (
            periode.statut_global_id
            == setup["statuts"][CodeStatutPaie.VALIDE.value].id
        )
        # Passage VALIDE → statut texte APPROVED
        assert periode.statut == PeriodeStatutTexte.APPROVED.value
        assert periode.date_decision_finale is None  # workflow pas encore fini

        # 5. Finance → MARQUER_PAYE (fin de workflow, statut PAYE)
        periode = await PaieWorkflowService.apply_action(
            db,
            periode=periode,
            action_id=setup["actions"]["paie_marquer"].id,
            valideur_employe_id=setup["employes"]["finance"].id,
            commentaire="Paiement effectué",
        )
        await db.commit()
        assert (
            periode.statut_global_id
            == setup["statuts"][CodeStatutPaie.PAYE.value].id
        )
        assert periode.statut == PeriodeStatutTexte.PAID.value
        assert periode.date_decision_finale is not None

    @pytest.mark.asyncio
    async def test_reject_at_chef_stops_workflow(self, db, paie_workflow_setup):
        setup = paie_workflow_setup
        periode = setup["periode"]
        periode = await PaieWorkflowService.submit_periode(
            db, periode, responsable_id=setup["employes"]["chef"].id
        )
        periode = await PaieWorkflowService.apply_action(
            db,
            periode=periode,
            action_id=setup["actions"]["calcul_ready"].id,
            valideur_employe_id=setup["employes"]["rh"].id,
        )
        periode = await PaieWorkflowService.apply_action(
            db,
            periode=periode,
            action_id=setup["actions"]["chef_rej"].id,
            valideur_employe_id=setup["employes"]["chef"].id,
            commentaire="Erreur de calcul",
        )
        await db.commit()

        assert (
            periode.statut_global_id
            == setup["statuts"][CodeStatutPaie.REJETE.value].id
        )
        assert periode.date_decision_finale is not None
        assert periode.statut == PeriodeStatutTexte.DRAFT.value

    @pytest.mark.asyncio
    async def test_non_valideur_cannot_act(self, db, paie_workflow_setup):
        setup = paie_workflow_setup
        periode = setup["periode"]
        periode = await PaieWorkflowService.submit_periode(db, periode)

        # L'outsider n'est pas l'attributaire de l'étape "Calcul RH"
        with pytest.raises(PaieWorkflowPermissionError):
            await PaieWorkflowService.apply_action(
                db,
                periode=periode,
                action_id=setup["actions"]["calcul_ready"].id,
                valideur_employe_id=setup["employes"]["outsider"].id,
            )

    @pytest.mark.asyncio
    async def test_apply_action_not_in_workflow_raises(
        self, db, paie_workflow_setup
    ):
        setup = paie_workflow_setup
        periode = setup["periode"]
        # Pas encore soumis → pas d'étape courante
        with pytest.raises(PaieWorkflowStateError):
            await PaieWorkflowService.apply_action(
                db,
                periode=periode,
                action_id=setup["actions"]["calcul_ready"].id,
                valideur_employe_id=setup["employes"]["rh"].id,
            )

    @pytest.mark.asyncio
    async def test_demander_modif_returns_to_calcul(self, db, paie_workflow_setup):
        setup = paie_workflow_setup
        periode = setup["periode"]
        periode = await PaieWorkflowService.submit_periode(
            db, periode, responsable_id=setup["employes"]["chef"].id
        )
        periode = await PaieWorkflowService.apply_action(
            db,
            periode=periode,
            action_id=setup["actions"]["calcul_ready"].id,
            valideur_employe_id=setup["employes"]["rh"].id,
        )
        # Chef demande modif → retour à l'étape Calcul RH
        periode = await PaieWorkflowService.apply_action(
            db,
            periode=periode,
            action_id=setup["actions"]["chef_modif"].id,
            valideur_employe_id=setup["employes"]["chef"].id,
            commentaire="À corriger",
        )
        await db.commit()

        assert periode.etape_courante_id == setup["etapes"]["calcul"].id
        assert (
            periode.statut_global_id
            == setup["statuts"][CodeStatutPaie.EN_MODIFICATION.value].id
        )
        assert periode.date_decision_finale is None
        # Nouvelle attribution créée pour le poste RH
        attributions = await AttributionService.list_attributions_for_step(
            db,
            demande_id=periode.id,
            etape_id=setup["etapes"]["calcul"].id,
            demande_type=DemandeTypePaie.PERIODE_PAIE.value,
        )
        assert any(
            a.valideur_attribue_id == setup["employes"]["rh"].id
            and a.statut == StatutAttribution.PRISE_EN_CHARGE.value
            for a in attributions
        )

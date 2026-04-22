"""Fixtures pytest pour le workflow paie (SQLite in-memory).

Parallèle à ``app/conge_app/tests/conftest.py`` mais oriente le workflow vers
``code_processus='PAIE'`` / ``demande_type='PERIODE_PAIE'`` et crée en plus la
table ``paie_periode``.
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Import every app model so Base.metadata knows about them before create_all.
from app.audit_app import models as _audit_models  # noqa: F401
from app.conge_app import models as _conge_models  # noqa: F401
from app.conge_app.models import (
    ActionEtapeProcessus,
    EtapeProcessus,
    StatutProcessus,
)
from app.core.database import Base
from app.paie_app import models as _paie_models  # noqa: F401
from app.paie_app.models import PeriodePaie
from app.paie_app.constants import (
    CodeProcessusPaie,
    CodeStatutPaie,
    NomActionPaie,
    PeriodeStatutTexte,
)
from app.reset_password_app import models as _pwd_models  # noqa: F401
from app.user_app import models as _user_models  # noqa: F401
from app.user_app.models import Employe, Group, Service, ServiceGroup


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Tables nécessaires côté workflow (partagées conge_app) + paie_periode.
_WORKFLOW_TABLES = [
    "cg_statut_processus",
    "cg_etape_processus",
    "cg_action_etape_processus",
    "cg_demande_attribution",
    "cg_historique_demande",
]

_PAIE_TABLES = [
    "paie_periode",
]

_USER_TABLES = [
    "rh_service",
    "user_management_group",
    "rh_service_group",
    "user_management_user",
    "user_management_usergroup",
    "user_management_permission",
    "user_management_grouppermission",
    "rh_employe",
    "rh_contrat",
    "rh_document",
]


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    wanted = set(_WORKFLOW_TABLES) | set(_PAIE_TABLES) | set(_USER_TABLES)
    tables = [t for t in Base.metadata.sorted_tables if t.name in wanted]
    async with eng.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables)
        )
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


def _make_employe(prenom: str, nom: str, email: str, **extra) -> Employe:
    return Employe(
        prenom=prenom,
        nom=nom,
        sexe="M",
        date_naissance=date(1980, 1, 1),
        statut_matrimonial="S",
        nationalite="FR",
        banque="N/A",
        numero_compte="0",
        niveau_etude="N/A",
        numero_inss="0",
        email_personnel=email,
        telephone_personnel="+33000000000",
        adresse_ligne1="-",
        date_embauche=date(2020, 1, 1),
        nom_contact_urgence="-",
        lien_contact_urgence="-",
        telephone_contact_urgence="+33000000000",
        **extra,
    )


@pytest_asyncio.fixture
async def paie_workflow_setup(db: AsyncSession):
    """Crée un workflow PAIE minimal à 4 étapes avec employés associés.

    - Étape 1 : Calcul RH (poste RH)
    - Étape 2 : Validation Chef service (is_responsable=True)
    - Étape 3 : Validation Direction (poste Direction)
    - Étape 4 : Paiement (poste Finance)
    """
    # Statuts
    statut_codes = [s.value for s in CodeStatutPaie]
    statuts: dict[str, StatutProcessus] = {}
    for code in statut_codes:
        st = StatutProcessus(code_statut=code)
        db.add(st)
        statuts[code] = st
    await db.flush()

    # Structure org
    service = Service(code="ADM", titre="Administration", description="Adm")
    db.add(service)
    await db.flush()

    group_rh = Group(code="RH", name="RH")
    group_dir = Group(code="DIR", name="Direction")
    group_fin = Group(code="FIN", name="Finance")
    db.add_all([group_rh, group_dir, group_fin])
    await db.flush()

    poste_rh = ServiceGroup(service_id=service.id, group_id=group_rh.id)
    poste_dir = ServiceGroup(service_id=service.id, group_id=group_dir.id)
    poste_fin = ServiceGroup(service_id=service.id, group_id=group_fin.id)
    db.add_all([poste_rh, poste_dir, poste_fin])
    await db.flush()

    # Étapes
    code_processus = CodeProcessusPaie.PAIE.value
    etape_calcul = EtapeProcessus(
        code_processus=code_processus,
        ordre=1,
        nom_etape="Calcul RH",
        is_responsable=False,
        poste_id=poste_rh.id,
    )
    etape_chef = EtapeProcessus(
        code_processus=code_processus,
        ordre=2,
        nom_etape="Validation Chef service",
        is_responsable=True,
    )
    etape_direction = EtapeProcessus(
        code_processus=code_processus,
        ordre=3,
        nom_etape="Validation Direction",
        is_responsable=False,
        poste_id=poste_dir.id,
    )
    etape_paiement = EtapeProcessus(
        code_processus=code_processus,
        ordre=4,
        nom_etape="Paiement",
        is_responsable=False,
        poste_id=poste_fin.id,
    )
    db.add_all([etape_calcul, etape_chef, etape_direction, etape_paiement])
    await db.flush()

    # Actions
    action_calcul_ready = ActionEtapeProcessus(
        etape_id=etape_calcul.id,
        nom_action=NomActionPaie.PRET_A_VALIDER.value,
        statut_cible_id=statuts[CodeStatutPaie.EN_COURS.value].id,
        etape_suivante_id=etape_chef.id,
    )
    action_chef_appr = ActionEtapeProcessus(
        etape_id=etape_chef.id,
        nom_action=NomActionPaie.APPROUVER.value,
        statut_cible_id=statuts[CodeStatutPaie.EN_COURS.value].id,
        etape_suivante_id=etape_direction.id,
    )
    action_chef_rej = ActionEtapeProcessus(
        etape_id=etape_chef.id,
        nom_action=NomActionPaie.REJETER.value,
        statut_cible_id=statuts[CodeStatutPaie.REJETE.value].id,
        etape_suivante_id=None,
    )
    action_chef_modif = ActionEtapeProcessus(
        etape_id=etape_chef.id,
        nom_action=NomActionPaie.DEMANDER_MODIF.value,
        statut_cible_id=statuts[CodeStatutPaie.EN_MODIFICATION.value].id,
        etape_suivante_id=etape_calcul.id,
    )
    action_dir_appr = ActionEtapeProcessus(
        etape_id=etape_direction.id,
        nom_action=NomActionPaie.APPROUVER.value,
        statut_cible_id=statuts[CodeStatutPaie.VALIDE.value].id,
        etape_suivante_id=etape_paiement.id,
    )
    action_paie_marquer = ActionEtapeProcessus(
        etape_id=etape_paiement.id,
        nom_action=NomActionPaie.MARQUER_PAYE.value,
        statut_cible_id=statuts[CodeStatutPaie.PAYE.value].id,
        etape_suivante_id=None,
    )
    db.add_all(
        [
            action_calcul_ready,
            action_chef_appr,
            action_chef_rej,
            action_chef_modif,
            action_dir_appr,
            action_paie_marquer,
        ]
    )
    await db.flush()

    # Employés
    rh_user = _make_employe("Rh", "Operator", "rh@ex.com", poste_id=poste_rh.id)
    chef_service = _make_employe("Chef", "Service", "chef@ex.com")
    dir_user = _make_employe("Dir", "Ection", "dir@ex.com", poste_id=poste_dir.id)
    fin_user = _make_employe("Fin", "Ance", "fin@ex.com", poste_id=poste_fin.id)
    outsider = _make_employe("Out", "Sider", "out@ex.com")
    db.add_all([rh_user, chef_service, dir_user, fin_user, outsider])
    await db.flush()

    # Période de paie initiale (non soumise)
    periode = PeriodePaie(
        annee=2025,
        mois=1,
        date_debut=date(2025, 1, 1),
        date_fin=date(2025, 1, 31),
        statut=PeriodeStatutTexte.DRAFT.value,
    )
    db.add(periode)
    await db.commit()

    return {
        "statuts": statuts,
        "etapes": {
            "calcul": etape_calcul,
            "chef": etape_chef,
            "direction": etape_direction,
            "paiement": etape_paiement,
        },
        "actions": {
            "calcul_ready": action_calcul_ready,
            "chef_appr": action_chef_appr,
            "chef_rej": action_chef_rej,
            "chef_modif": action_chef_modif,
            "dir_appr": action_dir_appr,
            "paie_marquer": action_paie_marquer,
        },
        "postes": {"rh": poste_rh, "dir": poste_dir, "fin": poste_fin},
        "employes": {
            "rh": rh_user,
            "chef": chef_service,
            "direction": dir_user,
            "finance": fin_user,
            "outsider": outsider,
        },
        "periode": periode,
    }

"""Shared pytest fixtures for the conge_app tests (SQLite in-memory)."""
from __future__ import annotations

import asyncio
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Import every app model so Base.metadata knows about them before create_all.
# Even though some tables (audit/paie) aren't created on SQLite, their classes
# must be imported so SQLAlchemy's relationship resolver can find them.
from app.audit_app import models as _audit_models  # noqa: F401
from app.conge_app import models as _conge_models  # noqa: F401
from app.paie_app import models as _paie_models  # noqa: F401
from app.reset_password_app import models as _pwd_models  # noqa: F401
from app.conge_app.constants import CodeProcessus, CodeStatut
from app.conge_app.models import (
    ActionEtapeProcessus,
    EtapeProcessus,
    SoldeConge,
    StatutProcessus,
    TypeConge,
)
from app.core.database import Base
from app.user_app import models as _user_models  # noqa: F401
from app.user_app.models import Employe, Group, Service, ServiceGroup


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


_CONGE_TABLES = [
    "cg_type_conge",
    "cg_solde_conge",
    "cg_statut_processus",
    "cg_etape_processus",
    "cg_action_etape_processus",
    "cg_demande_conge",
    "cg_demande_attribution",
    "cg_historique_demande",
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
    # Only create tables relevant to the conge tests; avoid audit/paie which
    # rely on Postgres-specific types (JSONB) not supported by SQLite.
    wanted = set(_CONGE_TABLES) | set(_USER_TABLES)
    tables = [t for t in Base.metadata.sorted_tables if t.name in wanted]
    async with eng.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def workflow_setup(db: AsyncSession):
    """Crée un workflow CONGE minimal : 2 étapes (N+1 + RH) avec leurs actions."""
    statut_en_attente = StatutProcessus(code_statut=CodeStatut.EN_ATTENTE.value)
    statut_en_cours = StatutProcessus(code_statut=CodeStatut.EN_COURS.value)
    statut_valide = StatutProcessus(code_statut=CodeStatut.VALIDE.value)
    statut_rejete = StatutProcessus(code_statut=CodeStatut.REJETE.value)
    statut_annule = StatutProcessus(code_statut=CodeStatut.ANNULE.value)
    db.add_all([statut_en_attente, statut_en_cours, statut_valide, statut_rejete, statut_annule])
    await db.flush()

    service = Service(code="IT", titre="IT", description="IT")
    db.add(service)
    await db.flush()

    group_manager = Group(code="MANAGER", name="Manager")
    group_rh = Group(code="RH", name="RH")
    db.add_all([group_manager, group_rh])
    await db.flush()

    poste_rh = ServiceGroup(service_id=service.id, group_id=group_rh.id)
    db.add(poste_rh)
    await db.flush()

    etape_resp = EtapeProcessus(
        code_processus=CodeProcessus.CONGE.value,
        ordre=1,
        nom_etape="Responsable",
        is_responsable=True,
    )
    etape_rh = EtapeProcessus(
        code_processus=CodeProcessus.CONGE.value,
        ordre=2,
        nom_etape="RH",
        is_responsable=False,
        poste_id=poste_rh.id,
    )
    db.add_all([etape_resp, etape_rh])
    await db.flush()

    action_resp_appr = ActionEtapeProcessus(
        etape_id=etape_resp.id,
        nom_action="APPROUVER",
        statut_cible_id=statut_en_cours.id,
        etape_suivante_id=etape_rh.id,
    )
    action_resp_rej = ActionEtapeProcessus(
        etape_id=etape_resp.id,
        nom_action="REJETER",
        statut_cible_id=statut_rejete.id,
        etape_suivante_id=None,
    )
    action_rh_appr = ActionEtapeProcessus(
        etape_id=etape_rh.id,
        nom_action="APPROUVER",
        statut_cible_id=statut_valide.id,
        etape_suivante_id=None,
    )
    db.add_all([action_resp_appr, action_resp_rej, action_rh_appr])
    await db.flush()

    type_ca = TypeConge(
        nom="Congé Annuel",
        code="CA",
        nb_jours_max_par_an=30.0,
        report_autorise=True,
        necessite_validation=True,
    )
    db.add(type_ca)
    await db.flush()

    def _make_employe(prenom: str, nom: str, sexe: str, email: str, **extra) -> Employe:
        return Employe(
            prenom=prenom,
            nom=nom,
            sexe=sexe,
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

    # Employés : responsable, demandeur, rh (dans le poste RH)
    responsable = _make_employe("Res", "Ponsable", "M", "resp@ex.com")
    db.add(responsable)
    await db.flush()

    employe = _make_employe(
        "Dem", "Andeur", "M", "emp@ex.com", responsable_id=responsable.id
    )
    db.add(employe)
    await db.flush()

    rh_user = _make_employe(
        "Rh", "Manager", "F", "rh@ex.com", poste_id=poste_rh.id
    )
    db.add(rh_user)
    await db.flush()

    solde = SoldeConge(
        employe_id=employe.id,
        type_conge_id=type_ca.id,
        annee=2025,
        alloue=20.0,
        utilise=0.0,
        restant=20.0,
        reporte=0.0,
    )
    db.add(solde)
    await db.commit()

    return {
        "statuts": {
            CodeStatut.EN_ATTENTE.value: statut_en_attente,
            CodeStatut.EN_COURS.value: statut_en_cours,
            CodeStatut.VALIDE.value: statut_valide,
            CodeStatut.REJETE.value: statut_rejete,
            CodeStatut.ANNULE.value: statut_annule,
        },
        "etape_resp": etape_resp,
        "etape_rh": etape_rh,
        "action_resp_appr": action_resp_appr,
        "action_resp_rej": action_resp_rej,
        "action_rh_appr": action_rh_appr,
        "poste_rh": poste_rh,
        "type_ca": type_ca,
        "responsable": responsable,
        "employe": employe,
        "rh_user": rh_user,
        "solde": solde,
    }

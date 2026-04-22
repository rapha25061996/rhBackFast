"""Seed script producing realistic mock data for user_app, conge_app, paie_app.

Idempotent: safe to run multiple times — existing rows (matched by natural
keys such as ``email``, ``matricule``, ``(annee,mois)``,
``(employe_id, type_conge_id, annee)``...) are reused rather than duplicated.

Usage::

    uv run python -m scripts.seed_mock_data            # insert / upsert mock data
    uv run python -m scripts.seed_mock_data --reset    # delete mock rows first
    uv run python -m scripts.seed_mock_data --quiet    # minimal output

Prerequisites
-------------

* ``uv run alembic upgrade head`` (creates ``cg_*`` tables + paie workflow columns).
* ``uv run python create_permissions.py`` (optional — lets non-superuser accounts
  actually exercise the RBAC once you've wired the group-permission links).

The default password for every generated user account is ``rapha12345678``.
This is intentional mock-data behaviour: rotate credentials before going
anywhere near a non-dev environment.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conge_app.constants import CodeProcessus, CodeStatut
from app.conge_app.init_data import init_conge_defaults
from app.conge_app.models import (
    DemandeConge,
    EtapeProcessus,
    SoldeConge,
    StatutProcessus,
    TypeConge,
)
from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.paie_app.constants import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    CodeProcessusPaie,
    CodeStatutPaie,
    DeductionType,
    PeriodeStatutTexte,
)
from app.paie_app.init_data import init_paie_workflow_defaults
from app.paie_app.models import Alert, EntreePaie, PeriodePaie, RetenueEmploye
from app.user_app.constants import (
    Sexe,
    StatutEmploi,
    StatutMatrimonial,
    TypeContrat,
)
from app.user_app.models import (
    Contrat,
    Employe,
    Group,
    Service,
    ServiceGroup,
    User,
    UserGroup,
)

DEFAULT_PASSWORD = "rapha12345678"


# ---------------------------------------------------------------------------
# Reference data (services, groups, postes)
# ---------------------------------------------------------------------------

SERVICES: list[dict[str, str]] = [
    {"code": "DIR", "titre": "Direction Générale"},
    {"code": "RH", "titre": "Ressources Humaines"},
    {"code": "IT", "titre": "Systèmes d'Information"},
    {"code": "FIN", "titre": "Finance & Comptabilité"},
    {"code": "OPS", "titre": "Opérations"},
    {"code": "COM", "titre": "Commercial & Marketing"},
]

GROUPS: list[dict[str, str]] = [
    {"code": "DIRECTION", "name": "Direction"},
    {"code": "MANAGER", "name": "Chef de service"},
    {"code": "EMPLOYEE", "name": "Employé"},
    {"code": "ADMIN_RH", "name": "Administrateur RH"},
]

# (service_code, group_code) pairs that form the "postes" assignable to an
# employee.
POSTES: list[tuple[str, str]] = [
    ("DIR", "DIRECTION"),
    ("RH", "ADMIN_RH"),
    ("RH", "MANAGER"),
    ("RH", "EMPLOYEE"),
    ("IT", "MANAGER"),
    ("IT", "EMPLOYEE"),
    ("FIN", "MANAGER"),
    ("FIN", "EMPLOYEE"),
    ("OPS", "MANAGER"),
    ("OPS", "EMPLOYEE"),
    ("COM", "MANAGER"),
    ("COM", "EMPLOYEE"),
]


# ---------------------------------------------------------------------------
# Employees + user accounts (emails & matricules are the idempotency keys)
# ---------------------------------------------------------------------------

# `manager_matricule` defines the reporting line (2-level hierarchy). The first
# entry (boss) has None; every manager reports to the boss; every employee
# reports to the manager of their service.
EMPLOYEES: list[dict[str, Any]] = [
    # --- Boss --------------------------------------------------------------
    {
        "matricule": "EMP-001",
        "prenom": "Raphaël",
        "nom": "Mushota",
        "email": "mushota09@gmail.com",
        "sexe": Sexe.MASCULIN.value,
        "statut_matrimonial": StatutMatrimonial.MARIE.value,
        "date_naissance": date(1988, 4, 12),
        "date_embauche": date(2015, 3, 1),
        "poste": ("DIR", "DIRECTION"),
        "manager_matricule": None,
        "is_superuser": True,
        "is_staff": True,
        "salaire_base": Decimal("4500000"),
        "type_contrat": TypeContrat.CDI.value,
        "nombre_enfants": 2,
        "nom_conjoint": "Aimée Mushota",
    },
    # --- Managers (rattachés au boss) -------------------------------------
    {
        "matricule": "EMP-002",
        "prenom": "Benjamin",
        "nom": "Kilolo",
        "email": "mushotaraphael09@gmail.com",
        "sexe": Sexe.MASCULIN.value,
        "statut_matrimonial": StatutMatrimonial.CELIBATAIRE.value,
        "date_naissance": date(1992, 7, 22),
        "date_embauche": date(2018, 9, 15),
        "poste": ("RH", "ADMIN_RH"),
        "manager_matricule": "EMP-001",
        "is_staff": True,
        "salaire_base": Decimal("2600000"),
        "type_contrat": TypeContrat.CDI.value,
    },
    {
        "matricule": "EMP-003",
        "prenom": "Michel",
        "nom": "Lubamba",
        "email": "mushotaraphael07@gmail.com",
        "sexe": Sexe.MASCULIN.value,
        "statut_matrimonial": StatutMatrimonial.CELIBATAIRE.value,
        "date_naissance": date(1994, 1, 30),
        "date_embauche": date(2020, 2, 1),
        "poste": ("RH", "MANAGER"),
        "manager_matricule": "EMP-002",
        "is_staff": True,
        "salaire_base": Decimal("2200000"),
        "type_contrat": TypeContrat.CDI.value,
    },
    {
        "matricule": "EMP-004",
        "prenom": "Chris-Cédric",
        "nom": "Mbombo",
        "email": "chriscedrick4@gmail.com",
        "sexe": Sexe.MASCULIN.value,
        "statut_matrimonial": StatutMatrimonial.MARIE.value,
        "date_naissance": date(1990, 11, 5),
        "date_embauche": date(2017, 6, 15),
        "poste": ("IT", "MANAGER"),
        "manager_matricule": "EMP-001",
        "is_staff": True,
        "salaire_base": Decimal("2800000"),
        "type_contrat": TypeContrat.CDI.value,
        "nombre_enfants": 1,
        "nom_conjoint": "Sarah Mbombo",
    },
    {
        "matricule": "EMP-005",
        "prenom": "David",
        "nom": "Ilunga",
        "email": "david.ilunga@example.com",
        "sexe": Sexe.MASCULIN.value,
        "statut_matrimonial": StatutMatrimonial.MARIE.value,
        "date_naissance": date(1987, 8, 9),
        "date_embauche": date(2016, 4, 1),
        "poste": ("FIN", "MANAGER"),
        "manager_matricule": "EMP-001",
        "is_staff": True,
        "salaire_base": Decimal("2700000"),
        "type_contrat": TypeContrat.CDI.value,
        "nombre_enfants": 3,
        "nom_conjoint": "Clarisse Ilunga",
    },
    {
        "matricule": "EMP-006",
        "prenom": "Patrick",
        "nom": "Kabila",
        "email": "patrick.kabila@example.com",
        "sexe": Sexe.MASCULIN.value,
        "statut_matrimonial": StatutMatrimonial.MARIE.value,
        "date_naissance": date(1985, 2, 14),
        "date_embauche": date(2016, 1, 10),
        "poste": ("OPS", "MANAGER"),
        "manager_matricule": "EMP-001",
        "is_staff": True,
        "salaire_base": Decimal("2500000"),
        "type_contrat": TypeContrat.CDI.value,
        "nombre_enfants": 2,
        "nom_conjoint": "Nadège Kabila",
    },
    {
        "matricule": "EMP-007",
        "prenom": "Esther",
        "nom": "Mbuyi",
        "email": "esther.mbuyi@example.com",
        "sexe": Sexe.FEMININ.value,
        "statut_matrimonial": StatutMatrimonial.MARIE.value,
        "date_naissance": date(1989, 6, 21),
        "date_embauche": date(2019, 9, 3),
        "poste": ("COM", "MANAGER"),
        "manager_matricule": "EMP-001",
        "is_staff": True,
        "salaire_base": Decimal("2450000"),
        "type_contrat": TypeContrat.CDI.value,
        "nombre_enfants": 1,
    },
    # --- Employees (each reports to the manager of its service) -----------
    {
        "matricule": "EMP-008",
        "prenom": "Grace",
        "nom": "Kalombo",
        "email": "grace.kalombo@example.com",
        "sexe": Sexe.FEMININ.value,
        "statut_matrimonial": StatutMatrimonial.CELIBATAIRE.value,
        "date_naissance": date(1996, 3, 18),
        "date_embauche": date(2023, 1, 10),
        "poste": ("IT", "EMPLOYEE"),
        "manager_matricule": "EMP-004",
        "salaire_base": Decimal("1500000"),
        "type_contrat": TypeContrat.CDI.value,
    },
    {
        "matricule": "EMP-009",
        "prenom": "Sarah",
        "nom": "Mwanza",
        "email": "sarah.mwanza@example.com",
        "sexe": Sexe.FEMININ.value,
        "statut_matrimonial": StatutMatrimonial.MARIE.value,
        "date_naissance": date(1993, 12, 2),
        "date_embauche": date(2021, 11, 1),
        "poste": ("FIN", "EMPLOYEE"),
        "manager_matricule": "EMP-005",
        "salaire_base": Decimal("1400000"),
        "type_contrat": TypeContrat.CDD.value,
        "nombre_enfants": 1,
        "nom_conjoint": "Jonathan Mwanza",
    },
    {
        "matricule": "EMP-010",
        "prenom": "Olivier",
        "nom": "Tshisekedi",
        "email": "olivier.tshisekedi@example.com",
        "sexe": Sexe.MASCULIN.value,
        "statut_matrimonial": StatutMatrimonial.CELIBATAIRE.value,
        "date_naissance": date(1998, 5, 25),
        "date_embauche": date(2024, 2, 12),
        "poste": ("OPS", "EMPLOYEE"),
        "manager_matricule": "EMP-006",
        "salaire_base": Decimal("1200000"),
        "type_contrat": TypeContrat.STAGE.value,
    },
    {
        "matricule": "EMP-011",
        "prenom": "Aline",
        "nom": "Kasongo",
        "email": "aline.kasongo@example.com",
        "sexe": Sexe.FEMININ.value,
        "statut_matrimonial": StatutMatrimonial.CELIBATAIRE.value,
        "date_naissance": date(1997, 4, 3),
        "date_embauche": date(2022, 5, 15),
        "poste": ("IT", "EMPLOYEE"),
        "manager_matricule": "EMP-004",
        "salaire_base": Decimal("1600000"),
        "type_contrat": TypeContrat.CDI.value,
    },
    {
        "matricule": "EMP-012",
        "prenom": "Jean",
        "nom": "Mutombo",
        "email": "jean.mutombo@example.com",
        "sexe": Sexe.MASCULIN.value,
        "statut_matrimonial": StatutMatrimonial.MARIE.value,
        "date_naissance": date(1991, 11, 18),
        "date_embauche": date(2019, 7, 1),
        "poste": ("FIN", "EMPLOYEE"),
        "manager_matricule": "EMP-005",
        "salaire_base": Decimal("1700000"),
        "type_contrat": TypeContrat.CDI.value,
        "nombre_enfants": 2,
        "nom_conjoint": "Cynthia Mutombo",
    },
    {
        "matricule": "EMP-013",
        "prenom": "Marie",
        "nom": "Bosenge",
        "email": "marie.bosenge@example.com",
        "sexe": Sexe.FEMININ.value,
        "statut_matrimonial": StatutMatrimonial.MARIE.value,
        "date_naissance": date(1990, 3, 8),
        "date_embauche": date(2018, 10, 20),
        "poste": ("COM", "EMPLOYEE"),
        "manager_matricule": "EMP-007",
        "salaire_base": Decimal("1550000"),
        "type_contrat": TypeContrat.CDI.value,
        "nombre_enfants": 1,
    },
    {
        "matricule": "EMP-014",
        "prenom": "Éric",
        "nom": "Luyindula",
        "email": "eric.luyindula@example.com",
        "sexe": Sexe.MASCULIN.value,
        "statut_matrimonial": StatutMatrimonial.CELIBATAIRE.value,
        "date_naissance": date(1995, 9, 27),
        "date_embauche": date(2022, 3, 1),
        "poste": ("COM", "EMPLOYEE"),
        "manager_matricule": "EMP-007",
        "salaire_base": Decimal("1450000"),
        "type_contrat": TypeContrat.CDD.value,
    },
    {
        "matricule": "EMP-015",
        "prenom": "Didier",
        "nom": "Nkongolo",
        "email": "didier.nkongolo@example.com",
        "sexe": Sexe.MASCULIN.value,
        "statut_matrimonial": StatutMatrimonial.MARIE.value,
        "date_naissance": date(1986, 1, 5),
        "date_embauche": date(2017, 8, 14),
        "poste": ("RH", "EMPLOYEE"),
        "manager_matricule": "EMP-003",
        "salaire_base": Decimal("1550000"),
        "type_contrat": TypeContrat.CDI.value,
        "nombre_enfants": 2,
        "nom_conjoint": "Sonia Nkongolo",
    },
    {
        "matricule": "EMP-016",
        "prenom": "Laurence",
        "nom": "Mpiana",
        "email": "laurence.mpiana@example.com",
        "sexe": Sexe.FEMININ.value,
        "statut_matrimonial": StatutMatrimonial.DIVORCE.value,
        "date_naissance": date(1984, 7, 11),
        "date_embauche": date(2015, 11, 9),
        "poste": ("RH", "EMPLOYEE"),
        "manager_matricule": "EMP-003",
        "salaire_base": Decimal("1650000"),
        "type_contrat": TypeContrat.CDI.value,
        "nombre_enfants": 1,
    },
    {
        "matricule": "EMP-017",
        "prenom": "Kevin",
        "nom": "Ngandu",
        "email": "kevin.ngandu@example.com",
        "sexe": Sexe.MASCULIN.value,
        "statut_matrimonial": StatutMatrimonial.CELIBATAIRE.value,
        "date_naissance": date(1999, 10, 17),
        "date_embauche": date(2024, 6, 3),
        "poste": ("OPS", "EMPLOYEE"),
        "manager_matricule": "EMP-006",
        "salaire_base": Decimal("1150000"),
        "type_contrat": TypeContrat.STAGE.value,
    },
    {
        "matricule": "EMP-018",
        "prenom": "Claudine",
        "nom": "Yav",
        "email": "claudine.yav@example.com",
        "sexe": Sexe.FEMININ.value,
        "statut_matrimonial": StatutMatrimonial.VEUF.value,
        "date_naissance": date(1982, 12, 30),
        "date_embauche": date(2014, 2, 1),
        "poste": ("FIN", "EMPLOYEE"),
        "manager_matricule": "EMP-005",
        "salaire_base": Decimal("1800000"),
        "type_contrat": TypeContrat.CDI.value,
        "nombre_enfants": 3,
    },
]


MATRICULES: list[str] = [e["matricule"] for e in EMPLOYEES]
EMAILS: list[str] = [e["email"] for e in EMPLOYEES]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _employee_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    """Fields with sensible mock defaults shared by every employee."""
    return {
        "nationalite": "Congolaise",
        "banque": "Rawbank",
        "numero_compte": f"RAW-{payload['matricule']}",
        "niveau_etude": "Licence",
        "numero_inss": f"INSS-{payload['matricule']}",
        "telephone_personnel": "+243900000000",
        "adresse_ligne1": "Avenue de la Paix",
        "ville": "Kinshasa",
        "pays": "RDC",
        "nom_contact_urgence": "Famille",
        "lien_contact_urgence": "Parent",
        "telephone_contact_urgence": "+243900000001",
        "nombre_enfants": payload.get("nombre_enfants", 0),
        "nom_conjoint": payload.get("nom_conjoint"),
        "statut_emploi": StatutEmploi.ACTIVE.value,
    }


async def _get_or_create_service(
    db: AsyncSession, payload: dict[str, str]
) -> Service:
    stmt = select(Service).where(Service.code == payload["code"])
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    svc = Service(code=payload["code"], titre=payload["titre"])
    db.add(svc)
    await db.flush()
    return svc


async def _get_or_create_group(db: AsyncSession, payload: dict[str, str]) -> Group:
    stmt = select(Group).where(Group.code == payload["code"])
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    grp = Group(code=payload["code"], name=payload["name"])
    db.add(grp)
    await db.flush()
    return grp


async def _get_or_create_service_group(
    db: AsyncSession, service_id: int, group_id: int
) -> ServiceGroup:
    stmt = select(ServiceGroup).where(
        ServiceGroup.service_id == service_id,
        ServiceGroup.group_id == group_id,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    poste = ServiceGroup(service_id=service_id, group_id=group_id)
    db.add(poste)
    await db.flush()
    return poste


async def _get_or_create_employe(
    db: AsyncSession, payload: dict[str, Any], poste_id: int
) -> Employe:
    stmt = select(Employe).where(Employe.matricule == payload["matricule"])
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    employe = Employe(
        matricule=payload["matricule"],
        prenom=payload["prenom"],
        nom=payload["nom"],
        postnom=payload.get("postnom"),
        date_naissance=payload["date_naissance"],
        sexe=payload["sexe"],
        statut_matrimonial=payload["statut_matrimonial"],
        email_personnel=payload["email"],
        date_embauche=payload["date_embauche"],
        poste_id=poste_id,
        **_employee_defaults(payload),
    )
    db.add(employe)
    await db.flush()
    return employe


async def _get_or_create_user(
    db: AsyncSession, employe: Employe, payload: dict[str, Any]
) -> User:
    stmt = select(User).where(User.email == payload["email"])
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    user = User(
        email=payload["email"],
        password=get_password_hash(DEFAULT_PASSWORD),
        nom=payload["nom"],
        prenom=payload["prenom"],
        is_active=True,
        is_superuser=payload.get("is_superuser", False),
        is_staff=payload.get("is_staff", False),
        employe_id=employe.id,
    )
    db.add(user)
    await db.flush()
    return user


async def _get_or_create_contrat(
    db: AsyncSession, employe: Employe, payload: dict[str, Any]
) -> Contrat:
    stmt = (
        select(Contrat)
        .where(Contrat.employe_id == employe.id)
        .where(Contrat.is_active.is_(True))
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    base = payload["salaire_base"]
    contrat = Contrat(
        employe_id=employe.id,
        type_contrat=payload["type_contrat"],
        date_debut=payload["date_embauche"],
        date_fin=None,
        salaire_base=base,
        indemnite_logement=base * Decimal("0.15"),
        indemnite_transport=Decimal("50000"),
        indemnite_fonction=base * Decimal("0.05"),
        prime_fonction=Decimal("0"),
        autre_avantage=Decimal("0"),
        assurance_patronale=base * Decimal("0.03"),
        assurance_salariale=base * Decimal("0.005"),
        fpc_patronale=base * Decimal("0.02"),
        fpc_salariale=Decimal("0"),
        devise="CDF",
        is_active=True,
    )
    db.add(contrat)
    await db.flush()
    return contrat


async def _link_user_to_group(db: AsyncSession, user_id: int, group: Group) -> None:
    stmt = select(UserGroup).where(
        UserGroup.user_id == user_id,
        UserGroup.group_id == group.id,
    )
    if (await db.execute(stmt)).scalar_one_or_none() is not None:
        return
    db.add(UserGroup(user_id=user_id, group_id=group.id))
    await db.flush()


# ---------------------------------------------------------------------------
# Conge mock data
# ---------------------------------------------------------------------------


async def _seed_soldes(db: AsyncSession, employes: list[Employe]) -> None:
    """Attribue un solde annuel par type de congé à chaque employé."""
    annee = date.today().year
    types = (await db.execute(select(TypeConge))).scalars().all()
    for employe in employes:
        for type_conge in types:
            stmt = select(SoldeConge).where(
                SoldeConge.employe_id == employe.id,
                SoldeConge.type_conge_id == type_conge.id,
                SoldeConge.annee == annee,
            )
            if (await db.execute(stmt)).scalar_one_or_none():
                continue
            alloue = type_conge.nb_jours_max_par_an or 0.0
            db.add(
                SoldeConge(
                    employe_id=employe.id,
                    type_conge_id=type_conge.id,
                    annee=annee,
                    alloue=alloue,
                    utilise=0.0,
                    restant=alloue,
                    reporte=0.0,
                )
            )
    await db.flush()


async def _statut_by_code(db: AsyncSession, code: str) -> StatutProcessus | None:
    stmt = select(StatutProcessus).where(StatutProcessus.code_statut == code)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _etape_conge(db: AsyncSession, ordre: int) -> EtapeProcessus | None:
    stmt = (
        select(EtapeProcessus)
        .where(EtapeProcessus.code_processus == CodeProcessus.CONGE.value)
        .where(EtapeProcessus.ordre == ordre)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _etape_paie(db: AsyncSession, ordre: int) -> EtapeProcessus | None:
    stmt = (
        select(EtapeProcessus)
        .where(EtapeProcessus.code_processus == CodeProcessusPaie.PAIE.value)
        .where(EtapeProcessus.ordre == ordre)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _seed_demandes(
    db: AsyncSession, employes_by_mat: dict[str, Employe]
) -> None:
    """5 demandes couvrant les 5 statuts globaux du workflow conge."""
    type_ca = (
        await db.execute(select(TypeConge).where(TypeConge.code == "CA"))
    ).scalar_one_or_none()
    type_cm = (
        await db.execute(select(TypeConge).where(TypeConge.code == "CM"))
    ).scalar_one_or_none()
    if type_ca is None or type_cm is None:
        return

    etape1 = await _etape_conge(db, 1)
    etape2 = await _etape_conge(db, 2)
    st_attente = await _statut_by_code(db, CodeStatut.EN_ATTENTE.value)
    st_cours = await _statut_by_code(db, CodeStatut.EN_COURS.value)
    st_valide = await _statut_by_code(db, CodeStatut.VALIDE.value)
    st_rejete = await _statut_by_code(db, CodeStatut.REJETE.value)
    st_annule = await _statut_by_code(db, CodeStatut.ANNULE.value)

    if not all([etape1, etape2, st_attente, st_cours, st_valide, st_rejete, st_annule]):
        return

    now = datetime.utcnow()
    samples = [
        {
            "employe": employes_by_mat["EMP-008"],
            "type_conge_id": type_ca.id,
            "start_offset": 30,
            "duration": 5,
            "etape": etape1,
            "statut": st_attente,
            "decision_date": None,
        },
        {
            "employe": employes_by_mat["EMP-009"],
            "type_conge_id": type_cm.id,
            "start_offset": 15,
            "duration": 3,
            "etape": etape2,
            "statut": st_cours,
            "decision_date": None,
        },
        {
            "employe": employes_by_mat["EMP-011"],
            "type_conge_id": type_ca.id,
            "start_offset": -30,
            "duration": 4,
            "etape": etape2,
            "statut": st_valide,
            "decision_date": now - timedelta(days=40),
        },
        {
            "employe": employes_by_mat["EMP-013"],
            "type_conge_id": type_ca.id,
            "start_offset": 60,
            "duration": 10,
            "etape": etape2,
            "statut": st_rejete,
            "decision_date": now - timedelta(days=2),
        },
        {
            "employe": employes_by_mat["EMP-014"],
            "type_conge_id": type_cm.id,
            "start_offset": 45,
            "duration": 2,
            "etape": etape1,
            "statut": st_annule,
            "decision_date": now - timedelta(days=1),
        },
    ]
    for sample in samples:
        employe: Employe = sample["employe"]
        debut = date.today() + timedelta(days=sample["start_offset"])
        fin = debut + timedelta(days=sample["duration"] - 1)
        stmt = select(DemandeConge).where(
            DemandeConge.employe_id == employe.id,
            DemandeConge.date_debut == debut,
            DemandeConge.date_fin == fin,
        )
        if (await db.execute(stmt)).scalar_one_or_none():
            continue
        db.add(
            DemandeConge(
                employe_id=employe.id,
                type_conge_id=sample["type_conge_id"],
                date_debut=debut,
                date_fin=fin,
                nb_jours_ouvres=float(sample["duration"]),
                etape_courante_id=sample["etape"].id,
                responsable_id=employe.responsable_id,
                statut_global_id=sample["statut"].id,
                date_soumission=now - timedelta(days=sample["duration"] * 2),
                date_decision_finale=sample["decision_date"],
            )
        )
    await db.flush()


# ---------------------------------------------------------------------------
# Paie mock data
# ---------------------------------------------------------------------------


async def _seed_entrees_for_periode(
    db: AsyncSession, periode: PeriodePaie, employes: list[Employe]
) -> None:
    for employe in employes:
        contrat = (
            await db.execute(
                select(Contrat)
                .where(Contrat.employe_id == employe.id)
                .where(Contrat.is_active.is_(True))
            )
        ).scalar_one_or_none()
        if contrat is None:
            continue
        stmt = select(EntreePaie).where(
            EntreePaie.employe_id == employe.id,
            EntreePaie.periode_paie_id == periode.id,
        )
        if (await db.execute(stmt)).scalar_one_or_none():
            continue
        salaire_brut = (
            contrat.salaire_base
            + contrat.indemnite_logement
            + contrat.indemnite_transport
            + contrat.indemnite_fonction
        )
        charges_salariales = contrat.assurance_salariale
        salaire_net = salaire_brut - charges_salariales
        db.add(
            EntreePaie(
                employe_id=employe.id,
                periode_paie_id=periode.id,
                contrat_reference={
                    "contrat_id": contrat.id,
                    "salaire_base": str(contrat.salaire_base),
                },
                salaire_base=contrat.salaire_base,
                indemnite_logement=contrat.indemnite_logement,
                indemnite_deplacement=contrat.indemnite_transport,
                indemnite_fonction=contrat.indemnite_fonction,
                allocation_familiale=Decimal("0"),
                autres_avantages=Decimal("0"),
                salaire_brut=salaire_brut,
                cotisations_patronales={
                    "inss_pension": str(contrat.assurance_patronale),
                },
                cotisations_salariales={
                    "inss_pension": str(contrat.assurance_salariale),
                },
                retenues_diverses={},
                total_charge_salariale=charges_salariales,
                base_imposable=salaire_brut - charges_salariales,
                salaire_net=salaire_net,
            )
        )
    await db.flush()


async def _seed_periode(
    db: AsyncSession,
    annee: int,
    mois: int,
    statut_texte: str,
    etape_ordre: int | None,
    statut_code: str | None,
    date_soumission: datetime | None,
    date_decision_finale: datetime | None,
) -> PeriodePaie:
    stmt = select(PeriodePaie).where(
        PeriodePaie.annee == annee, PeriodePaie.mois == mois
    )
    periode = (await db.execute(stmt)).scalar_one_or_none()
    if periode is not None:
        return periode
    date_debut = date(annee, mois, 1)
    if mois == 12:
        date_fin = date(annee, 12, 31)
    else:
        date_fin = date(annee, mois + 1, 1) - timedelta(days=1)
    periode = PeriodePaie(
        annee=annee,
        mois=mois,
        date_debut=date_debut,
        date_fin=date_fin,
        statut=statut_texte,
        date_soumission=date_soumission,
        date_decision_finale=date_decision_finale,
    )
    if etape_ordre is not None:
        etape = await _etape_paie(db, etape_ordre)
        if etape is not None:
            periode.etape_courante_id = etape.id
    if statut_code is not None:
        statut = await _statut_by_code(db, statut_code)
        if statut is not None:
            periode.statut_global_id = statut.id
    db.add(periode)
    await db.flush()
    return periode


async def _seed_retenues(db: AsyncSession, employes: list[Employe]) -> None:
    """Ajoute une retenue 'avance' sur 3 employés (idempotent par (employe, type))."""
    for employe in employes[:3]:
        stmt = select(RetenueEmploye).where(
            RetenueEmploye.employe_id == employe.id,
            RetenueEmploye.type_retenue == DeductionType.AVANCE_SALAIRE.value,
        )
        if (await db.execute(stmt)).scalar_one_or_none():
            continue
        db.add(
            RetenueEmploye(
                employe_id=employe.id,
                type_retenue=DeductionType.AVANCE_SALAIRE.value,
                description="Avance sur salaire",
                montant_mensuel=Decimal("100000"),
                montant_total=Decimal("500000"),
                montant_deja_deduit=Decimal("0"),
                date_debut=date.today().replace(day=1),
                est_active=True,
                est_recurrente=True,
            )
        )
    await db.flush()


async def _seed_alerts(db: AsyncSession, periodes: list[PeriodePaie]) -> None:
    if not periodes:
        return
    samples = [
        {
            "periode": periodes[0],
            "alert_type": AlertType.VALIDATION_ERROR.value,
            "severity": AlertSeverity.HIGH.value,
            "title": "Valeurs de cotisations manquantes",
            "message": "Vérifier les cotisations patronales de la période.",
        },
        {
            "periode": periodes[0],
            "alert_type": AlertType.OTHER.value,
            "severity": AlertSeverity.LOW.value,
            "title": "Rappel — clôture de période",
            "message": "Cette période de paie doit être clôturée avant la fin du mois.",
        },
        {
            "periode": periodes[-1] if len(periodes) > 1 else periodes[0],
            "alert_type": AlertType.CALCULATION_ERROR.value,
            "severity": AlertSeverity.CRITICAL.value,
            "title": "Incohérence sur le net à payer",
            "message": "Écart significatif détecté entre l'ancien calcul et le nouveau.",
        },
    ]
    for sample in samples:
        periode = sample.pop("periode")
        stmt = select(Alert).where(
            Alert.periode_paie_id == periode.id,
            Alert.title == sample["title"],
        )
        if (await db.execute(stmt)).scalar_one_or_none():
            continue
        db.add(
            Alert(
                periode_paie_id=periode.id,
                status=AlertStatus.ACTIVE.value,
                details={},
                **sample,
            )
        )
    await db.flush()


# ---------------------------------------------------------------------------
# Reset (delete mock data)
# ---------------------------------------------------------------------------


async def _reset_mock_data(db: AsyncSession, verbose: bool) -> None:
    employe_ids = [
        row[0]
        for row in (
            await db.execute(
                select(Employe.id).where(Employe.matricule.in_(MATRICULES))
            )
        ).all()
    ]
    if verbose:
        print(f"  • removing mock data for {len(employe_ids)} employe(s)")

    if employe_ids:
        await db.execute(
            delete(EntreePaie).where(EntreePaie.employe_id.in_(employe_ids))
        )
        await db.execute(
            delete(RetenueEmploye).where(RetenueEmploye.employe_id.in_(employe_ids))
        )
        await db.execute(
            delete(Alert).where(Alert.employe_id.in_(employe_ids))
        )
        await db.execute(
            delete(DemandeConge).where(DemandeConge.employe_id.in_(employe_ids))
        )
        await db.execute(
            delete(SoldeConge).where(SoldeConge.employe_id.in_(employe_ids))
        )
        await db.execute(delete(User).where(User.email.in_(EMAILS)))
        await db.execute(delete(Employe).where(Employe.id.in_(employe_ids)))

    today = date.today()
    prev_year, prev_month = _prev_month(today.year, today.month)
    await db.execute(
        delete(PeriodePaie).where(
            PeriodePaie.annee.in_([today.year, prev_year]),
            PeriodePaie.mois.in_([today.month, prev_month]),
        )
    )
    await db.commit()


def _prev_month(annee: int, mois: int) -> tuple[int, int]:
    return (annee - 1, 12) if mois == 1 else (annee, mois - 1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def seed(reset: bool = False, verbose: bool = True) -> None:
    def log(msg: str) -> None:
        if verbose:
            print(msg)

    async with AsyncSessionLocal() as db:
        if reset:
            log("🔄 Resetting mock data...")
            await _reset_mock_data(db, verbose=verbose)

        # 1. Services / groups / postes
        log("🏢 Seeding services + groups + postes...")
        services = {p["code"]: await _get_or_create_service(db, p) for p in SERVICES}
        groups = {p["code"]: await _get_or_create_group(db, p) for p in GROUPS}
        postes: dict[tuple[str, str], ServiceGroup] = {}
        for svc_code, grp_code in POSTES:
            postes[(svc_code, grp_code)] = await _get_or_create_service_group(
                db, services[svc_code].id, groups[grp_code].id
            )

        # 2. Conge / paie default workflow (idempotent)
        log("⚙️  Ensuring CONGE + PAIE workflow defaults...")
        await init_conge_defaults(db)
        await init_paie_workflow_defaults(db)

        # 3. Employees + users + contrats
        log(f"👤 Seeding {len(EMPLOYEES)} employees + user accounts...")
        employes_by_mat: dict[str, Employe] = {}
        for payload in EMPLOYEES:
            poste = postes[payload["poste"]]
            employe = await _get_or_create_employe(db, payload, poste.id)
            user = await _get_or_create_user(db, employe, payload)
            await _get_or_create_contrat(db, employe, payload)
            _, grp_code = payload["poste"]
            await _link_user_to_group(db, user.id, groups[grp_code])
            employes_by_mat[payload["matricule"]] = employe
        await db.commit()

        # 4. Resolve responsable_id once every employee has been committed.
        for payload in EMPLOYEES:
            manager_mat = payload.get("manager_matricule")
            if manager_mat is None:
                continue
            employe = employes_by_mat[payload["matricule"]]
            manager = employes_by_mat[manager_mat]
            if employe.responsable_id != manager.id:
                employe.responsable_id = manager.id
        await db.commit()

        employes = list(employes_by_mat.values())

        # 5. Conge seed data (soldes + 5 demandes covering every statut)
        log("🏖️  Seeding conge soldes + sample demandes (5 statuts)...")
        await _seed_soldes(db, employes)
        await _seed_demandes(db, employes_by_mat)
        await db.commit()

        # 6. Paie seed data — 2 periodes
        today = date.today()
        prev_year, prev_month = _prev_month(today.year, today.month)
        now = datetime.utcnow()

        log(
            f"💰 Seeding paie periodes "
            f"{prev_year}-{prev_month:02d} (PAID) + {today.year}-{today.month:02d} (DRAFT)..."
        )
        # Previous month — full workflow completed
        periode_prev = await _seed_periode(
            db,
            annee=prev_year,
            mois=prev_month,
            statut_texte=PeriodeStatutTexte.PAID.value,
            etape_ordre=4,  # Paiement
            statut_code=CodeStatutPaie.PAYE.value,
            date_soumission=now - timedelta(days=30),
            date_decision_finale=now - timedelta(days=5),
        )
        await _seed_entrees_for_periode(db, periode_prev, employes)

        # Current month — brand-new DRAFT
        periode_now = await _seed_periode(
            db,
            annee=today.year,
            mois=today.month,
            statut_texte=PeriodeStatutTexte.DRAFT.value,
            etape_ordre=1,  # Calcul RH
            statut_code=CodeStatutPaie.EN_ATTENTE.value,
            date_soumission=None,
            date_decision_finale=None,
        )
        await _seed_entrees_for_periode(db, periode_now, employes)

        await _seed_retenues(db, employes)
        await _seed_alerts(db, [periode_now, periode_prev])
        await db.commit()

        log("\n✅ Mock data seeding complete.")
        log(
            f"   - {len(employes)} employees / users (password: {DEFAULT_PASSWORD!r})"
        )
        log(
            f"   - paie periodes: {prev_year}-{prev_month:02d} (PAID) "
            f"and {today.year}-{today.month:02d} (DRAFT)"
        )
        log("   - conge demandes covering EN_ATTENTE / EN_COURS / VALIDE / REJETE / ANNULE")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete mock rows matching the seed fixtures before re-inserting.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output.",
    )
    args = parser.parse_args()
    asyncio.run(seed(reset=args.reset, verbose=not args.quiet))


if __name__ == "__main__":
    main()

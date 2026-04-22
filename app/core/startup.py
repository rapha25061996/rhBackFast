


"""
Application startup tasks

This module handles tasks that should run when the application starts,
such as creating default permissions and loading default holidays.
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import select

from app.core.config import settings
from app.core.database import Base
from app.user_app.models import Permission
from app.conge_app.constants import PERMISSIONS as CONGE_PERMISSIONS
from app.conge_app.init_data import init_conge_defaults
from app.paie_app.init_data import init_paie_workflow_defaults
from app.paie_app.constants import WORKFLOW_PERMISSIONS as PAIE_WORKFLOW_PERMISSIONS


# Audit app permissions
AUDIT_PERMISSIONS = {
    "audit.view": "Consulter les logs d'audit",
}

# Paie app permissions
PAIE_PERMISSIONS = {
    "alert.view": "Consulter les alertes",
    "alert.create": "Créer des alertes",
    "alert.update": "Modifier des alertes",
    "retenue.view": "Consulter les retenues",
    "retenue.create": "Créer des retenues",
    "periode.view": "Consulter les périodes de paie",
    "periode.create": "Créer des périodes de paie",
    "periode.update": "Modifier des périodes de paie",
    "entree.view": "Consulter les entrées de paie",
    "entree.update": "Modifier les entrées de paie",
    "payroll.view": "Consulter et exporter la paie",
    **PAIE_WORKFLOW_PERMISSIONS,
}


# Model to resource name mapping (customize as needed)
MODEL_RESOURCE_MAPPING = {
    "Employe": "employe",
    "User": "user",
    "Group": "group",
    "Service": "service",
    "ServiceGroup": "service_group",
    "UserGroup": "user_group",
    "Permission": "permission",
    "GroupPermission": "group_permission",
    "Contrat": "contrat",
    "Document": "document",
}

# Actions to create for each model
ACTIONS = ["CREATE", "READ", "UPDATE", "DELETE"]

# Content type mapping (customize based on your content type IDs)
CONTENT_TYPE_MAPPING = {
    "employe": 1,
    "user": 2,
    "group": 3,
    "service": 4,
    "service_group": 5,
    "user_group": 6,
    "contrat": 7,
    "document": 8,
    "permission": 9,
    "group_permission": 10,
}


def get_all_models():
    """Get all SQLAlchemy models from Base.metadata"""
    models = []
    for table in Base.metadata.tables.values():
        # Get the model class name from the table
        for mapper in Base.registry.mappers:
            if mapper.local_table.name == table.name:
                model_class = mapper.class_
                models.append(model_class)
                break
    return models


def get_resource_name(model_class):
    """Get resource name for a model"""
    model_name = model_class.__name__
    return MODEL_RESOURCE_MAPPING.get(model_name, model_name.lower())


def get_permission_name(resource: str, action: str) -> str:
    """Generate human-readable permission name"""
    action_names = {
        "CREATE": "Create",
        "READ": "Read",
        "UPDATE": "Update",
        "DELETE": "Delete"
    }
    resource_display = resource.replace("_", " ").title()
    return f"{action_names[action]} {resource_display}"


def get_permission_description(resource: str, action: str) -> str:
    """Generate permission description"""
    action_descriptions = {
        "CREATE": "create new",
        "READ": "view",
        "UPDATE": "update",
        "DELETE": "delete"
    }
    resource_display = resource.replace("_", " ")
    return f"Permission to {action_descriptions[action]} {resource_display}"


async def create_default_permissions():
    """
    Create default CRUD permissions for all models + conge_app permissions.
    This runs at application startup if AUTO_CREATE_PERMISSIONS is True.
    """
    if not settings.AUTO_CREATE_PERMISSIONS:
        print("⏭️  Auto-create permissions disabled (set "
              "AUTO_CREATE_PERMISSIONS=true to enable)")
        return

    print("\n🔐 Creating default permissions...")

    # Create engine and session
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    # Get all models
    models = get_all_models()

    created_count = 0
    skipped_count = 0

    try:
        async with async_session() as session:
            # Create CRUD permissions for all models
            for model_class in models:
                resource = get_resource_name(model_class)
                content_type = CONTENT_TYPE_MAPPING.get(resource, 0)

                for action in ACTIONS:
                    codename = f"{resource}.{action.lower()}"

                    # Check if permission already exists
                    result = await session.execute(
                        select(Permission).where(
                            Permission.codename == codename
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        skipped_count += 1
                        continue

                    # Create permission
                    permission = Permission(
                        codename=codename,
                        name=get_permission_name(resource, action),
                        content_type=content_type,
                        resource=resource,
                        action=action,
                        description=get_permission_description(
                            resource, action
                        )
                    )
                    session.add(permission)
                    created_count += 1

            # Create conge_app specific permissions
            conge_created = 0
            for codename, description in CONGE_PERMISSIONS.items():
                # Check if permission already exists
                result = await session.execute(
                    select(Permission).where(Permission.codename == codename)
                )
                existing = result.scalar_one_or_none()

                if existing:
                    skipped_count += 1
                    continue

                # Extract resource and action from codename
                # (e.g., "conge.view" -> resource="conge", action="VIEW")
                parts = codename.split(".")
                resource = parts[0]
                action = parts[1].upper() if len(parts) > 1 else "CUSTOM"

                # Create permission
                permission = Permission(
                    codename=codename,
                    name=description,
                    content_type=0,  # Custom permission
                    resource=resource,
                    action=action,
                    description=description
                )
                session.add(permission)
                created_count += 1
                conge_created += 1

            # Create audit_app specific permissions
            audit_created = 0
            for codename, description in AUDIT_PERMISSIONS.items():
                # Check if permission already exists
                result = await session.execute(
                    select(Permission).where(Permission.codename == codename)
                )
                existing = result.scalar_one_or_none()

                if existing:
                    skipped_count += 1
                    continue

                # Extract resource and action from codename
                parts = codename.split(".")
                resource = parts[0]
                action = parts[1].upper() if len(parts) > 1 else "CUSTOM"

                # Create permission
                permission = Permission(
                    codename=codename,
                    name=description,
                    content_type=0,  # Custom permission
                    resource=resource,
                    action=action,
                    description=description
                )
                session.add(permission)
                created_count += 1
                audit_created += 1

            # Create paie_app specific permissions
            paie_created = 0
            for codename, description in PAIE_PERMISSIONS.items():
                # Check if permission already exists
                result = await session.execute(
                    select(Permission).where(Permission.codename == codename)
                )
                existing = result.scalar_one_or_none()

                if existing:
                    skipped_count += 1
                    continue

                # Extract resource and action from codename
                parts = codename.split(".")
                resource = parts[0]
                action = parts[1].upper() if len(parts) > 1 else "CUSTOM"

                # Create permission
                permission = Permission(
                    codename=codename,
                    name=description,
                    content_type=0,  # Custom permission
                    resource=resource,
                    action=action,
                    description=description
                )
                session.add(permission)
                created_count += 1
                paie_created += 1

            # Commit all permissions
            await session.commit()

        if created_count > 0:
            print(f"✅ Created {created_count} new permissions")
            if conge_created > 0:
                print(f"   - Conge app: {conge_created} permissions")
            if audit_created > 0:
                print(f"   - Audit app: {audit_created} permissions")
            if paie_created > 0:
                print(f"   - Paie app: {paie_created} permissions")
        if skipped_count > 0:
            print(f"⏭️  Skipped {skipped_count} existing permissions")

        print(f"✓ Permission initialization complete "
              f"({created_count + skipped_count} total)\n")

    except Exception as e:
        print(f"❌ Error creating permissions: {e}\n")
        # Don't raise - allow app to start even if permission creation fails
    finally:
        await engine.dispose()


async def init_conge_workflow_defaults():
    """Initialise les données par défaut du module congé (statuts, types, workflow).

    Rien n'est fait si ``CONGE_INIT_DEFAULTS=False``. Le reste s'appuie uniquement
    sur la lib `holidays` à la volée : aucun chargement en base n'est nécessaire.
    """
    if not getattr(settings, "CONGE_INIT_DEFAULTS", True):
        print("⏭️  Conge defaults init disabled")
        return

    print("\n🎉 Initializing CONGE workflow defaults...")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with async_session() as session:
            await init_conge_defaults(session)
        print("✓ CONGE defaults initialization complete\n")
    except Exception as e:
        print(f"❌ Error initializing CONGE defaults: {e}\n")
    finally:
        await engine.dispose()


async def init_paie_workflow_defaults_task():
    """Initialise les données par défaut du workflow paie (statuts + étapes + actions).

    Désactivable via ``PAIE_INIT_DEFAULTS=False``. Idempotent.
    """
    if not getattr(settings, "PAIE_INIT_DEFAULTS", True):
        print("⏭️  Paie workflow defaults init disabled")
        return

    print("\n💰 Initializing PAIE workflow defaults...")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with async_session() as session:
            await init_paie_workflow_defaults(session)
        print("✓ PAIE workflow defaults initialization complete\n")
    except Exception as e:
        print(f"❌ Error initializing PAIE workflow defaults: {e}\n")
    finally:
        await engine.dispose()


async def run_startup_tasks():
    """
    Run all startup tasks.
    This is called when the application starts.
    """
    await create_default_permissions()
    await init_conge_workflow_defaults()
    await init_paie_workflow_defaults_task()
    # Add other startup tasks here in the future


def startup_event_handler():
    """
    Synchronous wrapper for startup tasks.
    This is called by FastAPI's startup event.
    """
    asyncio.run(run_startup_tasks())

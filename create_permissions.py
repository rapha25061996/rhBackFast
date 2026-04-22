"""
Script to automatically create permissions for all models

This script inspects all SQLAlchemy models and creates CRUD permissions
for each model automatically.

Usage:
    python create_permissions.py
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from app.core.config import settings
from app.core.database import Base
from app.user_app.models import Permission

# Import all models to ensure they're registered with Base.metadata
from app.user_app import models as user_models  # noqa: F401
from app.paie_app import models as paie_models  # noqa: F401
from app.audit_app import models as audit_models  # noqa: F401
from app.conge_app import models as conge_models  # noqa: F401


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
    "AuditLog": "audit",
    "TypeConge": "conge_type",
    "DemandeConge": "conge_demande",
    "SoldeConge": "conge_solde",
    "HistoriqueDemande": "conge_historique",
    "DemandeAttribution": "conge_attribution",
    "StatutProcessus": "conge_statut",
    "EtapeProcessus": "conge_etape",
    "ActionEtapeProcessus": "conge_action",
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
    "audit": 11,
    "conge_type": 12,
    "conge_demande": 13,
    "conge_solde": 14,
    "conge_historique": 15,
    "conge_attribution": 16,
    "conge_statut": 17,
    "conge_etape": 18,
    "conge_action": 19,
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


async def create_permissions_for_models():
    """Create permissions for all models"""
    # Create engine and session
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Get all models
    models = get_all_models()

    print(f"\n{'='*60}")
    print(f"Found {len(models)} models")
    print(f"{'='*60}\n")

    created_count = 0
    skipped_count = 0

    async with async_session() as session:
        # Create permissions for models
        for model_class in models:
            resource = get_resource_name(model_class)
            content_type = CONTENT_TYPE_MAPPING.get(resource, 0)

            print(f"\n📦 Processing model: {model_class.__name__} (resource: {resource})")

            for action in ACTIONS:
                codename = f"{resource}.{action.lower()}"

                # Check if permission already exists
                result = await session.execute(
                    select(Permission).where(Permission.codename == codename)
                )
                existing = result.scalar_one_or_none()

                if existing:
                    print(f"  ⏭️  Skipped: {codename} (already exists)")
                    skipped_count += 1
                    continue

                # Create permission
                permission = Permission(
                    codename=codename,
                    name=get_permission_name(resource, action),
                    content_type=content_type,
                    resource=resource,
                    action=action,
                    description=get_permission_description(resource, action)
                )
                session.add(permission)
                print(f"  ✅ Created: {codename}")
                created_count += 1

        # Create special conge permissions
        special_conge_permissions = [
            {
                "codename": "conge.view",
                "name": "View Leave Data",
                "content_type": 0,
                "resource": "conge",
                "action": "VIEW",
                "description": "Permission to view leave data"
            },
            {
                "codename": "conge.create",
                "name": "Create Leave Requests",
                "content_type": 0,
                "resource": "conge",
                "action": "CREATE",
                "description": "Permission to create leave requests"
            },
            {
                "codename": "conge.update",
                "name": "Update Leave Requests",
                "content_type": 0,
                "resource": "conge",
                "action": "UPDATE",
                "description": "Permission to update leave requests"
            },
            {
                "codename": "conge.delete",
                "name": "Delete Leave Requests",
                "content_type": 0,
                "resource": "conge",
                "action": "DELETE",
                "description": "Permission to delete leave requests"
            },
            {
                "codename": "conge.approve",
                "name": "Approve Leave Requests",
                "content_type": 0,
                "resource": "conge",
                "action": "APPROVE",
                "description": "Permission to approve leave requests"
            },
            {
                "codename": "conge.manage_types",
                "name": "Manage Leave Types",
                "content_type": 0,
                "resource": "conge",
                "action": "MANAGE_TYPES",
                "description": "Permission to manage leave types"
            },
            {
                "codename": "conge.manage_soldes",
                "name": "Manage Leave Balances",
                "content_type": 0,
                "resource": "conge",
                "action": "MANAGE_SOLDES",
                "description": "Permission to manage leave balances"
            },
            {
                "codename": "conge.export",
                "name": "Export Leave Data",
                "content_type": 0,
                "resource": "conge",
                "action": "EXPORT",
                "description": "Permission to export leave data"
            },
        ]

        print("\n📦 Processing special conge permissions")
        for perm_data in special_conge_permissions:
            codename = perm_data["codename"]

            # Check if permission already exists
            result = await session.execute(
                select(Permission).where(Permission.codename == codename)
            )
            existing = result.scalar_one_or_none()

            if existing:
                print(f"  ⏭️  Skipped: {codename} (already exists)")
                skipped_count += 1
                continue

            # Create permission
            permission = Permission(
                codename=perm_data["codename"],
                name=perm_data["name"],
                content_type=perm_data["content_type"],
                resource=perm_data["resource"],
                action=perm_data["action"],
                description=perm_data["description"]
            )
            session.add(permission)
            print(f"  ✅ Created: {codename}")
            created_count += 1

        # Note: Special audit permissions are already created above with standard CRUD actions

        # Commit all permissions
        await session.commit()

    print(f"\n{'='*60}")
    print("✨ Summary:")
    print(f"  - Created: {created_count} permissions")
    print(f"  - Skipped: {skipped_count} permissions (already exist)")
    print(f"  - Total: {created_count + skipped_count} permissions")
    print(f"{'='*60}\n")


async def list_all_permissions():
    """List all permissions in the database"""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            select(Permission).order_by(Permission.resource, Permission.action)
        )
        permissions = result.scalars().all()

        print(f"\n{'='*60}")
        print(f"📋 All Permissions ({len(permissions)} total)")
        print(f"{'='*60}\n")

        current_resource = None
        for perm in permissions:
            if perm.resource != current_resource:
                current_resource = perm.resource
                print(f"\n🔹 {perm.resource.upper()}")
            print(f"  - {perm.codename:30} | {perm.name}")


async def delete_all_permissions():
    """Delete all permissions (use with caution!)"""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(select(Permission))
        permissions = result.scalars().all()

        count = len(permissions)
        for perm in permissions:
            await session.delete(perm)

        await session.commit()
        print(f"🗑️  Deleted {count} permissions")


async def main():
    """Main function"""
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "list":
            await list_all_permissions()
        elif command == "delete":
            print("⚠️  WARNING: This will delete ALL permissions!")
            confirm = input("Type 'yes' to confirm: ")
            if confirm.lower() == "yes":
                await delete_all_permissions()
            else:
                print("❌ Cancelled")
        elif command == "create":
            await create_permissions_for_models()
        else:
            print(f"❌ Unknown command: {command}")
            print("\nUsage:")
            print("  python create_permissions.py create  - Create permissions")
            print("  python create_permissions.py list    - List all permissions")
            print("  python create_permissions.py delete  - Delete all permissions")
    else:
        # Default: create permissions
        await create_permissions_for_models()


if __name__ == "__main__":
    asyncio.run(main())

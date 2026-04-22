"""Drop CHECK constraint ck_permission_action.

Supprime la contrainte CHECK ``ck_permission_action`` qui limitait la colonne
``user_management_permission.action`` à ``('CREATE', 'READ', 'UPDATE',
'DELETE')``. Cette contrainte était incompatible avec les actions réellement
utilisées par l'application et insérées par ``create_permissions.py`` :

- VIEW
- APPROVE
- MANAGE_TYPES
- MANAGE_SOLDES
- MANAGE_WORKFLOW (utilisé par conge_app.routes)
- EXPORT

Le set d'actions valides est piloté côté application (le script d'init + les
workflows). L'identification d'une permission se fait de toute façon sur
``codename`` (ex: ``conge.view``), pas sur le couple ``(resource, action)``,
donc cette contrainte n'apportait rien fonctionnellement et bloquait
``python create_permissions.py`` au premier INSERT ``VIEW``.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-19 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the restrictive CHECK constraint on Permission.action."""
    # ``IF EXISTS`` : tolérant si la DB a déjà été patchée manuellement
    # ou si la contrainte n'a jamais été créée (cas d'une DB toute neuve
    # avant que la migration initiale l'ajoute — improbable mais défensif).
    op.execute(
        "ALTER TABLE user_management_permission "
        "DROP CONSTRAINT IF EXISTS ck_permission_action"
    )


def downgrade() -> None:
    """Recreate the original 4-action CHECK constraint.

    Note : si des lignes avec ``action NOT IN ('CREATE','READ','UPDATE',
    'DELETE')`` existent déjà en base, ce downgrade échouera. Dans ce cas
    il faudra d'abord nettoyer / renommer les permissions étendues.
    """
    op.execute(
        "ALTER TABLE user_management_permission "
        "ADD CONSTRAINT ck_permission_action "
        "CHECK (action IN ('CREATE', 'READ', 'UPDATE', 'DELETE'))"
    )

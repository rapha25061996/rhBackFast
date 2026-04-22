"""Modification history service for tracking changes to payroll data"""
import logging
from datetime import datetime
from typing import Optional, Any, Dict, List
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.paie_app.models import EntreePaie, RetenueEmploye
from app.user_app.models import User

logger = logging.getLogger(__name__)


class ModificationHistoryService:
    """
    Service for tracking and managing modification history.

    This service maintains a detailed history of changes to payroll
    entries and deductions in their respective modification_history
    JSON fields.
    """

    @staticmethod
    async def track_entree_modification(
        db: AsyncSession,
        entree: EntreePaie,
        user: User,
        action: str,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None
    ) -> None:
        """
        Track a modification to a payroll entry.

        Args:
            db: Database session
            entree: EntreePaie instance
            user: User making the modification
            action: Type of action (CREATE, UPDATE, RECALCULATE, etc.)
            old_values: Previous values (for UPDATE)
            new_values: New values (for CREATE/UPDATE)
            reason: Optional reason for the modification
        """
        try:
            # Create modification record
            modification = {
                "timestamp": datetime.utcnow().isoformat(),
                "user_id": user.id,
                "user_name": f"{user.nom} {user.prenom}",
                "user_email": user.email,
                "action": action,
                "reason": reason,
                "changes": {}
            }

            # Track specific field changes
            if old_values and new_values:
                changes = ModificationHistoryService._compute_changes(
                    old_values,
                    new_values
                )
                modification["changes"] = changes

            # Add to history
            if entree.modification_history is None:
                entree.modification_history = []

            entree.modification_history.append(modification)

            # Mark as modified for SQLAlchemy
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(entree, "modification_history")

            await db.commit()

            logger.info(
                f"Tracked modification for EntreePaie {entree.id}: "
                f"{action} by {user.email}"
            )

        except Exception as e:
            logger.error(f"Failed to track entree modification: {e}")
            # Don't raise - history tracking should not break main flow

    @staticmethod
    async def track_retenue_modification(
        db: AsyncSession,
        retenue: RetenueEmploye,
        user: User,
        action: str,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None
    ) -> None:
        """
        Track a modification to an employee deduction.

        Args:
            db: Database session
            retenue: RetenueEmploye instance
            user: User making the modification
            action: Type of action (CREATE, UPDATE, APPLY, etc.)
            old_values: Previous values (for UPDATE)
            new_values: New values (for CREATE/UPDATE)
            reason: Optional reason for the modification
        """
        try:
            # Create modification record
            modification = {
                "timestamp": datetime.utcnow().isoformat(),
                "user_id": user.id,
                "user_name": f"{user.nom} {user.prenom}",
                "user_email": user.email,
                "action": action,
                "reason": reason,
                "changes": {}
            }

            # Track specific field changes
            if old_values and new_values:
                changes = ModificationHistoryService._compute_changes(
                    old_values,
                    new_values
                )
                modification["changes"] = changes

            # Add to history
            if retenue.modification_history is None:
                retenue.modification_history = []

            retenue.modification_history.append(modification)

            # Mark as modified for SQLAlchemy
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(retenue, "modification_history")

            await db.commit()

            logger.info(
                f"Tracked modification for RetenueEmploye {retenue.id}: "
                f"{action} by {user.email}"
            )

        except Exception as e:
            logger.error(f"Failed to track retenue modification: {e}")
            # Don't raise - history tracking should not break main flow

    @staticmethod
    def _compute_changes(
        old_values: Dict[str, Any],
        new_values: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Compute the differences between old and new values.

        Args:
            old_values: Previous values
            new_values: New values

        Returns:
            Dictionary of changes with old and new values
        """
        changes = {}

        # Check all fields in new_values
        for field, new_value in new_values.items():
            old_value = old_values.get(field)

            # Convert Decimal to float for comparison
            if isinstance(old_value, Decimal):
                old_value = float(old_value)
            if isinstance(new_value, Decimal):
                new_value = float(new_value)

            # Only track if value changed
            if old_value != new_value:
                changes[field] = {
                    "old": old_value,
                    "new": new_value
                }

        return changes

    @staticmethod
    async def get_entree_history(
        db: AsyncSession,
        entree_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get modification history for a payroll entry.

        Args:
            db: Database session
            entree_id: EntreePaie ID

        Returns:
            List of modification records
        """
        try:
            stmt = select(EntreePaie).where(EntreePaie.id == entree_id)
            result = await db.execute(stmt)
            entree = result.scalar_one_or_none()

            if not entree:
                return []

            return entree.modification_history or []

        except Exception as e:
            logger.error(f"Failed to get entree history: {e}")
            return []

    @staticmethod
    async def get_retenue_history(
        db: AsyncSession,
        retenue_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get modification history for an employee deduction.

        Args:
            db: Database session
            retenue_id: RetenueEmploye ID

        Returns:
            List of modification records
        """
        try:
            stmt = select(RetenueEmploye).where(
                RetenueEmploye.id == retenue_id
            )
            result = await db.execute(stmt)
            retenue = result.scalar_one_or_none()

            if not retenue:
                return []

            return retenue.modification_history or []

        except Exception as e:
            logger.error(f"Failed to get retenue history: {e}")
            return []

    @staticmethod
    def extract_model_values(instance: Any) -> Dict[str, Any]:
        """
        Extract values from a model instance for tracking.

        Args:
            instance: SQLAlchemy model instance

        Returns:
            Dictionary of field names and values
        """
        if not hasattr(instance, '__table__'):
            return {}

        values = {}
        try:
            for column in instance.__table__.columns:
                # Skip internal fields and history itself
                if column.name not in [
                    'id', 'created_at', 'updated_at',
                    'modification_history'
                ]:
                    value = getattr(instance, column.name, None)
                    # Convert to serializable format
                    if isinstance(value, Decimal):
                        values[column.name] = float(value)
                    elif isinstance(value, datetime):
                        values[column.name] = value.isoformat()
                    elif value is not None:
                        values[column.name] = value
        except Exception as e:
            logger.warning(f"Failed to extract model values: {e}")

        return values

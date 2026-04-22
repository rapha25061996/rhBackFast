"""Local filesystem storage for uploaded documents.

Files are written under `uploads/<folder>/<uuid><ext>` and served by the
`StaticFiles` mount declared in ``main.py`` (path prefix ``/uploads``).
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

UPLOAD_ROOT = Path("uploads")


class LocalStorageService:
    """Persist uploaded files on the local filesystem."""

    def upload_file(
        self,
        file_content: bytes,
        original_filename: str,
        folder: str = "documents",
    ) -> Optional[str]:
        try:
            upload_dir = UPLOAD_ROOT / folder
            upload_dir.mkdir(parents=True, exist_ok=True)

            ext = os.path.splitext(original_filename)[1]
            unique_filename = f"{uuid.uuid4()}{ext}"
            file_path = upload_dir / unique_filename

            with open(file_path, "wb") as f:
                f.write(file_content)

            relative_path = f"uploads/{folder}/{unique_filename}"
            logger.info("Fichier sauvegardé localement: %s", relative_path)
            return relative_path
        except Exception as exc:
            logger.error("Erreur sauvegarde locale: %s", exc)
            return None

    def delete_file(self, file_path: str) -> bool:
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
            return True
        except Exception as exc:
            logger.error("Erreur suppression locale: %s", exc)
            return False


def get_storage_service() -> LocalStorageService:
    """Return the storage backend. Local filesystem is the only supported backend."""
    return LocalStorageService()


def get_storage() -> LocalStorageService:
    """Backward-compatible accessor."""
    return get_storage_service()


storage_service: LocalStorageService = get_storage_service()

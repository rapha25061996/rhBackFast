"""
Utilitaires pour la gestion des fichiers uploadés
"""
import os
import uuid
from pathlib import Path
from typing import Optional, Tuple
from fastapi import UploadFile


class FileManager:
    """Gestionnaire de fichiers pour les uploads"""
    
    UPLOAD_BASE_DIR = Path("uploads")
    DOCUMENTS_DIR = UPLOAD_BASE_DIR / "documents"
    
    # Extensions autorisées par type de document
    ALLOWED_EXTENSIONS = {
        "CONTRACT": [".pdf", ".doc", ".docx"],
        "ID": [".pdf", ".jpg", ".jpeg", ".png"],
        "RESUME": [".pdf", ".doc", ".docx"],
        "CERTIFICATE": [".pdf", ".jpg", ".jpeg", ".png"],
        "PERFORMANCE": [".pdf", ".doc", ".docx"],
        "DISCIPLINARY": [".pdf", ".doc", ".docx"],
        "MEDICAL": [".pdf", ".jpg", ".jpeg", ".png"],
        "TRAINING": [".pdf", ".doc", ".docx"],
        "OTHER": [".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".txt"]
    }
    
    # Taille maximale par type (en bytes)
    MAX_FILE_SIZE = {
        "CONTRACT": 10 * 1024 * 1024,  # 10 MB
        "ID": 5 * 1024 * 1024,  # 5 MB
        "RESUME": 5 * 1024 * 1024,  # 5 MB
        "CERTIFICATE": 5 * 1024 * 1024,  # 5 MB
        "PERFORMANCE": 10 * 1024 * 1024,  # 10 MB
        "DISCIPLINARY": 10 * 1024 * 1024,  # 10 MB
        "MEDICAL": 5 * 1024 * 1024,  # 5 MB
        "TRAINING": 10 * 1024 * 1024,  # 10 MB
        "OTHER": 10 * 1024 * 1024  # 10 MB
    }
    
    @classmethod
    def ensure_directories(cls):
        """Créer les répertoires nécessaires s'ils n'existent pas"""
        cls.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def validate_file(
        cls,
        file: UploadFile,
        document_type: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Valider un fichier avant sauvegarde
        
        Returns:
            (is_valid, error_message)
        """
        # Vérifier l'extension
        file_extension = os.path.splitext(file.filename)[1].lower()
        allowed_extensions = cls.ALLOWED_EXTENSIONS.get(document_type, [])
        
        if allowed_extensions and file_extension not in allowed_extensions:
            return False, f"Extension {file_extension} non autorisée pour {document_type}"
        
        # Vérifier la taille (si possible)
        if hasattr(file, 'size') and file.size:
            max_size = cls.MAX_FILE_SIZE.get(document_type, 10 * 1024 * 1024)
            if file.size > max_size:
                max_mb = max_size / (1024 * 1024)
                return False, f"Fichier trop volumineux (max {max_mb}MB)"
        
        return True, None

    
    @classmethod
    async def save_file(
        cls,
        file: UploadFile,
        document_type: str,
        subdirectory: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Sauvegarder un fichier sur disque
        
        Args:
            file: Fichier à sauvegarder
            document_type: Type de document
            subdirectory: Sous-répertoire optionnel
        
        Returns:
            (success, file_path, error_message)
        """
        try:
            # Valider le fichier
            is_valid, error = cls.validate_file(file, document_type)
            if not is_valid:
                return False, None, error
            
            # Créer les répertoires
            cls.ensure_directories()
            
            # Déterminer le répertoire de destination
            target_dir = cls.DOCUMENTS_DIR
            if subdirectory:
                target_dir = target_dir / subdirectory
                target_dir.mkdir(parents=True, exist_ok=True)
            
            # Générer un nom unique
            file_extension = os.path.splitext(file.filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            file_path = target_dir / unique_filename
            
            # Sauvegarder le fichier
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)
            
            return True, str(file_path), None
            
        except Exception as e:
            return False, None, f"Erreur lors de la sauvegarde: {str(e)}"
    
    @classmethod
    def delete_file(cls, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Supprimer un fichier
        
        Returns:
            (success, error_message)
        """
        try:
            path = Path(file_path)
            if path.exists() and path.is_file():
                path.unlink()
                return True, None
            return False, "Fichier introuvable"
        except Exception as e:
            return False, f"Erreur lors de la suppression: {str(e)}"
    
    @classmethod
    def get_file_info(cls, file_path: str) -> Optional[dict]:
        """
        Obtenir les informations d'un fichier
        
        Returns:
            Dict avec size, extension, exists
        """
        try:
            path = Path(file_path)
            if not path.exists():
                return None
            
            return {
                "exists": True,
                "size": path.stat().st_size,
                "extension": path.suffix,
                "filename": path.name,
                "created": path.stat().st_ctime,
                "modified": path.stat().st_mtime
            }
        except Exception:
            return None
    
    @classmethod
    def cleanup_orphaned_files(cls, valid_paths: list[str]) -> int:
        """
        Nettoyer les fichiers orphelins (non référencés en base)
        
        Args:
            valid_paths: Liste des chemins valides en base de données
        
        Returns:
            Nombre de fichiers supprimés
        """
        deleted_count = 0
        
        try:
            # Parcourir tous les fichiers
            for file_path in cls.DOCUMENTS_DIR.rglob("*"):
                if file_path.is_file():
                    if str(file_path) not in valid_paths:
                        file_path.unlink()
                        deleted_count += 1
        except Exception as e:
            print(f"Erreur lors du nettoyage: {e}")
        
        return deleted_count

# RH Management System - FastAPI

Système de gestion des ressources humaines développé avec FastAPI, SQLAlchemy (asynchrone), Alembic et PostgreSQL.

## 🔥 Nouveau : Système d'Expansion

Le système d'expansion permet de charger automatiquement les relations dans les requêtes API pour éviter les requêtes N+1.

**📖 [Documentation Complète du Système d'Expansion](./EXPAND_DOCUMENTATION_INDEX.md)**

**Exemple rapide :**
```http
# Charger un employé avec son poste, service et groupe
GET /api/employees/?expand=poste.service,poste.group

# Charger les membres d'un groupe avec leurs détails
GET /api/user-groups/?expand=user.employe,group
```

**Guides disponibles :**
- [Guide d'Utilisation](./GUIDE_EXPAND_RELATIONS.md) - Syntaxe complète et exemples
- [Dépannage](./TROUBLESHOOTING_EXPAND.md) - Résolution d'erreurs
- [Cas de Test](./EXPAND_TEST_CASES.md) - Tous les cas supportés

---

## Structure du Projet

```
rhBackFast/
├── app/
│   ├── core/              # Configuration et utilitaires
│   │   ├── config.py      # Configuration de l'application
│   │   ├── database.py    # Configuration base de données
│   │   └── security.py    # Sécurité et authentification
│   ├── user_app/          # Gestion des utilisateurs et RBAC
│   │   └── models.py      # Modèles utilisateurs
│   ├── paie_app/          # Gestion de la paie
│   │   └── models.py      # Modèles paie
│   └── conge_app/         # Gestion des congés
│       └── models.py      # Modèles congés
├── alembic/               # Migrations de base de données
├── main.py                # Point d'entrée de l'application
├── pyproject.toml         # Dépendances du projet
└── .env                   # Variables d'environnement (non versionné — voir .env.example)
```

## 🔐 Configuration des variables d'environnement

Le fichier `.env` **n'est pas versionné** (il contient des secrets : `DATABASE_URL`, `SECRET_KEY`, `SMTP_PASSWORD`, etc.). Pour démarrer :

```bash
cp .env.example .env
# Puis édite .env avec tes vraies valeurs :
# - DATABASE_URL (Postgres local ou Neon)
# - SECRET_KEY (génère avec: openssl rand -hex 32)
# - SMTP_USER / SMTP_PASSWORD (Gmail App Password si 2FA active)
```

> ⚠️ Ne jamais committer `.env`. Le `.gitignore` bloque explicitement tous les `.env*` sauf `.env.example`.

## Modèles Implémentés

### User App (RBAC System)
- ✅ **Service** - Services/Départements
- ✅ **Group** - Groupes/Rôles
- ✅ **ServiceGroup** - Liaison Service-Group (Postes)
- ✅ **User** - Comptes utilisateurs
- ✅ **UserGroup** - Assignation utilisateurs aux groupes
- ✅ **Permission** - Permissions système
- ✅ **GroupPermission** - Permissions des groupes
- ✅ **Employe** - Employés
- ✅ **Contrat** - Contrats de travail
- ✅ **Document** - Documents employés

### Paie App
- ✅ **Alert** - Alertes système de paie
- ✅ **RetenueEmploye** - Retenues salariales
- ✅ **PeriodePaie** - Périodes de paie
- ✅ **EntreePaie** - Entrées de paie

### Conge App
- ✅ **TypeConge** - Types de congés
- ✅ **DemandeConge** - Demandes de congés
- ✅ **SoldeConge** - Soldes de congés
- ✅ **HistoriqueConge** - Historique d
bic**
Éditer `alembic/env.py` pour importer les modèles:
```python
from app.core.database import Base
from app.user_app.models import *
from app.paie_app.models import *
from app.conge_app.models import *

target_metadata = Base.metadata
```

7. **Créer la première migration**
```bash
uv run alembic revision --autogenerate -m "Initial migration"
```

8. **Appliquer les migrations**
```bash
uv run alembic upgrade head
```

9. **Lancer l'application**
```bash
uv run python main.py
```

L'API sera disponible sur http://localhost:8000

## Documentation API

### Documentation Interactive
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Documentation Module Paie
- **[Index de Documentation](PAIE_APP_DOCUMENTATION_INDEX.md)** - Point d'entrée pour toute la documentation
- **[API Documentation Complète](PAIE_APP_API_DOCUMENTATION.md)** - Documentation détaillée de tous les endpoints
- **[API Quick Reference](PAIE_APP_API_QUICK_REFERENCE.md)** - Référence rapide pour consultation quotidienne

### Guides Spécifiques
- **[Payslip Generation Guide](PAYSLIP_GENERATION_GUIDE.md)** - Génération de bulletins de paie PDF
- **[Export Feature Guide](EXPORT_FEATURE_GUIDE.md)** - Export de données Excel/CSV
- **[Statistics Feature Summary](STATISTICS_FEATURE_SUMMARY.md)** - Statistiques et rapports
- **[Notification System Guide](NOTIFICATION_SYSTEM_GUIDE.md)** - Notifications automatiques
- **[Modification History Guide](MODIFICATION_HISTORY_GUIDE.md)** - Historique des modifications

## Prochaines Étapes

1. ✅ Modèles créés
2. ⏳ Schémas Pydantic (schemas)
3. ⏳ Repositories (CRUD operations)
4. ⏳ Services (business logic)
5. ⏳ Routes/Endpoints
6. ⏳ Authentication & Authorization
7. ⏳ Tests

## Technologies

- **FastAPI** - Framework web moderne et rapide
- **SQLAlchemy 2.0** - ORM avec support asynchrone
- **Alembic** - Migrations de base de données
- **PostgreSQL** - Base de données relationnelle
- **asyncpg** - Driver PostgreSQL asynchrone
- **Pydantic** - Validation des données
- **python-jose** - JWT tokens
- **passlib** - Hashing de mots de passe

## Commandes Utiles

```bash
# Lancer en mode développement
uv run python main.py

# Créer une nouvelle migration
uv run alembic revision --autogenerate -m "Description"

# Appliquer les migrations
uv run alembic upgrade head

# Revenir en arrière d'une migration
uv run alembic downgrade -1

# Voir l'historique des migrations
uv run alembic history

# Formater le code
uv run black app/

# Linter
uv run ruff check app/
```

## Structure des Modèles

Tous les modèles héritent de `BaseModel` qui fournit:
- `id`: Clé primaire auto-incrémentée
- `created_at`: Date de création
- `updated_at`: Date de dernière modification

Les relations sont définies avec SQLAlchemy 2.0 style (Mapped, mapped_column).

## Licence

Propriétaire


<!-- ******************************************************************************************************************************************************************************************* -->

je veux que tu analyse rhBackFast pour completer les routes maquant des models suivant:

Service,
Group,
ServiceGroup,
User,
UserGroup,
Permission,
GroupPermission,
Employe,
Contrat,
Document

consignes: 1 analyse d'abord les codes existants , 2 pour les gets ajoutes les expand , la pagination (avec possibilite de de faire /?no_pagination=true) , 3 verifie toujours les erreurs de syntaxe .


"""Payroll management models"""
from datetime import datetime, date
from typing import Optional, TYPE_CHECKING
from decimal import Decimal
from sqlalchemy import (
    String, Integer, Boolean, DateTime, Date, Text, Numeric,
    ForeignKey, UniqueConstraint, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship


Dans rhBackFast principalement le conge_app
commence par analyser les models ou codes existants a fin de comprendre, puis je veux que ce module prenne aussi en charge la GESTION deconge DEMI-JOURNÉE (0.5,0.5==1 journee),GESTION CONGÉ MULTI-PAYS (en utilisant la bibliotheque comme holidays ou autre plus puissante [bien gerer les estimated et observed]) gere la gestion de conge comme un professionnel

consignes:

1 ajouter les expands si necessaire (si c ne pas implementer)
2 la pagination (avec possibilite de de faire /?no_pagination=true) comme dans user_app
3 la recherche si necessaire
3 la tracabilite audit_log
4 verifier toujours les erreurs de syntaxe



je veux que tu implemente dans rhBackFast le module PasswordResetOTP  qui se trouve dans  le workspace audit_odecaBack plus precisement dans  gestionUtilisateur/modules/PasswordResetOTP
consignes:
1 analyser le module
2 respecter la logique
3 decouper le fichier de service {exemple dans conge_app}
4 verifier les erreurs de syntaxe



fais moi un portofolio sur base de l'image que je viens de te partager / nom:mushota raphael ,email:mushota09@gmail.com,github:https://github.com/mushota09/, linkdin:www.linkedin.com/in/raph-mushota-ab8925378,ma_photo:https://drive.google.com/file/d/11b0ktr8i4tsXWsqVOyYfMGGCg7jIJJHu/view?usp=sharing , mes competences: ## MES COMPÉTENCES TECHNIQUES ### 🔹 Backend & API - **Django & Django REST Framework** – APIs performantes et sécurisées - **FastAPI** – Microservices et endpoints ultra rapides - **Node.js & Express** – Backend scalable et event-driven ### 🔹 Bases de données - **PostgreSQL** – Schémas normalisés, transactions ACID, optimisation de requêtes, multi-tenant - **MySQL** – Applications CRUD haute performance, réplication et contraintes relationnelles - **MongoDB** – Modélisation document, agrégations complexes, stockage flexible JSON ### 🔹 Caching & Messaging - **Redis** – Cache API, rate limiting, session store, pub/sub, file d’attente légère - **Kafka** – Communication événementielle entre microservices, event-driven architecture ### 🔹 Architecture & Design - Microservices et monolithe modulaire - Event-driven architecture & async processing - Multi-tenancy et isolation de données - RBAC & JWT Auth - Conception d’APIs performantes et scalables ### 🔹 DevOps & Deployment - **Docker & Docker Compose** - **Nginx** – Reverse proxy et load balancing - CI/CD (GitHub Actions, GitLab CI) - Monitoring & logging structuré - Linux server management.


https://rhbackfast.onrender.com/docs

## 🧪 Mock data (développement)

Un script reproductible est disponible pour seeder une base de dev avec des données réalistes (services, postes, employés, contrats, congés, paie).

### Pré-requis

```bash
uv run alembic upgrade head          # applique les migrations (crée les tables cg_*, paie_*, etc.)
uv run python create_permissions.py  # (optionnel) crée les permissions RBAC de référence
```

### Exécution

```bash
uv run python -m scripts.seed_mock_data            # insert / upsert idempotent
uv run python -m scripts.seed_mock_data --reset    # supprime les lignes mock puis réinsère
uv run python -m scripts.seed_mock_data --quiet    # sans les logs intermédiaires
```

### Contenu seedé

- **6 services / 4 groupes / 12 postes** (Direction, RH, IT, Finance, Opérations, Commercial)
- **18 employés + comptes utilisateurs** avec hiérarchie à 2 niveaux (boss → managers → employés)
- **Mot de passe par défaut pour tous les comptes** : `rapha12345678`
- **Contrats actifs** (CDI / CDD / STAGE) avec salaire réaliste + indemnités en CDF
- **Soldes de congé** pour chaque type (CA, CM, CSS) de l'année courante
- **5 demandes de congé** couvrant les 5 statuts du workflow (`EN_ATTENTE`, `EN_COURS`, `VALIDE`, `REJETE`, `ANNULE`)
- **2 périodes de paie** : mois précédent déjà `PAID` (workflow complet) + mois courant `DRAFT`
- **1 entrée de paie par employé et par période**, retenues et alertes d'exemple

Le script est **idempotent** : les doublons sont évités grâce aux clefs naturelles (`email`, `matricule`, `(annee, mois)`, `(employe_id, type_conge_id, annee)`…). Relancer le script ne duplique jamais de lignes.

> ⚠️ Le mot de passe `rapha12345678` n'est acceptable qu'en environnement de développement. À ne jamais utiliser en production.

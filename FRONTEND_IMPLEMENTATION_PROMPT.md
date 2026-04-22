# 🎯 PROMPT COMPLET POUR IMPLÉMENTER LE FRONTEND DE rhBackFast

Tu dois créer un frontend React TypeScript moderne et professionnel pour **rhBackFast**, un système complet de gestion des ressources humaines. Le backend FastAPI est déjà déployé et accessible sur `https://rhbackfast.onrender.com/docs`.

## ⚠️ CONTEXTE CRITIQUE

Le frontend possède des **anciens codes pour les modules congé et paie**, mais le backend a été **complètement refactorisé** avec un système de **workflow dynamique**. Tu dois **adapter ou réécrire entièrement** ces parties pour correspondre à la nouvelle architecture backend.

---

## 📋 ARCHITECTURE BACKEND (Version Actuelle)

### 🔐 Authentification & Sécurité

**Système JWT** :
- Access token : 30 minutes
- Refresh token : 7 jours
- Endpoint login : `POST /api/auth/login` → retourne `{access, refresh, user}`
- Endpoint refresh : `POST /api/auth/refresh` → retourne `{access_token}`
- Header requis : `Authorization: Bearer {token}`

**Mot de passe par défaut des données de test** : `rapha12345678`

### 🌐 Fonctionnalités Transversales

**Système d'expansion** (évite les requêtes N+1) :
```
?expand=relation1,relation2.nested
Exemple : ?expand=poste.service,poste.group,contrats
```

**Pagination** :
```
?skip=0&limit=100
ou ?no_pagination=true
Réponse : {results: [], total: int, skip: int, limit: int}
```

**Recherche** :
```
?search=terme
```

**Tri** :
```
?ordering=nom (ascendant)
?ordering=-nom (descendant)
```

---

## 📦 MODULE 1 : USER_APP (Gestion Utilisateurs & RBAC)

### Endpoints Principaux

**Authentification** :
- `POST /api/auth/login` - Connexion
- `POST /api/auth/refresh` - Rafraîchir token
- `POST /api/auth/logout` - Déconnexion

**Services** :
- `GET /api/services` - Liste des services/départements
- `POST /api/services` - Créer service
- `GET /api/services/{id}` - Détail service
- `PUT /api/services/{id}` - Modifier service
- `DELETE /api/services/{id}` - Supprimer service

**Groupes (Rôles)** :
- `GET /api/groups` - Liste des groupes
- `POST /api/groups` - Créer groupe
- `GET /api/groups/{id}` - Détail groupe
- `PUT /api/groups/{id}` - Modifier groupe
- `DELETE /api/groups/{id}` - Supprimer groupe

**Postes (ServiceGroup)** :
- `GET /api/service-groups` - Liste des postes
- `POST /api/service-groups` - Créer poste
- `GET /api/service-groups/{id}` - Détail poste
- `PUT /api/service-groups/{id}` - Modifier poste
- `DELETE /api/service-groups/{id}` - Supprimer poste

**Employés** :
- `GET /api/employees` - Liste avec filtres
- `POST /api/employees` - Créer employé simple
- `POST /api/employees/with-user` - Créer employé + compte utilisateur
- `POST /api/employees/create-complete` - Créer employé complet (FormData : employé + contrat + documents + user)
- `GET /api/employees/{id}` - Détail employé
- `PUT /api/employees/{id}` - Modifier employé
- `DELETE /api/employees/{id}` - Supprimer employé

**Permissions** :
- `GET /api/permissions` - Liste des permissions
- `GET /api/group-permissions` - Permissions par groupe
- `POST /api/group-permissions` - Assigner permission à groupe

### Modèles Clés

**Employe** : Informations personnelles (nom, prénom, date naissance, sexe, statut matrimonial, nationalité), professionnelles (poste, responsable, date embauche, statut emploi), coordonnées (emails, téléphones, adresse), bancaires (banque, compte, INSS), familiales (nombre enfants, conjoint), contact urgence.

**Contrat** : Type (CDI/CDD/STAGE), dates, salaire de base, indemnités (logement, transport, déplacement, fonction), primes, avantages, cotisations (patronales et salariales : INSS, MFP, FPC).

**Document** : Type, titre, description, fichier, date upload, date expiration.

---

## 📦 MODULE 2 : CONGE_APP (Gestion Congés avec Workflow Dynamique)

### ⚠️ CHANGEMENTS MAJEURS vs Ancienne Version

1. **Workflow dynamique** : Étapes, actions et statuts configurables en base de données
2. **Support demi-journées** : `demi_journee_debut` et `demi_journee_fin` (valeurs : "matin" ou "apres-midi")
3. **Multi-pays** : Jours fériés via bibliothèque Python `holidays`
4. **Attributions polymorphiques** : Système de validation multi-niveaux avec prise en charge
5. **Historique complet** : Traçabilité de toutes les actions du workflow

### Endpoints Workflow

**Types de congé** :
- `GET /api/conge/types` - Liste des types (CA, CM, CSS, etc.)
- `POST /api/conge/types` - Créer type
- `PATCH /api/conge/types/{id}` - Modifier type
- `DELETE /api/conge/types/{id}` - Supprimer type

**Soldes** :
- `GET /api/conge/soldes/me` - Mes soldes (employé connecté)
- `GET /api/conge/soldes` - Tous les soldes (admin) avec filtres `?employe_id=X&annee=Y&type_conge_id=Z`
- `POST /api/conge/soldes` - Créer/Modifier solde (upsert)

**Configuration Workflow** (Admin uniquement) :
- `GET /api/conge/workflow/statuts` - Liste des statuts (EN_ATTENTE, EN_COURS, VALIDE, REJETE, ANNULE)
- `POST /api/conge/workflow/statuts` - Créer statut
- `GET /api/conge/workflow/etapes?code_processus=CONGE` - Liste des étapes du processus CONGE
- `POST /api/conge/workflow/etapes` - Créer étape
- `PATCH /api/conge/workflow/etapes/{id}` - Modifier étape
- `DELETE /api/conge/workflow/etapes/{id}` - Supprimer étape
- `GET /api/conge/workflow/actions?etape_id=X` - Liste des actions d'une étape
- `POST /api/conge/workflow/actions` - Créer action
- `PATCH /api/conge/workflow/actions/{id}` - Modifier action
- `DELETE /api/conge/workflow/actions/{id}` - Supprimer action

**Demandes de congé** :
- `POST /api/conge/demandes` - Créer demande
- `GET /api/conge/demandes?mode=mine|a_valider|all` - Liste des demandes
  - `mode=mine` : Mes demandes
  - `mode=a_valider` : Demandes à valider (assignées à moi)
  - `mode=all` : Toutes les demandes (superuser uniquement)
- `GET /api/conge/demandes/{id}` - Détail avec historique et attributions
- `GET /api/conge/demandes/{id}/actions` - Actions possibles pour l'étape courante
- `POST /api/conge/demandes/{id}/prendre-en-charge` - Prendre en charge la validation
- `POST /api/conge/demandes/{id}/valider` - Appliquer une action (body: `{action_id, commentaire?}`)

### Structure DemandeConge

```json
{
  "id": 1,
  "employe_id": 5,
  "type_conge_id": 1,
  "date_debut": "2024-06-01",
  "demi_journee_debut": "matin",
  "date_fin": "2024-06-03",
  "demi_journee_fin": "apres-midi",
  "nb_jours_ouvres": 2.5,
  "etape_courante_id": 2,
  "responsable_id": 3,
  "statut_global_id": 1,
  "date_soumission": "2024-05-25T10:00:00",
  "date_decision_finale": null
}
```

### Workflow - Flux de Validation

1. **Créer demande** : `POST /api/conge/demandes` → Statut initial `EN_ATTENTE`, première étape assignée
2. **Récupérer actions possibles** : `GET /api/conge/demandes/{id}/actions` → Retourne `{etape_courante_id, is_valideur, actions: [...]}`
3. **Prendre en charge** (si poste partagé) : `POST /api/conge/demandes/{id}/prendre-en-charge`
4. **Appliquer action** : `POST /api/conge/demandes/{id}/valider` avec `{action_id: 1, commentaire: "Approuvé"}`
5. **Consulter historique** : Inclus dans `GET /api/conge/demandes/{id}` avec `?expand=historique,attributions`

---

## 📦 MODULE 3 : PAIE_APP (Gestion Paie avec Workflow)

### ⚠️ CHANGEMENTS MAJEURS vs Ancienne Version

1. **Workflow dynamique** : Même système que congés (tables partagées)
2. **Calculs automatiques** : Salaire brut, cotisations (INSS, MFP, FPC), IRE, retenues, net
3. **Bulletins PDF** : Génération automatique avec ReportLab
4. **Statistiques avancées** : Endpoints dédiés pour tableaux de bord
5. **Historique des modifications** : Traçabilité complète avec raisons
6. **Notifications email** : Automatiques (si activées)

### Endpoints Principaux

**Périodes de paie** :
- `GET /api/paie/periodes` - Liste avec filtres `?annee=2024&mois=1`
- `POST /api/paie/periodes` - Créer période
- `GET /api/paie/periodes/{id}` - Détail période
- `POST /api/paie/periodes/{id}/process` - Traiter (calculer tous les salaires)
- `POST /api/paie/periodes/{id}/finalize` - Finaliser
- `POST /api/paie/periodes/{id}/approve` - Approuver (ancien système)

**Workflow Paie** (Nouveau) :
- `POST /api/paie/periodes/{id}/submit` - Soumettre au workflow (body: `{responsable_id?}`)
- `GET /api/paie/periodes/{id}/actions` - Actions possibles
- `POST /api/paie/periodes/{id}/prendre-en-charge` - Prendre en charge
- `POST /api/paie/periodes/{id}/valider` - Appliquer action (body: `{action_id, commentaire?}`)
- `GET /api/paie/periodes/{id}/historique` - Historique workflow
- `GET /api/paie/periodes/{id}/attributions` - Attributions courantes
- `GET /api/paie/periodes/config/etapes` - Configuration workflow PAIE

**Entrées de paie** :
- `GET /api/paie/entrees?periode_id=X` - Liste des entrées
- `GET /api/paie/entrees/{id}` - Détail entrée
- `POST /api/paie/entrees/{id}/calculate` - Recalculer salaire

**Bulletins de paie PDF** :
- `POST /api/paie/payroll/entrees/{id}/generate-payslip` - Générer bulletin
- `GET /api/paie/payroll/entrees/{id}/download-payslip` - Télécharger bulletin
- `POST /api/paie/payroll/periodes/{id}/generate-all-payslips` - Générer tous les bulletins

**Retenues salariales** :
- `GET /api/paie/retenues?employe_id=X` - Liste des retenues
- `POST /api/paie/retenues` - Créer retenue

**Alertes** :
- `GET /api/paie/alerts` - Liste des alertes
- `POST /api/paie/alerts` - Créer alerte

**Statistiques** (Nouveau) :
- `GET /api/paie/statistics/periode/{id}/summary` - Résumé période
- `GET /api/paie/statistics/annual/{annee}/summary` - Résumé annuel
- `GET /api/paie/statistics/employee/{id}/history` - Historique employé
- `GET /api/paie/statistics/dashboard` - Dashboard complet

**Export** :
- `GET /api/paie/payroll/export/periode/{id}?export_format=excel|csv` - Exporter période
- `GET /api/paie/payroll/export/all-periodes?annee=2024` - Exporter toutes les périodes

### Calculs Salariaux (Automatiques)

**Salaire brut** = Base + Indemnités + Allocations familiales + Avantages

**Cotisations patronales** :
- INSS pension : 6% (plafonné 27 000 FC)
- INSS risques : 6% (plafonné 2 400 FC)
- MFP, FPC : % configurables

**Cotisations salariales** :
- INSS : 4% (plafonné 18 000 FC)
- MFP, FPC : % configurables

**IRE (Impôt)** - Tranches :
- 0 - 150 000 FC : 0%
- 150 000 - 300 000 FC : 20%
- > 300 000 FC : 30%

**Salaire net** = Brut - Cotisations salariales - IRE - Retenues

---

## 📦 MODULE 4 : AUDIT_APP

- `GET /api/audit/logs` - Liste avec filtres `?user_id=X&action=CREATE&resource_type=EMPLOYE`

---

## 📦 MODULE 5 : RESET_PASSWORD_APP

- `POST /api/password-reset/request-otp` - Demander OTP (body: `{email}`)
- `POST /api/password-reset/verify-otp` - Vérifier OTP (body: `{email, otp}`)
- `POST /api/password-reset/reset-password` - Changer mot de passe (body: `{email, otp, new_password}`)

**Flux** : Email → OTP (6 chiffres, 10 min) → Nouveau mot de passe

---

## 🎨 SPÉCIFICATIONS FRONTEND

### 🛠️ Stack Technique Obligatoire

- **Framework** : React 18+ avec TypeScript
- **Build Tool** : Vite
- **Styling** : Tailwind CSS (ou Material-UI)
- **State Management** : Zustand ou Redux Toolkit
- **Data Fetching** : TanStack Query (React Query) - **Obligatoire**
- **Forms** : React Hook Form + Zod
- **Routing** : React Router v6
- **Tables** : TanStack Table
- **Dates** : date-fns ou Day.js
- **Charts** : Recharts ou Chart.js
- **Notifications** : React Hot Toast
- **HTTP Client** : Axios avec intercepteurs

### 📁 Structure du Projet

```
frontend/
├── src/
│   ├── api/                      # Clients API
│   │   ├── axios.ts             # Config Axios + intercepteurs
│   │   ├── auth.api.ts
│   │   ├── employee.api.ts
│   │   ├── conge.api.ts         # ⚠️ À ADAPTER
│   │   ├── paie.api.ts          # ⚠️ À ADAPTER
│   │   └── audit.api.ts
│   ├── components/
│   │   ├── common/              # Composants réutilisables
│   │   ├── layout/              # Layout (Sidebar, Header)
│   │   ├── forms/               # Formulaires
│   │   └── workflow/            # ⚠️ NOUVEAU
│   │       ├── WorkflowTimeline.tsx
│   │       ├── WorkflowActions.tsx
│   │       └── WorkflowStatus.tsx
│   ├── features/                # Features par module
│   │   ├── auth/
│   │   ├── dashboard/
│   │   ├── employees/
│   │   ├── conges/              # ⚠️ À REFACTORISER
│   │   ├── paie/                # ⚠️ À REFACTORISER
│   │   └── admin/
│   ├── hooks/                   # Hooks personnalisés
│   ├── types/                   # Types TypeScript
│   │   ├── workflow.types.ts   # ⚠️ NOUVEAU
│   │   ├── conge.types.ts      # ⚠️ À METTRE À JOUR
│   │   └── paie.types.ts       # ⚠️ À METTRE À JOUR
│   ├── utils/                   # Utilitaires
│   └── App.tsx
```

---

## 🎯 FONCTIONNALITÉS À IMPLÉMENTER

### 1. AUTHENTIFICATION

**Login** (`/login`) :
- Formulaire email + mot de passe
- Stockage tokens (localStorage)
- Redirection après connexion

**Réinitialisation** (`/reset-password`) :
- Étape 1 : Email → OTP
- Étape 2 : Saisie OTP
- Étape 3 : Nouveau mot de passe

**Gestion tokens** :
- Intercepteur Axios
- Refresh automatique si 401

### 2. DASHBOARD

- Statistiques clés
- Graphiques
- Widgets
- Accès rapides

### 3. GESTION EMPLOYÉS

**Liste** (`/employees`) :
- Table avec filtres, recherche, pagination
- Expansion : `?expand=poste.service,poste.group`

**Détail** (`/employees/:id`) :
- Onglets : Perso, Pro, Coordonnées, Bancaires, Contrats, Documents, Congés, Paie

**Création** (`/employees/create`) :
- Formulaire multi-étapes
- Endpoint : `POST /api/employees/create-complete` (FormData)

### 4. GESTION CONGÉS ⚠️ À REFACTORISER

**Liste** (`/conges`) :
- Vues : `?mode=mine|a_valider|all`
- Expansion : `?expand=type_conge,etape_courante,statut_global`

**Détail** (`/conges/:id`) ⚠️ NOUVEAU :
- **Timeline workflow** (composant `WorkflowTimeline`)
- **Actions possibles** (composant `WorkflowActions`)

**Création** (`/conges/create`) ⚠️ AJOUTER :
- **Checkboxes demi-journées** (matin/après-midi)
- **Calcul automatique jours ouvrés**

**Validation** :
1. `POST /api/conge/demandes/{id}/prendre-en-charge`
2. `POST /api/conge/demandes/{id}/valider` avec `{action_id, commentaire}`

**Configuration workflow** (`/admin/workflow/conge`) :
- Gérer statuts, étapes, actions

### 5. GESTION PAIE ⚠️ À REFACTORISER

**Liste périodes** (`/paie/periodes`) :
- Filtres : année, mois, statut

**Détail période** (`/paie/periodes/:id`) ⚠️ AJOUTER :
- **Onglet Workflow** (NOUVEAU) :
  - Timeline : `GET /api/paie/periodes/{id}/historique`
  - Actions : `GET /api/paie/periodes/{id}/actions`
- **Onglet Statistiques** : `GET /api/paie/statistics/periode/{id}/summary`

**Actions workflow** :
- Soumettre : `POST /api/paie/periodes/{id}/submit`
- Valider : `POST /api/paie/periodes/{id}/valider`

**Bulletins PDF** :
- Générer : `POST /api/paie/payroll/entrees/{id}/generate-payslip`
- Télécharger : `GET /api/paie/payroll/entrees/{id}/download-payslip`

**Statistiques** ⚠️ NOUVEAU :
- Dashboard : `GET /api/paie/statistics/dashboard`
- Analyses : `GET /api/paie/statistics/comparative/{annee}/{mois}`

---

## 🔧 COMPOSANTS WORKFLOW (À CRÉER)

### WorkflowTimeline.tsx

```typescript
interface WorkflowTimelineProps {
  historique: HistoriqueItem[];
  etapeCourante?: EtapeProcessus;
  statutGlobal?: StatutProcessus;
}
```

Affiche timeline verticale des actions passées avec valideur, action, commentaire, date.

### WorkflowActions.tsx

```typescript
interface WorkflowActionsProps {
  demandeId: number;
  isValideur: boolean;
  actions: ActionEtape[];
  onAction: (actionId: number, commentaire?: string) => void;
}
```

Affiche boutons d'actions possibles avec modal pour commentaire.

### WorkflowStatus.tsx

```typescript
interface WorkflowStatusProps {
  statut: StatutProcessus;
  size?: 'sm' | 'md' | 'lg';
}
```

Badge coloré selon statut (EN_ATTENTE=jaune, EN_COURS=bleu, VALIDE=vert, REJETE=rouge).

---

## 📝 TYPES TYPESCRIPT CRITIQUES

### Workflow (NOUVEAU)

```typescript
interface StatutProcessus {
  id: number;
  code_statut: string;
  created_at: string;
  updated_at: string;
}

interface EtapeProcessus {
  id: number;
  code_processus: string;
  ordre: number;
  nom_etape: string;
  poste_id?: number;
  is_responsable: boolean;
}

interface ActionEtapeProcessus {
  id: number;
  etape_id: number;
  nom_action: string;
  statut_cible_id: number;
  etape_suivante_id?: number;
}

interface HistoriqueDemande {
  id: number;
  demande_type: string;
  demande_id: number;
  etape_id: number;
  action_id: number;
  nouveau_statut_id: number;
  valideur_id: number;
  commentaire?: string;
  created_at: string;
}

interface DemandeAttribution {
  id: number;
  demande_type: string;
  demande_id: number;
  etape_id: number;
  valideur_attribue_id: number;
  statut: "en_attente" | "prise_en_charge" | "traitee";
}
```

### Congés (MIS À JOUR)

```typescript
interface DemandeConge {
  id: number;
  employe_id: number;
  type_conge_id: number;
  date_debut: string;
  demi_journee_debut?: "matin" | "apres-midi";  // ⚠️ NOUVEAU
  date_fin: string;
  demi_journee_fin?: "matin" | "apres-midi";    // ⚠️ NOUVEAU
  nb_jours_ouvres: number;
  etape_courante_id: number;    // ⚠️ WORKFLOW
  responsable_id?: number;
  statut_global_id: number;     // ⚠️ WORKFLOW
  date_soumission: string;
  date_decision_finale?: string;
}
```

### Paie (MIS À JOUR)

```typescript
interface PeriodePaie {
  id: number;
  annee: number;
  mois: number;
  statut: string;

  // ⚠️ WORKFLOW (nouveau)
  etape_courante_id?: number;
  statut_global_id?: number;
  responsable_id?: number;
  date_soumission?: string;
  date_decision_finale?: string;

  // Stats
  nombre_employes: number;
  masse_salariale_brute: number;
  total_net_a_payer: number;
}
```

---

## 🚀 INSTRUCTIONS D'IMPLÉMENTATION

### Configuration Axios

```typescript
// src/api/axios.ts
import axios from 'axios';

const api = axios.create({
  baseURL: 'https://rhbackfast.onrender.com',
});

// Intercepteur requête : ajouter token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Intercepteur réponse : refresh si 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const { data } = await axios.post('/api/auth/refresh', {
            refresh_token: refreshToken
          });
          localStorage.setItem('access_token', data.access_token);
          error.config.headers.Authorization = `Bearer ${data.access_token}`;
          return api.request(error.config);
        } catch {
          localStorage.clear();
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  }
);

export default api;
```

---

## ✅ CHECKLIST DE VALIDATION

### Congés
- [ ] Formulaire avec demi-journées
- [ ] Calcul automatique jours ouvrés
- [ ] Timeline workflow
- [ ] Actions workflow (prendre en charge, approuver, rejeter)
- [ ] Historique complet
- [ ] Filtres par mode (mine, a_valider, all)

### Paie
- [ ] Workflow paie (submit, actions, historique)
- [ ] Statistiques avancées
- [ ] Génération bulletins PDF
- [ ] Export Excel/CSV
- [ ] Onglet workflow dans détail période

### Général
- [ ] Authentification JWT avec refresh
- [ ] Système d'expansion
- [ ] Pagination
- [ ] Recherche
- [ ] Permissions
- [ ] Notifications
- [ ] Responsive design

---

## 🎨 DESIGN & UX

- Interface moderne et professionnelle
- Responsive (mobile, tablet, desktop)
- Dark mode (optionnel)
- Animations fluides
- Feedback utilisateur (loading, success, error)
- Accessibilité (WCAG AA)

---

## 📚 DOCUMENTATION À FOURNIR

- README.md avec instructions d'installation
- Guide d'utilisation des composants workflow
- Documentation des types TypeScript
- Exemples d'utilisation des hooks
- Guide de déploiement

---

**BON COURAGE ! 🚀**

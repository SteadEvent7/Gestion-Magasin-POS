# Application Desktop Gestion Magasin (POS Code-barres)

Application desktop Python pour la gestion complete d'un magasin: ventes, facturation, stock, approvisionnement, fournisseurs, clients, rapports et utilisateurs.

Voir aussi:
- `LISEZ_MOI.md`: guide complet d'installation, migration SQLite -> MySQL et exploitation.
- `COPYRIGHT.md`: droits d'auteur et conditions d'utilisation.

## Stack technique

- Desktop UI: `Tkinter` (Python)
- Backend applicatif: `Python`
- Base de donnees: `SQLite` par defaut (embarquee), `MySQL` en option
- Exports: `PDF` (factures/rapports) et `CSV` (Excel)

## Fonctionnalites implementees (MVP)

- Authentification avec roles (`Administrateur`, `Caissier`, `Gestionnaire`)
- Journal d'activite (audit)
- Tableau de bord (CA jour, nb ventes, stock faible, top produits)
- Gestion des categories et produits (CRUD)
- Generation automatique de code-barres numerique
- Vente POS avec lecture code-barres (scanner clavier), remise, TVA, mode de paiement
- Facturation + export PDF
- Historique ventes + retours produits
- Suivi stock en temps reel + mouvements
- Approvisionnement fournisseur avec mise a jour automatique du stock
- Gestion fournisseurs et clients
- Rapports des ventes + resume financier + export PDF/CSV
- Gestion utilisateurs (admin)
- Sauvegarde manuelle JSON

## Fonctionnalites avancees ajoutees

- Permissions fines par role sur actions critiques
- Securite compte: politique mot de passe + verrouillage temporaire apres echecs
- Changement de mot de passe utilisateur
- Multi-magasin / multi-caisse (selection contexte actif)
- Ticket thermique 80mm en PDF apres chaque vente
- Import/Export Excel produits
- Export Excel avance des rapports (multi-feuilles)
- Restauration complete depuis sauvegarde JSON
- Alertes stock critiques au demarrage
- Script de build executable Windows (`build_exe.ps1`)

## Correctif 1.0.2

- SQLite actif par defaut (installation client simplifiee, sans serveur externe obligatoire).
- Creation automatique de la base SQLite au premier lancement.
- Correctif de resolution du chemin SQLite quand `SQLITE_DB_PATH` est vide.
- Compatibilite MySQL maintenue en mode optionnel (`DB_ENGINE=mysql`).

## Prerequis

- Windows avec Python 3.10+
- Aucun serveur BD requis en mode par defaut (`SQLite`)
- Optionnel: MySQL/XAMPP uniquement si vous choisissez `DB_ENGINE=mysql`

## Installation

1. Copier `.env.example` vers `.env` et adapter les valeurs:

```env
DB_ENGINE=sqlite
SQLITE_DB_PATH=
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=gestion_magasin
APP_TITLE=Gestion Magasin POS
```

Notes:
- Si `DB_ENGINE=sqlite`, l'application cree automatiquement la base locale au premier lancement.
- `SQLITE_DB_PATH` vide = chemin auto dans le dossier de donnees de l'application.
- Pour MySQL, definir `DB_ENGINE=mysql` puis renseigner `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME`.

2. Installer les dependances:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

3. Initialiser la base:

```powershell
.\.venv\Scripts\python.exe init_db.py
```

En mode SQLite, cette etape est optionnelle (la creation est automatique au premier demarrage).

4. Lancer l'application:

```powershell
.\.venv\Scripts\python.exe run.py
```

Avec l'installateur Windows, l'utilisateur peut choisir directement le moteur de base de donnees:
- `SQLite` (recommande, operationnel immediatement)
- `MySQL` (parametrage serveur, tentative d'installation auto via winget disponible)

## Build executable Windows (.exe)

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

Sortie: `dist/GestionMagasinPOS.exe`

## Mises a jour via GitHub

1. Creer un repository GitHub (ex: `vente2-updates`).

2. Ajouter le fichier `update.json` a la racine du repo:

```json
{
	"version": "1.0.1",
	"download_url": "https://github.com/SteadEvent7/Gestion-Magasin-POS/releases/download/v1.0.1/GestionMagasinPOS.exe",
	"notes": "Correctifs mineurs et optimisation demarrage."
}
```

3. Configurer l'application pour lire ce manifeste:

```env
APP_UPDATE_URL=https://raw.githubusercontent.com/SteadEvent7/Gestion-Magasin-POS/main/update.json
```

4. A chaque nouvelle version:
- Builder le nouvel exe (`dist/GestionMagasinPOS.exe`).
- Creer une GitHub Release avec un tag (ex: `v1.0.2`).
- Uploader `GestionMagasinPOS.exe` dans les assets de la release.
- Mettre a jour `update.json` (`version`, `download_url`, `notes`) et pousser sur GitHub.

5. Au prochain lancement client:
- L'app detecte la nouvelle version.
- L'utilisateur clique sur `Mettre a jour`.
- Telechargement auto vers dossier temporaire.
- Updater externe remplace l'exe puis relance l'application.

## Compte par defaut

- Utilisateur: `admin`
- Mot de passe: `admin123`

## Structure du projet

- `schema_mysql.sql`: schema complet MySQL
- `init_db.py`: initialisation base
- `run.py`: point d'entree
- `app/config.py`: configuration
- `app/db.py`: acces base
- `app/security.py`: hash des mots de passe
- `app/services.py`: logique metier
- `app/main.py`: interface desktop

## Notes

- Le scanner code-barres est supporte via saisie clavier (mode HID classique).
- La restauration automatique complete est activee depuis l'onglet Parametres.
- Un ticket thermique 80mm PDF est genere apres chaque vente.

## Fonctionnement detaille du logiciel

1. Demarrage:
- Charge l'application.
- Initialise automatiquement la base locale SQLite si absente (`DB_ENGINE=sqlite`).
- Verifie l'integrite des donnees (coherence de base, stocks negatifs, orphelins).
- Cree une sauvegarde automatique journaliere si absente.
- Verifie la disponibilite d'une mise a jour distante si `APP_UPDATE_URL` est defini.
- Affiche la fenetre de connexion.

2. Authentification et roles:
- Connexion par nom d'utilisateur / mot de passe.
- Verrouillage temporaire apres echecs repetes.
- Redirection initiale par role: admin -> dashboard, gestionnaire -> stock, caissier -> POS.
- Permissions fines appliquees sur chaque action.

3. Dashboard:
- CA du jour, nombre de ventes, stock faible, top produits.
- Statistiques mensuelles via diagrammes et classements.

4. Produits et stock:
- CRUD produits/categorie, recherche, code-barres auto.
- Mouvements stock en temps reel (vente, approvisionnement, retour).
- Alertes stock faible au demarrage.

5. Approvisionnement:
- Saisie commande/reception fournisseur.
- Maj automatique du stock et des couts.

6. POS et facturation:
- Scan code-barres, panier, remise, TVA, paiement.
- Maj auto du stock apres validation.
- Generation facture PDF + ticket thermique 80mm.

7. Clients, rapports, sauvegardes:
- Gestion clients et historique.
- Rapports ventes/stock/finance en PDF, CSV et Excel.
- Sauvegarde et restauration complete JSON.

8. Architecture:
- Interface Tkinter.
- Logique metier Python.
- SQLite par defaut pour la persistence locale, MySQL en option.

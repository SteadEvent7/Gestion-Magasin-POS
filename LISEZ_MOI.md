# LISEZ-MOI - Gestion Magasin POS v1.0.2

Ce document explique:
- les nouveautes de la version 1.0.2,
- l'installation complete chez un client,
- le passage de SQLite vers MySQL,
- les bonnes pratiques de deploiement.

## 1. Nouveautes de la version 1.0.2

- Base de donnees SQLite activee par defaut.
- Creation automatique de la base locale au premier demarrage.
- Compatibilite MySQL conservee (mode optionnel).
- Correctif sur la gestion du chemin `SQLITE_DB_PATH` vide.

## 2. Installation rapide client (recommandee)

Mode recommande: SQLite (aucun MySQL a installer).

### Prerequis

- Windows 10 ou 11
- 4 Go RAM minimum
- 500 Mo espace disque libre

### Etapes

1. Lancer `Setup_GestionMagasinPOS.exe`.
2. Dans l'installateur, choisir le moteur de base de donnees:
   - `SQLite` (recommande, pret a l'emploi), ou
   - `MySQL` (mode serveur/multi-postes).
3. Si `MySQL` est choisi:
   - renseigner les parametres de connexion,
   - optionnellement cocher l'installation automatique MySQL via winget (internet requis).
4. Terminer l'installation.
5. Demarrer l'application.
6. Se connecter avec:
   - Utilisateur: `admin`
   - Mot de passe: `admin123`
7. Changer le mot de passe administrateur immediatement.

### Configuration par defaut (.env)

```env
DB_ENGINE=sqlite
SQLITE_DB_PATH=
APP_TITLE=Gestion Magasin POS
APP_VERSION=1.0.2
APP_UPDATE_URL=https://raw.githubusercontent.com/SteadEvent7/Gestion-Magasin-POS/main/update.json
```

Notes:
- `SQLITE_DB_PATH` vide = chemin auto gere par l'application.
- Si l'application est installee en mode systeme, les donnees sont stockees dans un dossier de donnees accessible en ecriture.

## 3. Installation en mode MySQL (optionnel)

Choisir ce mode uniquement pour un usage multi-postes ou une architecture client/serveur.

### Prerequis MySQL

- MySQL Server 8.x ou MariaDB 10.x
- Base accessible depuis le poste applicatif
- Port 3306 ouvert (ou port personnalise)

### Etapes

1. Installer MySQL/MariaDB.
2. Creer la base `gestion_magasin`.
3. Initialiser le schema:
   - via `init_db.py`, ou
   - via import SQL.
4. Configurer `.env`:

```env
DB_ENGINE=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=gestion_magasin
APP_TITLE=Gestion Magasin POS
APP_VERSION=1.0.2
APP_UPDATE_URL=https://raw.githubusercontent.com/SteadEvent7/Gestion-Magasin-POS/main/update.json
```

5. Lancer l'application.

## 4. Passage de SQLite vers MySQL (migration)

Objectif: conserver les donnees et passer en architecture serveur.

### Methode recommandee

1. Arreter l'application sur tous les postes.
2. Faire une sauvegarde JSON depuis l'application (ou utiliser le backup existant).
3. Configurer le `.env` en mode MySQL (`DB_ENGINE=mysql` + parametres DB).
4. Initialiser la base MySQL avec le schema.
5. Demarrer l'application avec MySQL.
6. Restaurer le backup JSON via l'onglet de restauration.
7. Verifier:
   - produits,
   - clients,
   - ventes,
   - stock,
   - utilisateurs.

### Checklist de validation apres migration

- Connexion admin OK
- Creation d'un produit test OK
- Vente test OK
- Rapport ventes OK
- Sauvegarde JSON OK

## 5. Mises a jour a distance

Le mecanisme de mise a jour reste identique en SQLite et MySQL.

Pour publier une nouvelle version:
1. Generer le nouvel exe.
2. Creer la release GitHub (ex: `v1.0.3`).
3. Uploader `GestionMagasinPOS.exe`.
4. Mettre a jour `update.json` (`version`, `patch`, `download_url`, `notes`).
5. Pousser `update.json` sur la branche principale.

Regle de detection:
- mise a jour proposee si `version` distante > version locale,
- ou si `version` distante = version locale et `patch` distant > patch local.

## 6. Support exploitation

En cas de probleme:
- verifier la connectivite reseau (si MySQL distant),
- verifier les droits d'ecriture du dossier de donnees,
- verifier le contenu de `.env`,
- verifier que la version de l'application et le manifest distant sont coherents.

# Steam Survival Tracker

Suivi quotidien automatisé des jeux Steam combinant **monde persistant + coop + PvP**.

![daily-update](https://github.com/USER/REPO/actions/workflows/daily-update.yml/badge.svg)
![deploy-pages](https://github.com/USER/REPO/actions/workflows/deploy-pages.yml/badge.svg)

🔗 **Voir l'app en live** : https://USER.github.io/REPO/

## 🏗️ Comment ça marche

```
┌────────────────────────────────────────────────────┐
│  GitHub Actions (cron quotidien 10h UTC)           │
│  └─> python ingest_steam.py                        │
│       ├─> Steam API (CCU live)                    │
│       └─> Twitch Helix API (viewers/streams)      │
│  └─> commit & push data/history.json              │
└────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────┐
│  GitHub Pages (déploiement auto à chaque push)     │
│  └─> https://USER.github.io/REPO/                  │
│  └─> index.html fetch data/history.json           │
└────────────────────────────────────────────────────┘
```

Aucun serveur à louer, aucune carte bancaire. Tout est gratuit pour usage perso.

## 📋 Setup en 5 étapes

### 1. Fork ou clone ce repo

Clone-le dans ton propre compte GitHub.

### 2. Crée une app Twitch (3 min)

Va sur [dev.twitch.tv/console/apps](https://dev.twitch.tv/console/apps), clique **Register Your Application** :
- Name : `steam-survival-tracker` (n'importe quoi)
- OAuth Redirect URLs : `http://localhost`
- Category : **Application Integration**

Récupère :
- **Client ID** (visible directement)
- **Client Secret** (clique "New Secret" pour le générer)

### 3. Configure les secrets GitHub

Dans ton repo : **Settings** → **Secrets and variables** → **Actions** → **New repository secret** :

| Nom | Valeur |
|-----|--------|
| `TWITCH_CLIENT_ID` | Ton Client ID |
| `TWITCH_SECRET` | Ton Client Secret |

### 4. Active GitHub Actions

Va dans l'onglet **Actions** de ton repo et clique sur "I understand my workflows, go ahead and enable them".

### 5. Active GitHub Pages

**Settings** → **Pages** :
- Source : **GitHub Actions**

Le premier déploiement se fait automatiquement après le prochain push (ou lance manuellement le workflow "Deploy to GitHub Pages" depuis l'onglet Actions).

## 🚀 Lancer manuellement la première ingestion

Va dans **Actions** → **Daily Steam + Twitch ingestion** → **Run workflow** → **Run workflow**.

Ça lance immédiatement la collecte de données. Une fois terminé (1-2 minutes), `data/history.json` est mis à jour et l'app se redéploie automatiquement.

## 🛠️ Lancer en local (optionnel)

```bash
# Sans Twitch
python ingest_steam.py

# Avec Twitch
export TWITCH_CLIENT_ID=xxx
export TWITCH_SECRET=yyy
python ingest_steam.py
```

Pour visualiser localement, lance un serveur HTTP simple :
```bash
python -m http.server 8000
```
Puis ouvre http://localhost:8000.

## 📁 Structure

```
.
├── index.html              # L'app (React + Recharts via CDN)
├── ingest_steam.py         # Script de collecte (Steam + Twitch APIs)
├── data/
│   ├── history.json        # Historique cumulé (mis à jour quotidiennement)
│   ├── games_meta.json     # Métadonnées Steam (prix, reviews) - hebdo
│   ├── twitch_game_ids.json # Cache des IDs Twitch
│   └── snapshot_*.json     # Archives quotidiennes
└── .github/workflows/
    ├── daily-update.yml    # Cron quotidien d'ingestion
    └── deploy-pages.yml    # Déploiement auto sur Pages
```

## 🎯 Personnaliser

### Ajouter / retirer des jeux

Édite la constante `GAMES` dans `ingest_steam.py` :
```python
GAMES = {
    252490: ("Rust", "Rust"),
    # ajouter ici: appid: (nom Steam, nom Twitch)
}
```

Édite aussi la constante `GAMES` dans `index.html` (avec les métadonnées : PvP, persistant, etc.).

### Changer l'heure d'exécution

Édite `.github/workflows/daily-update.yml`, ligne `cron`. Format : `'minute heure jour mois jour_de_la_semaine'` en UTC.

## 📊 Données collectées

Pour chaque jeu, chaque jour :
- **CCU Steam** : joueurs simultanés (instantané)
- **Viewers Twitch** : somme des viewers sur tous les streams live
- **Channels Twitch** : nombre de streams live

Et hebdomadairement :
- Prix Steam (avec promo si en cours)
- % positif des reviews + nombre total
- Date de sortie, dev, éditeur, genres, tags

## ❓ FAQ

**Q : Pourquoi pas de monitoring "all-time peak" ?**
L'API Steam ne le donne pas. Cette valeur reste maintenue manuellement dans `index.html` (elle bouge très rarement).

**Q : Les données risquent d'être perdues ?**
Non, tout est versionné dans Git. Tu peux remonter à n'importe quelle date via l'historique des commits.

**Q : Mon repo est privé, ça marche quand même ?**
GitHub Pages sur un repo privé nécessite GitHub Pro (4 $/mois). Sinon, mets le repo en public (les données collectées sont publiques de toute façon) ou utilise Cloudflare Pages.

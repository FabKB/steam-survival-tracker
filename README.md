# Steam Survival Tracker (v2 — pipeline horaire)

Suivi automatisé des jeux Steam combinant **monde persistant + coop + PvP**, avec :
- ⏱️ Collecte **toutes les heures** (24 points/jour)
- 📊 Peak CCU et peak Twitch viewers calculés sur 24h
- 🌍 Région primaire déduite (heure UTC + langue Twitch dominante)
- 📈 Sparklines basées sur les peaks journaliers (pas des instantanés)

🔗 **Voir l'app en live** : https://USER.github.io/REPO/

## 🆕 Nouveautés v2

### Avant (v1)
- 1 mesure/jour à 10h UTC = juste un instantané
- Pas de notion de "peak"
- Pas de signal géographique

### Maintenant (v2)
- 24 mesures/jour → peak CCU réel sur 24h
- Heure UTC du peak affichée (utile pour comprendre quelle zone géo pousse l'audience)
- Région primaire affichée (Europe / Amérique / Asie Est / Russie/CEI / etc.)
- Désambiguïsation par langue Twitch dominante au moment du peak

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────┐
│  GitHub Actions (cron horaire, HH:05 UTC)          │
│  └─> python ingest_steam.py                        │
│       ├─> Steam API : CCU live                    │
│       └─> Twitch Helix : viewers + langue         │
│  └─> commit & push                                │
│       ├─> data/hourly/YYYY-MM-DD.json (raw)       │
│       └─> data/daily_stats.json (peaks calculés)  │
└────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────┐
│  GitHub Pages (déploiement auto si data/ change)   │
│  └─> https://USER.github.io/REPO/                  │
│  └─> index.html fetch daily_stats.json            │
└────────────────────────────────────────────────────┘
```

## 📊 Structure des données

### `data/hourly/YYYY-MM-DD.json`
Snapshots horaires complets du jour :
```json
{
  "date": "2026-05-14",
  "snapshots": [
    {
      "hour_utc": 16,
      "timestamp": "2026-05-14T16:05:00+00:00",
      "games": [
        {
          "appid": 252490,
          "name": "Rust",
          "ccu": 95432,
          "twitch_viewers": 18432,
          "twitch_channels": 487,
          "viewers_by_lang": { "en": 12000, "fr": 2500, "ru": 2000, ... }
        }, ...
      ]
    }, ...
  ]
}
```

### `data/daily_stats.json`
Agrégat des peaks journaliers (1 entrée par jour x jeu) :
```json
{
  "2026-05-14": {
    "252490": {
      "peak_ccu": 105947,
      "peak_ccu_hour_utc": 20,
      "peak_twitch_viewers": 19432,
      "peak_twitch_hour_utc": 21,
      "region": {
        "code": "EU",
        "label": "🇪🇺 Europe",
        "emoji": "🇪🇺",
        "confidence": "high"
      },
      "samples": 24
    }
  }
}
```

## 🌍 Méthode de détection de la région

### Heuristique fuseau horaire
Pour chaque région, on définit la plage UTC où il est "19h local" (cœur du prime time gaming) :

| Région | UTC du peak local 19h | Plage UTC plausible |
|---|---|---|
| 🇺🇸 Amérique Ouest | 03h UTC | 00h-07h |
| 🇺🇸 Amérique Est | 00h UTC | 21h-04h |
| 🇧🇷 Amérique Latine | 22h UTC | 21h-03h |
| 🇪🇺 Europe | 18h UTC | 16h-22h |
| 🇷🇺 Russie/CEI | 16h UTC | 13h-19h |
| 🌍 Moyen-Orient | 16h UTC | 13h-19h |
| 🇨🇳 Asie Est | 11h UTC | 09h-15h |
| 🇸🇬 Asie SE | 12h UTC | 10h-16h |
| 🇦🇺 Océanie | 09h UTC | 06h-12h |

### Désambiguïsation par langue Twitch
Quand 2 régions sont plausibles à la même heure UTC (ex: Europe vs Russie à 16h),
on regarde la **langue dominante** des viewers Twitch au moment du peak.

| Langue dominante | Boost la région |
|---|---|
| ru, uk | Russie/CEI |
| zh, ko, ja | Asie Est |
| fr, de, it, pl | Europe |
| pt, es | Europe / LATAM (50/50) |
| en | Amérique + Europe (peu informatif seul) |

### Niveau de confiance
- **high** : 1 région clairement dominante
- **medium** : ambiguïté légère
- **low** : 2 régions affichées simultanément (l'app le marque visuellement)

## 📋 Setup

Voir `SETUP_v2.md` pour la migration depuis v1 ou un setup neuf.

## 🛠️ Lancer en local

```bash
export TWITCH_CLIENT_ID=xxx
export TWITCH_SECRET=yyy
python ingest_steam.py
```

Le script créera/mettra à jour :
- `data/hourly/YYYY-MM-DD.json` (snapshot de l'heure actuelle ajouté)
- `data/daily_stats.json` (peaks du jour recalculés)

Pour visualiser :
```bash
python -m http.server 8000
# → http://localhost:8000
```

## ❓ FAQ

**Q : Pourquoi le pipeline est-il horaire et pas par minute ?**
GitHub Actions Free Tier offre 2000 minutes/mois. Un run dure ~30 sec. 24 runs/jour = ~12 min/jour = 360 min/mois. Largement OK. Une fréquence plus haute consommerait trop pour peu de bénéfice (le CCU ne bouge pas vite).

**Q : Les peaks remontent à quand ?**
Avant la v2, on n'avait que des instantanés. Le repo contient un `daily_stats.json` initial simulé pour les 60 derniers jours, mais les vrais peaks ne commencent qu'à la première heure d'ingestion v2.

**Q : Peut-on changer l'heuristique de région ?**
Oui, c'est dans `infer_region()` et `LANG_TO_REGION` dans `ingest_steam.py`.

**Q : Que se passe-t-il si Twitch est down 1 heure ?**
Le snapshot horaire est quand même créé avec les CCU Steam, sans les viewers Twitch.
Au calcul du peak du jour, on prend les heures où les données sont dispo.

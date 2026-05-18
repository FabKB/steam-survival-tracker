# 🔄 Migration vers la v2 (pipeline horaire)

Tu as déjà la v1 qui tourne. Ce guide explique comment migrer vers la v2 **sans casser ton site**.

## ⚠️ Ce qui change

| Aspect | v1 | v2 |
|---|---|---|
| Fréquence | 1x/jour (10h UTC) | **24x/jour (toutes les heures)** |
| Donnée stockée | CCU instantané | CCU + Twitch + langue par heure |
| Fichier principal | `data/history.json` | `data/daily_stats.json` + `data/hourly/*.json` |
| Affichage du peak | Le CCU à 10h UTC | **Le vrai peak sur 24h** |
| Région affichée | ❌ | ✅ Inférée de l'heure + langue Twitch |
| Coût GitHub Actions | ~5 min/mois | ~360 min/mois (sur 2000 dispo) |

## 🚀 Migration en 3 étapes (~10 min)

### Étape 1 : Sauvegarde de la v1 (optionnel mais conseillé)

Sur GitHub, crée une **branche de sauvegarde** au cas où :

1. Va sur ton repo
2. Cliquer sur le sélecteur de branche (en haut, "main")
3. Taper `backup-v1` dans le champ
4. Cliquer **Create branch: backup-v1 from main**

Tu peux toujours revenir en arrière avec `git checkout backup-v1` (ou via l'interface).

### Étape 2 : Upload des fichiers v2

**Trois fichiers à remplacer / créer** :

| Fichier | Action |
|---|---|
| `ingest_steam.py` | **Remplacer** par la version v2 |
| `index.html` | **Remplacer** par la version v2 |
| `data/daily_stats.json` | **Créer** (présent dans le ZIP v2) |
| `.github/workflows/hourly-update.yml` | **Créer** |
| `.github/workflows/daily-update.yml` | **Supprimer** (remplacé par hourly) |

Méthode la plus simple :

1. Décompresse le ZIP v2 sur ton bureau
2. Sur ton repo GitHub, va sur chaque fichier existant et clique sur le crayon ✏️ pour éditer :
   - **`ingest_steam.py`** : sélectionne tout (Ctrl+A) → supprime → colle le contenu du nouveau fichier → Commit changes
   - **`index.html`** : pareil
3. Pour le nouveau fichier `data/daily_stats.json` :
   - **Add file** → **Upload files**
   - Glisse le fichier `daily_stats.json` depuis le dossier `data/` du ZIP
   - Le drag-and-drop dans le dossier `data/` directement, sinon mets `data/daily_stats.json` comme nom
4. Pour le workflow `hourly-update.yml` :
   - Va sur `.github/workflows/`
   - **Add file** → **Create new file**
   - Nom : `hourly-update.yml`
   - Colle le contenu depuis le ZIP
   - Commit
5. Pour supprimer `daily-update.yml` :
   - Va sur `.github/workflows/daily-update.yml`
   - Clique sur l'icône poubelle 🗑️ en haut à droite
   - Commit la suppression

### Étape 3 : Vérifier que tout tourne

1. Onglet **Actions** → tu dois voir un nouveau workflow **"Hourly Steam + Twitch ingestion"**
2. Clique dessus → **Run workflow** → **Run workflow** (lance manuellement pour la 1re fois)
3. Attends 1-2 min → run vert ✓
4. Va sur ton site → tu dois voir les 2 nouvelles colonnes : **Peak ⏰** et **Région**

### Étape 4 (optionnelle) : Supprimer l'ancien history.json

Une fois que tu as au moins 1 jour de données v2, tu peux supprimer `data/history.json` (le site utilise `daily_stats.json` en priorité maintenant).

Tu peux aussi le garder, ça ne pose pas de souci — l'app utilise `daily_stats.json` en priorité.

## 🕐 Fréquence de mise à jour

Le workflow tournera maintenant à **HH:05 UTC** chaque heure, soit :
- 00:05, 01:05, 02:05, ... 23:05 UTC

Sur ton fuseau (France) :
- Heure d'hiver : 01:05, 02:05, ... 00:05 (heure locale)
- Heure d'été : 02:05, 03:05, ... 01:05 (heure locale)

⚠️ **Note** : GitHub Actions ne garantit pas la ponctualité exacte des crons. Il peut y avoir 5-15 min de retard pendant les pics d'utilisation. Ce n'est pas grave pour notre usage.

## 📊 Premier jour de données réelles

À la première heure d'ingestion v2 :
- `data/hourly/YYYY-MM-DD.json` est créé avec **1 snapshot**
- `data/daily_stats.json` ajoute une entrée pour aujourd'hui avec **peak = 1 mesure** (forcément égale à cette seule mesure)
- L'app fonctionne mais la région et le peak sont peu informatifs (1 seule donnée)

Au bout de **24 heures**, tu auras le premier "vrai" peak journalier avec toutes les heures couvertes.

## ❓ Problèmes courants

### "Le site affiche encore les anciennes données"

- Cache navigateur : fait un **hard refresh** (Ctrl+F5)
- GitHub Pages prend ~1 min après un push pour redéployer

### "Le workflow horaire échoue"

Va voir le log : Actions → dernier run rouge → ingest → Run hourly ingestion.

Causes fréquentes :
- **Token Twitch expiré** : régénère un Client Secret et mets-le à jour dans Settings → Secrets
- **Conflit Git** (rare) : le workflow réessaie automatiquement 3 fois
- **Rate limit Steam/Twitch** : très rare, ça passe au run suivant

### "Je veux revenir à la v1"

```
Settings → Branches → switch default branch → backup-v1
```

Ou bien dans l'interface, restore les anciens fichiers depuis l'historique des commits.

## 🎯 Et après ?

Une fois que la v2 tourne depuis ~1 semaine, tu auras des données vraiment intéressantes :
- Pour Rust, tu verras si le peak est à 18h UTC (Europe) ou 22h UTC (US East)
- Pour les jeux asiatiques (s'il y en a), le peak sera à 11h-13h UTC
- Pour Once Human (qui a une grosse base CN), tu pourras voir si le peak est asiatique ou occidental

Évolutions possibles à ce stade :
- **Heatmap horaire** : voir la distribution des CCU heure par heure
- **Comparaison régions** : superposer Europe vs US sur un même jeu
- **Détection de patterns** : "Rust pic à 20h UTC le week-end vs 18h UTC en semaine"

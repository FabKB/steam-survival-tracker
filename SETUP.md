# 🚀 Guide pas-à-pas : du zéro au site en ligne

Ce guide t'emmène de "je n'ai pas de compte GitHub" à "j'ai un site live qui se met à jour tout seul". Compte ~25 minutes.

---

## Étape 1 — Créer un compte GitHub (5 min)

1. Va sur https://github.com/signup
2. Email → mot de passe → username (ce sera l'URL de ton site, choisis bien : ex `julien-survival`)
3. Vérifie ton email
4. Choisis le plan **Free** (suffit largement)

⚠️ **Note importante sur le repo privé** : GitHub Pages (= hébergement gratuit de l'app) ne fonctionne sur repos privés qu'avec un compte **GitHub Pro (4 $/mois)**. Trois options :
- 🟢 **Le plus simple** : repo public — les données Steam/Twitch sont publiques de toute façon, et personne ne tombera dessus sans connaître l'URL
- 🟡 GitHub Pro pour rester privé
- 🟠 Utiliser Cloudflare Pages au lieu de GitHub Pages (voir tout en bas)

Choisis publique pour l'instant, tu pourras toujours passer en privé plus tard.

---

## Étape 2 — Créer une app Twitch (3 min)

1. Va sur https://dev.twitch.tv/console/apps
2. Connecte-toi avec ton compte Twitch (crée-en un si besoin)
3. Clique **Register Your Application** :
   - **Name** : `steam-survival-tracker`
   - **OAuth Redirect URLs** : `http://localhost`
   - **Category** : `Application Integration`
   - **Client Type** : `Confidential`
4. Clique **Create**
5. Sur la page de ton app, copie le **Client ID** dans un fichier texte temporaire
6. Clique **New Secret** → confirme → copie le **Client Secret** dans le même fichier texte

⚠️ Tu ne pourras plus jamais revoir le Secret après avoir quitté cette page. Garde-le bien.

---

## Étape 3 — Créer le repo (5 min)

### 3.1 Crée le repo vide

1. Sur GitHub, clique le **+** en haut à droite → **New repository**
2. Nom : `steam-survival-tracker`
3. **Public** (voir note étape 1)
4. **Coche** "Add a README file"
5. Clique **Create repository**

### 3.2 Upload les fichiers

Le plus simple sans connaître Git :

1. Sur la page du repo, clique **Add file** → **Upload files**
2. Glisse-dépose tous les fichiers et dossiers que je t'ai fournis :
   - `index.html`
   - `ingest_steam.py`
   - `README.md` (écrase celui créé par défaut)
   - `.gitignore`
   - Le dossier `data/` (avec `history.json` dedans)
   - Le dossier `.github/` (avec `workflows/`)
3. En bas, écris un message de commit : `initial setup`
4. Clique **Commit changes**

⚠️ Le dossier `.github/` peut être invisible par défaut dans certains gestionnaires de fichiers (commence par un point). Sur Windows, active "Afficher les éléments masqués" dans l'Explorateur.

💡 **Astuce** : tu peux drag-and-drop des dossiers entiers dans l'interface GitHub. Elle conserve l'arborescence.

---

## Étape 4 — Configurer les secrets Twitch (2 min)

1. Sur ton repo, va dans **Settings** (en haut à droite, dans la barre du repo)
2. Dans le menu de gauche : **Secrets and variables** → **Actions**
3. Clique **New repository secret** :
   - Name : `TWITCH_CLIENT_ID`
   - Secret : (colle ton Client ID)
   - Clique **Add secret**
4. Re-clique **New repository secret** :
   - Name : `TWITCH_SECRET`
   - Secret : (colle ton Client Secret)
   - Clique **Add secret**

Tu dois maintenant voir 2 secrets dans la liste.

---

## Étape 5 — Activer GitHub Pages (2 min)

1. **Settings** → **Pages** (menu de gauche)
2. Sous "Build and deployment", **Source** : sélectionne **GitHub Actions**
3. C'est tout, pas besoin de cliquer Save.

---

## Étape 6 — Lancer la première mise à jour (3 min)

1. Onglet **Actions** (barre du haut du repo)
2. Si GitHub te demande "I understand my workflows..." → clique pour activer
3. Dans la sidebar gauche, clique **Daily Steam + Twitch ingestion**
4. À droite, bouton **Run workflow** (gris) → clique → **Run workflow** (vert)
5. Attends 1-2 minutes. Tu verras un point vert ✓ quand c'est fini.

Pendant ce temps, le workflow **Deploy to GitHub Pages** se lance automatiquement après le commit (déclenché par le push de `data/history.json`). Attends qu'il soit vert aussi.

---

## ✅ C'est fini !

Ton site est en ligne sur :

```
https://TON-USERNAME.github.io/steam-survival-tracker/
```

(remplace `TON-USERNAME` par ton vrai username GitHub)

Cette URL est partageable, fonctionne sur mobile, tablet, desktop, sur tous les navigateurs.

À partir de maintenant, **chaque jour à 10h UTC**, le workflow tourne tout seul, met à jour les données, et redéploie le site. Tu n'as plus rien à faire.

---

## 🔧 Vérifications de bon fonctionnement

Va sur l'onglet **Actions** régulièrement (1-2 fois par semaine) pour vérifier que les jobs passent au vert ✓.

Si un jour le job échoue (rouge ❌) :
- Clique dessus pour voir l'erreur
- Cas fréquents :
  - **Token Twitch expiré** : c'est rare, mais re-génère un Secret si besoin
  - **API Steam indisponible** : ça passera tout seul le lendemain
  - **Rate limit** : pareil, ça repasse seul

---

## 🆘 En cas de problème

### Le site affiche les données simulées au lieu des vraies

Le fetch de `data/history.json` a échoué. Ouvre la console du navigateur (F12) → onglet **Console** : tu verras "[tracker] Using embedded fallback history" suivi de la raison.

Causes fréquentes :
- Le fichier `data/history.json` n'a pas encore été commité → relance le workflow d'ingestion
- GitHub Pages pas encore activé ou redéployé → attends ~1 minute après le push

### "404" sur l'URL GitHub Pages

- Vérifie que Settings → Pages indique bien "Your site is live at..."
- Le premier déploiement peut prendre 5-10 minutes
- Vérifie qu'il y a bien un `index.html` à la racine du repo

### Le workflow ne se lance pas tout seul à 10h

GitHub peut retarder les crons de quelques minutes à quelques heures sur les comptes Free. C'est normal. Si ça dure >24h, vérifie que le workflow est bien activé (Actions → enable workflow).

---

## 🌈 Alternative : Cloudflare Pages (pour repo privé gratuit)

Si tu veux absolument garder le repo privé sans payer GitHub Pro :

1. Crée un compte Cloudflare gratuit
2. **Workers & Pages** → **Create application** → **Pages** → **Connect to Git**
3. Connecte ton GitHub, choisis le repo
4. Build settings : laisse vide (pas de build)
5. **Save and Deploy**

Tu auras une URL `https://steam-survival-tracker.pages.dev/` qui se met à jour automatiquement à chaque push.

C'est gratuit, illimité, supporte les repos privés, et c'est encore plus rapide que GitHub Pages. Le workflow `daily-update.yml` continue de tourner sur GitHub, mais Cloudflare se charge juste de l'hébergement. Tu peux désactiver `deploy-pages.yml` dans ce cas.

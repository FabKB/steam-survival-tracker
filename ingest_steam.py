#!/usr/bin/env python3
"""
Ingestion quotidienne des données Steam + Twitch pour le tracker survie.

Usage:
    python ingest_steam.py

Récupère:
- CCU live Steam (GetNumberOfCurrentPlayers) - quotidien, historisé
- Métadonnées Steam (prix, reviews, date sortie, tags) - hebdo
- Viewers Twitch via Helix API (si TWITCH_CLIENT_ID + TWITCH_SECRET en env vars)

Fichiers produits:
- data/snapshot_YYYY-MM-DD.json : snapshot du jour
- data/history.json : historique cumulé {appid: [{date, ccu, twitch_viewers}, ...]}
- data/games_meta.json : métadonnées (prix, reviews, etc.)

Setup Twitch (optionnel mais recommandé):
    1. Crée une app sur https://dev.twitch.tv/console/apps
       - OAuth Redirect URL: http://localhost
       - Category: Application Integration
    2. Copie Client ID + génère un Client Secret
    3. Exporte les variables d'environnement:
        export TWITCH_CLIENT_ID=xxx
        export TWITCH_SECRET=yyy
"""

import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import date, datetime
from pathlib import Path

# Liste des jeux: appid -> (nom Steam, nom Twitch)
# Le nom Twitch peut différer (ex: "ARK: Survival Evolved" sur Steam = "ARK" sur Twitch)
GAMES = {
    252490: ("Rust", "Rust"),
    221100: ("DayZ", "DayZ"),
    346110: ("ARK: Survival Evolved", "ARK"),
    2399830: ("ARK: Survival Ascended", "ARK: Survival Ascended"),
    892970: ("Valheim", "Valheim"),
    251570: ("7 Days to Die", "7 Days to Die"),
    1604030: ("V Rising", "V Rising"),
    440900: ("Conan Exiles", "Conan Exiles"),
    1172710: ("Dune: Awakening", "Dune: Awakening"),
    1623730: ("Palworld", "Palworld"),
    108600: ("Project Zomboid", "Project Zomboid"),
    1203620: ("Enshrouded", "Enshrouded"),
    2646460: ("Soulmask", "Soulmask"),
    2139460: ("Once Human", "Once Human"),
    1371580: ("Myth of Empires", "Myth of Empires"),
}

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
HEADERS = {"User-Agent": "Mozilla/5.0 (steam-survival-tracker)"}


def http_get_json(url, headers=None, timeout=10):
    req = urllib.request.Request(url, headers={**HEADERS, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_post_json(url, data, headers=None, timeout=10):
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, headers={**HEADERS, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ============================================================
# Steam API
# ============================================================

def get_current_players(appid):
    """CCU instantané — gratuit, pas de clé."""
    url = f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={appid}"
    try:
        data = http_get_json(url)
        return data.get("response", {}).get("player_count")
    except Exception as e:
        print(f"  [!] Steam CCU {appid}: {e}")
        return None


def get_app_details(appid, cc="us", lang="english"):
    """Métadonnées Store (prix, dev, genres, etc.)."""
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc={cc}&l={lang}"
    try:
        data = http_get_json(url)
        entry = data.get(str(appid), {})
        if not entry.get("success"):
            return None
        d = entry["data"]
        price_data = d.get("price_overview") or {}
        return {
            "name": d.get("name"),
            "release_date": d.get("release_date", {}).get("date"),
            "is_free": d.get("is_free", False),
            "price_usd": price_data.get("final") / 100 if price_data.get("final") else None,
            "discount_pct": price_data.get("discount_percent", 0),
            "developers": d.get("developers", []),
            "publishers": d.get("publishers", []),
            "categories": [c["description"] for c in d.get("categories", [])],
            "genres": [g["description"] for g in d.get("genres", [])],
            "header_image": d.get("header_image"),
        }
    except Exception as e:
        print(f"  [!] Steam appdetails {appid}: {e}")
        return None


def get_reviews(appid):
    """Reviews Steam : % positif et total."""
    url = f"https://store.steampowered.com/appreviews/{appid}?json=1&language=all&purchase_type=all"
    try:
        data = http_get_json(url)
        s = data.get("query_summary", {})
        total = s.get("total_reviews", 0)
        positive = s.get("total_positive", 0)
        return {
            "total_reviews": total,
            "positive_pct": round(100 * positive / total, 1) if total else None,
            "review_score_desc": s.get("review_score_desc"),
        }
    except Exception as e:
        print(f"  [!] Steam reviews {appid}: {e}")
        return None


# ============================================================
# Twitch Helix API
# ============================================================

class TwitchClient:
    """Client minimal pour l'API Twitch Helix.
    Doc: https://dev.twitch.tv/docs/api/
    """
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.token_expires = 0

    def _ensure_token(self):
        if self.token and time.time() < self.token_expires - 60:
            return
        # OAuth client credentials flow
        url = "https://id.twitch.tv/oauth2/token"
        resp = http_post_json(url, {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        })
        self.token = resp["access_token"]
        self.token_expires = time.time() + resp.get("expires_in", 3600)

    def _headers(self):
        return {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.token}",
        }

    def get_game_id(self, name):
        """Trouve le game_id Twitch pour un nom donné."""
        self._ensure_token()
        url = f"https://api.twitch.tv/helix/games?name={urllib.parse.quote(name)}"
        data = http_get_json(url, headers=self._headers())
        items = data.get("data", [])
        return items[0]["id"] if items else None

    def get_total_viewers_for_game(self, game_id):
        """Somme des viewers de tous les streams live pour ce jeu.
        Pour les jeux populaires, on récupère jusqu'à 500 streams (5 pages * 100).
        """
        self._ensure_token()
        base_url = f"https://api.twitch.tv/helix/streams?game_id={game_id}&first=100"
        total_viewers = 0
        total_streams = 0
        cursor = None
        for _ in range(5):
            url = base_url + (f"&after={cursor}" if cursor else "")
            data = http_get_json(url, headers=self._headers())
            streams = data.get("data", [])
            if not streams:
                break
            total_viewers += sum(s.get("viewer_count", 0) for s in streams)
            total_streams += len(streams)
            cursor = data.get("pagination", {}).get("cursor")
            if not cursor:
                break
        return {"total_viewers": total_viewers, "live_channels": total_streams}


# ============================================================
# Storage helpers
# ============================================================

def update_history(snapshot, history_path):
    """Append le snapshot au history.json (dédup par date)."""
    if history_path.exists():
        history = json.loads(history_path.read_text(encoding="utf-8"))
    else:
        history = {}

    today = snapshot["date"]
    for entry in snapshot["games"]:
        appid = str(entry["appid"])
        if appid not in history:
            history[appid] = []
        history[appid] = [h for h in history[appid] if h["date"] != today]
        new_entry = {"date": today}
        if entry.get("ccu") is not None:
            new_entry["ccu"] = entry["ccu"]
        if entry.get("twitch_viewers") is not None:
            new_entry["twitch_viewers"] = entry["twitch_viewers"]
            new_entry["twitch_channels"] = entry.get("twitch_channels")
        if "ccu" in new_entry or "twitch_viewers" in new_entry:
            history[appid].append(new_entry)
        history[appid].sort(key=lambda x: x["date"])

    history_path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    return history


def should_refresh_meta(meta_path, days=7):
    if not meta_path.exists():
        return True
    age = (datetime.now() - datetime.fromtimestamp(meta_path.stat().st_mtime)).days
    return age >= days


# ============================================================
# Main
# ============================================================

def main():
    today_str = date.today().isoformat()
    print(f"=== Ingestion Steam + Twitch — {today_str} ===\n")

    # Setup Twitch (optionnel)
    twitch = None
    tw_id = os.environ.get("TWITCH_CLIENT_ID")
    tw_secret = os.environ.get("TWITCH_SECRET")
    if tw_id and tw_secret:
        try:
            twitch = TwitchClient(tw_id, tw_secret)
            twitch._ensure_token()
            print("✓ Twitch API: connecté\n")
        except Exception as e:
            print(f"✗ Twitch API échoué: {e}\n")
            twitch = None
    else:
        print("ℹ  TWITCH_CLIENT_ID / TWITCH_SECRET non définis — viewers Twitch ignorés\n")

    # Cache game_id Twitch (évite de relookup à chaque run)
    twitch_ids_path = DATA_DIR / "twitch_game_ids.json"
    twitch_ids = {}
    if twitch_ids_path.exists():
        twitch_ids = json.loads(twitch_ids_path.read_text())

    print("→ Métriques live")
    snapshot = {"date": today_str, "games": []}
    for appid, (steam_name, twitch_name) in GAMES.items():
        ccu = get_current_players(appid)
        time.sleep(0.3)

        tw_viewers = None
        tw_channels = None
        if twitch:
            try:
                gid = twitch_ids.get(twitch_name)
                if not gid:
                    gid = twitch.get_game_id(twitch_name)
                    if gid:
                        twitch_ids[twitch_name] = gid
                if gid:
                    res = twitch.get_total_viewers_for_game(gid)
                    tw_viewers = res["total_viewers"]
                    tw_channels = res["live_channels"]
                time.sleep(0.3)
            except Exception as e:
                print(f"  [!] Twitch {twitch_name}: {e}")

        ccu_str = f"{ccu:>7,}" if ccu is not None else "    N/A"
        tw_str = f"{tw_viewers:>6,}v / {tw_channels:>3} ch" if tw_viewers is not None else ""
        print(f"  {steam_name:30s} CCU={ccu_str}  Twitch={tw_str}")

        snapshot["games"].append({
            "appid": appid,
            "name": steam_name,
            "ccu": ccu,
            "twitch_viewers": tw_viewers,
            "twitch_channels": tw_channels,
        })

    if twitch:
        twitch_ids_path.write_text(json.dumps(twitch_ids, indent=2, ensure_ascii=False))

    snapshot_path = DATA_DIR / f"snapshot_{today_str}.json"
    snapshot_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n✓ Snapshot : {snapshot_path}")

    history_path = DATA_DIR / "history.json"
    history = update_history(snapshot, history_path)
    print(f"✓ Historique : {history_path} ({sum(len(v) for v in history.values())} points)")

    # Métadonnées (hebdo)
    meta_path = DATA_DIR / "games_meta.json"
    if should_refresh_meta(meta_path):
        print("\n→ Métadonnées (refresh hebdo)")
        meta = {}
        for appid, (steam_name, _) in GAMES.items():
            print(f"  {steam_name}")
            details = get_app_details(appid)
            reviews = get_reviews(appid)
            time.sleep(1.0)
            meta[str(appid)] = {
                "name": steam_name,
                "details": details,
                "reviews": reviews,
                "last_refresh": today_str,
            }
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"✓ Métadonnées : {meta_path}")
    else:
        print("\n→ Métadonnées : skip (refresh dans <7j)")

    print("\n=== Terminé ===")


if __name__ == "__main__":
    main()

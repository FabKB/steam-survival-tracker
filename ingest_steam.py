#!/usr/bin/env python3
"""
Ingestion HORAIRE des données Steam + Twitch pour le tracker survie.

Lancé toutes les heures par GitHub Actions, ce script :
1. Capture CCU Steam + viewers Twitch pour les 15 jeux
2. Stocke un snapshot horaire dans data/hourly/YYYY-MM-DD.json
3. Met à jour data/daily_stats.json avec les peaks du jour en cours
4. Refresh hebdo des métadonnées Steam

Détection de la région primaire :
- Combinaison de l'heure UTC du peak (heuristique fuseau horaire)
- Et de la langue dominante des streams Twitch au moment du peak

Setup Twitch :
    https://dev.twitch.tv/console/apps → Register → récupérer Client ID + Secret
    export TWITCH_CLIENT_ID=xxx
    export TWITCH_SECRET=yyy
"""

import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path
from collections import defaultdict

# appid -> (nom Steam, nom Twitch)
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
(DATA_DIR / "hourly").mkdir(exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 (steam-survival-tracker)"}


# ============================================================
# HTTP helpers
# ============================================================

def http_get_json(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers={**HEADERS, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_post_json(url, data, headers=None, timeout=15):
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, headers={**HEADERS, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ============================================================
# Steam API
# ============================================================

def get_current_players(appid):
    url = f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={appid}"
    try:
        data = http_get_json(url)
        return data.get("response", {}).get("player_count")
    except Exception as e:
        print(f"  [!] Steam CCU {appid}: {e}")
        return None


def get_app_details(appid):
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=us&l=english"
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
            "genres": [g["description"] for g in d.get("genres", [])],
            "header_image": d.get("header_image"),
        }
    except Exception as e:
        print(f"  [!] Steam appdetails {appid}: {e}")
        return None


def get_reviews(appid):
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
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.token_expires = 0

    def _ensure_token(self):
        if self.token and time.time() < self.token_expires - 60:
            return
        resp = http_post_json("https://id.twitch.tv/oauth2/token", {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        })
        self.token = resp["access_token"]
        self.token_expires = time.time() + resp.get("expires_in", 3600)

    def _headers(self):
        return {"Client-ID": self.client_id, "Authorization": f"Bearer {self.token}"}

    def get_game_id(self, name):
        self._ensure_token()
        url = f"https://api.twitch.tv/helix/games?name={urllib.parse.quote(name)}"
        data = http_get_json(url, headers=self._headers())
        items = data.get("data", [])
        return items[0]["id"] if items else None

    def get_streams_for_game(self, game_id, max_pages=5):
        """Récupère les streams + agrège viewers et langues.
        Pour les jeux populaires, ~500 streams suffisent à couvrir 95%+ des viewers.
        """
        self._ensure_token()
        base_url = f"https://api.twitch.tv/helix/streams?game_id={game_id}&first=100"
        total_viewers = 0
        total_streams = 0
        viewers_by_lang = defaultdict(int)  # lang code -> total viewers
        cursor = None

        for _ in range(max_pages):
            url = base_url + (f"&after={cursor}" if cursor else "")
            data = http_get_json(url, headers=self._headers())
            streams = data.get("data", [])
            if not streams:
                break
            for s in streams:
                v = s.get("viewer_count", 0)
                lang = (s.get("language") or "??").lower()
                total_viewers += v
                viewers_by_lang[lang] += v
                total_streams += 1
            cursor = data.get("pagination", {}).get("cursor")
            if not cursor:
                break

        return {
            "total_viewers": total_viewers,
            "live_channels": total_streams,
            "viewers_by_lang": dict(viewers_by_lang),
        }


# ============================================================
# Région : heuristique fuseau horaire + désambiguïsation langue
# ============================================================

# Mapping langue Twitch -> région principale (pour la désambiguïsation)
LANG_TO_REGION = {
    "en": "NA_EU",       # mix Amérique / Europe
    "fr": "EU",
    "de": "EU",
    "es": "EU_LATAM",
    "it": "EU",
    "pl": "EU",
    "pt": "EU_LATAM",    # PT-BR aussi
    "ru": "CIS",
    "uk": "CIS",
    "tr": "EU_ME",
    "ar": "ME",
    "ja": "ASIA_E",
    "ko": "ASIA_E",
    "zh": "ASIA_E",
    "th": "ASIA_SE",
    "vi": "ASIA_SE",
    "id": "ASIA_SE",
    "tl": "ASIA_SE",
}


def infer_region(peak_hour_utc, viewers_by_lang):
    """
    Retourne {code, label, emoji, confidence}
    code: ID interne (NA, EU, CIS, ASIA_E, ASIA_SE, ME, LATAM, MIXED)
    """
    # Étape 1 : régions plausibles selon l'heure UTC (où il est 17h-23h local)
    # Heure locale du peak gaming = ~19h en moyenne
    hour_candidates = {
        # heure UTC : [(région, label, emoji, score)]
    }

    def add(h, region, label, emoji, score):
        hour_candidates.setdefault(h, []).append((region, label, emoji, score))

    # On définit pour chaque région la plage UTC où 17h-23h locales tombent
    # Score = à quel point on est au "cœur" de la prime time (max à 19-20h local)
    regions_tz = [
        # (région, label, emoji, plage_utc_min, plage_utc_max, utc_du_peak_local_19h)
        ("NA_W", "🇺🇸 Amérique Ouest", "🇺🇸", 0, 7, 3),     # UTC-8 → 19h local = 03h UTC
        ("NA_E", "🇺🇸 Amérique Est", "🇺🇸", 21, 4, 0),      # UTC-5 → 19h local = 00h UTC
        ("LATAM", "🇧🇷 Amérique Latine", "🌎", 21, 3, 22),  # UTC-3 → 19h local = 22h UTC
        ("EU", "🇪🇺 Europe", "🇪🇺", 16, 22, 19),            # UTC+1 → 19h local = 18h UTC
        ("CIS", "🇷🇺 Russie/CEI", "🇷🇺", 13, 19, 16),       # UTC+3 → 19h local = 16h UTC
        ("ME", "🌍 Moyen-Orient", "🌍", 13, 19, 16),
        ("ASIA_E", "🇨🇳 Asie Est", "🇨🇳", 9, 15, 11),       # UTC+8 → 19h local = 11h UTC
        ("ASIA_SE", "🇸🇬 Asie SE", "🌏", 10, 16, 12),       # UTC+7 → 19h local = 12h UTC
        ("OCEANIA", "🇦🇺 Océanie", "🇦🇺", 6, 12, 9),        # UTC+10 → 19h local = 09h UTC
    ]

    candidates = []
    for region, label, emoji, lo, hi, peak in regions_tz:
        # Gérer le wraparound (lo > hi)
        if lo <= hi:
            in_range = lo <= peak_hour_utc <= hi
        else:
            in_range = peak_hour_utc >= lo or peak_hour_utc <= hi
        if in_range:
            # Distance au "vrai" peak (19h local) → score
            distance = min(abs(peak_hour_utc - peak), 24 - abs(peak_hour_utc - peak))
            score = max(0, 6 - distance)
            candidates.append((region, label, emoji, score))

    if not candidates:
        return {"code": "UNKNOWN", "label": "—", "emoji": "🌐", "confidence": "low"}

    # Étape 2 : désambiguïsation par langue Twitch
    if viewers_by_lang:
        total = sum(viewers_by_lang.values()) or 1
        # Calculer le poids par région d'après les langues
        region_lang_score = defaultdict(int)
        for lang, viewers in viewers_by_lang.items():
            region_lang = LANG_TO_REGION.get(lang)
            if not region_lang:
                continue
            weight = viewers / total
            # Une langue peut booster plusieurs régions
            if region_lang == "NA_EU":
                region_lang_score["NA_W"] += weight * 0.5
                region_lang_score["NA_E"] += weight * 0.5
                region_lang_score["EU"] += weight * 0.5
            elif region_lang == "EU_LATAM":
                region_lang_score["EU"] += weight * 0.5
                region_lang_score["LATAM"] += weight * 0.5
            elif region_lang == "EU_ME":
                region_lang_score["EU"] += weight * 0.5
                region_lang_score["ME"] += weight * 0.5
            else:
                region_lang_score[region_lang] += weight

        # Boost des candidates avec la langue
        boosted = []
        for region, label, emoji, score in candidates:
            lang_boost = region_lang_score.get(region, 0) * 10
            boosted.append((region, label, emoji, score + lang_boost))
        candidates = boosted

    # Tri par score descendant
    candidates.sort(key=lambda x: -x[3])
    best = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None

    # Confidence : haute si le 1er a 2x le score du 2nd, basse sinon
    if second and best[3] < second[3] * 1.3:
        # Trop proches → mixed
        return {
            "code": "MIXED",
            "label": f"{best[1]} / {second[1].split(' ', 1)[1] if ' ' in second[1] else second[1]}",
            "emoji": f"{best[2]}{second[2]}",
            "confidence": "low",
        }

    return {
        "code": best[0],
        "label": best[1],
        "emoji": best[2],
        "confidence": "high" if second is None or best[3] > second[3] * 2 else "medium",
    }


# ============================================================
# Stockage : hourly + daily aggregate
# ============================================================

def append_hourly_snapshot(snapshot):
    """Ajoute le snapshot du jour dans data/hourly/YYYY-MM-DD.json (par date UTC)."""
    today = snapshot["date"]
    hourly_path = DATA_DIR / "hourly" / f"{today}.json"
    if hourly_path.exists():
        day_data = json.loads(hourly_path.read_text(encoding="utf-8"))
    else:
        day_data = {"date": today, "snapshots": []}

    # Dédup par heure UTC
    hour_utc = snapshot["hour_utc"]
    day_data["snapshots"] = [s for s in day_data["snapshots"] if s.get("hour_utc") != hour_utc]
    day_data["snapshots"].append({
        "hour_utc": hour_utc,
        "timestamp": snapshot["timestamp"],
        "games": snapshot["games"],
    })
    day_data["snapshots"].sort(key=lambda x: x["hour_utc"])
    hourly_path.write_text(json.dumps(day_data, ensure_ascii=False), encoding="utf-8")
    return day_data


def compute_daily_stats(day_data):
    """À partir des snapshots d'une journée, calcule peak CCU, peak Twitch et régions."""
    stats_by_game = {}
    snapshots = day_data["snapshots"]
    if not snapshots:
        return {}

    # Pour chaque jeu, trouver le peak CCU et le peak Twitch sur la journée
    for appid_str in {str(g["appid"]) for s in snapshots for g in s["games"]}:
        ccu_series = []
        twitch_series = []
        for s in snapshots:
            for g in s["games"]:
                if str(g["appid"]) == appid_str:
                    ccu_series.append({
                        "hour_utc": s["hour_utc"],
                        "ccu": g.get("ccu"),
                        "twitch_viewers": g.get("twitch_viewers"),
                        "viewers_by_lang": g.get("viewers_by_lang", {}),
                    })

        # Peak CCU
        valid_ccu = [x for x in ccu_series if x["ccu"] is not None]
        peak_ccu = max(valid_ccu, key=lambda x: x["ccu"]) if valid_ccu else None

        # Peak Twitch viewers
        valid_tw = [x for x in ccu_series if x["twitch_viewers"] is not None]
        peak_tw = max(valid_tw, key=lambda x: x["twitch_viewers"]) if valid_tw else None

        # Région : inférée à l'heure du peak CCU, désambiguïsation avec les langues Twitch
        # au même moment (si dispo)
        region = None
        if peak_ccu:
            # Cherche le viewers_by_lang au moment du peak (ou le plus proche)
            lang_at_peak = peak_ccu.get("viewers_by_lang") or {}
            region = infer_region(peak_ccu["hour_utc"], lang_at_peak)

        stats_by_game[appid_str] = {
            "peak_ccu": peak_ccu["ccu"] if peak_ccu else None,
            "peak_ccu_hour_utc": peak_ccu["hour_utc"] if peak_ccu else None,
            "peak_twitch_viewers": peak_tw["twitch_viewers"] if peak_tw else None,
            "peak_twitch_hour_utc": peak_tw["hour_utc"] if peak_tw else None,
            "region": region,
            "samples": len(ccu_series),
        }

    return stats_by_game


def update_daily_stats_file(date_str, daily_stats):
    """Met à jour data/daily_stats.json avec les stats du jour."""
    path = DATA_DIR / "daily_stats.json"
    if path.exists():
        all_stats = json.loads(path.read_text(encoding="utf-8"))
    else:
        all_stats = {}

    # all_stats = { "YYYY-MM-DD": { "appid": {...} } }
    all_stats[date_str] = daily_stats
    # Tri par date
    sorted_stats = dict(sorted(all_stats.items()))
    path.write_text(json.dumps(sorted_stats, ensure_ascii=False, indent=2), encoding="utf-8")


def should_refresh_meta(meta_path, days=7):
    if not meta_path.exists():
        return True
    age = (datetime.now() - datetime.fromtimestamp(meta_path.stat().st_mtime)).days
    return age >= days


# ============================================================
# Main
# ============================================================

def main():
    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    hour_utc = now_utc.hour
    iso_ts = now_utc.isoformat()

    print(f"=== Ingestion HORAIRE — {today_str} {hour_utc:02d}h UTC ===\n")

    # Twitch setup (optionnel)
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
        print("ℹ  TWITCH_CLIENT_ID / TWITCH_SECRET non définis — Twitch ignoré\n")

    # Cache des game_id Twitch
    twitch_ids_path = DATA_DIR / "twitch_game_ids.json"
    twitch_ids = json.loads(twitch_ids_path.read_text()) if twitch_ids_path.exists() else {}

    # Collecte
    print("→ Métriques live")
    games_data = []
    for appid, (steam_name, twitch_name) in GAMES.items():
        ccu = get_current_players(appid)
        time.sleep(0.25)

        tw_viewers = None
        tw_channels = None
        viewers_by_lang = {}
        if twitch:
            try:
                gid = twitch_ids.get(twitch_name)
                if not gid:
                    gid = twitch.get_game_id(twitch_name)
                    if gid:
                        twitch_ids[twitch_name] = gid
                if gid:
                    res = twitch.get_streams_for_game(gid)
                    tw_viewers = res["total_viewers"]
                    tw_channels = res["live_channels"]
                    viewers_by_lang = res["viewers_by_lang"]
                time.sleep(0.25)
            except Exception as e:
                print(f"  [!] Twitch {twitch_name}: {e}")

        ccu_str = f"{ccu:>7,}" if ccu is not None else "    N/A"
        tw_str = f"{tw_viewers:>6,}v" if tw_viewers is not None else ""
        print(f"  {steam_name:30s} CCU={ccu_str}  Twitch={tw_str}")

        games_data.append({
            "appid": appid,
            "name": steam_name,
            "ccu": ccu,
            "twitch_viewers": tw_viewers,
            "twitch_channels": tw_channels,
            "viewers_by_lang": viewers_by_lang if viewers_by_lang else None,
        })

    if twitch:
        twitch_ids_path.write_text(json.dumps(twitch_ids, indent=2, ensure_ascii=False))

    # 1. Append au snapshot horaire
    snapshot = {
        "date": today_str,
        "hour_utc": hour_utc,
        "timestamp": iso_ts,
        "games": games_data,
    }
    day_data = append_hourly_snapshot(snapshot)
    print(f"\n✓ Snapshot horaire ajouté ({len(day_data['snapshots'])} h/24 pour {today_str})")

    # 2. Recalculer les stats du jour
    daily_stats = compute_daily_stats(day_data)
    update_daily_stats_file(today_str, daily_stats)
    print(f"✓ daily_stats.json mis à jour")

    # Afficher un résumé peak
    print("\n→ Peaks du jour (jusqu'à présent):")
    for appid_str, stats in daily_stats.items():
        if stats["peak_ccu"]:
            steam_name = GAMES[int(appid_str)][0]
            region = stats.get("region", {}) or {}
            region_str = f" {region.get('emoji', '')} {region.get('label', '')}" if region else ""
            print(f"  {steam_name:30s} peak CCU={stats['peak_ccu']:>7,} @ {stats['peak_ccu_hour_utc']:02d}h UTC{region_str}")

    # 3. Métadonnées (hebdo, à minuit UTC seulement pour éviter de refresh à chaque heure)
    meta_path = DATA_DIR / "games_meta.json"
    if hour_utc == 0 and should_refresh_meta(meta_path):
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
        print("✓ Métadonnées mises à jour")

    print("\n=== Terminé ===")


if __name__ == "__main__":
    main()

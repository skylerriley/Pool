#!/usr/bin/env python3
"""
GitHub Actions script: fetches the active major's leaderboard from ESPN
and writes data/leaderboard.json in the format the Pool app expects.

ESPN endpoint:
  https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard

Output JSON shape (mirrors what processLiveLeaderboard() expects as CSV rows):
{
  "major": "US Open",
  "year": "2026",
  "updated": "2026-06-15T14:32:00Z",
  "active": true,
  "rows": [
    {
      "PLAYER": "Scottie Scheffler",
      "COUNTRY": "USA",
      "POS": "1",
      "SCORE": "-10",
      "TODAY": "-3",
      "THRU": "14",
      "R1": "-4",
      "R2": "-3",
      "R3": null,
      "R4": null
    },
    ...
  ]
}
"""

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard"

# Map ESPN event name fragments → our major keys (must match MAJOR_META.majorKey in the app)
MAJOR_KEY_MAP = [
    ("masters",     "Masters"),
    ("pga championship", "PGA"),
    ("u.s. open",   "US Open"),
    ("us open",     "US Open"),
    ("the open",    "The Open"),
    ("open championship", "The Open"),
]

def detect_major(event_name: str) -> str | None:
    lower = event_name.lower()
    for fragment, key in MAJOR_KEY_MAP:
        if fragment in lower:
            return key
    return None

def parse_score(val) -> str:
    """Normalise a score value to a signed integer string, 'E', or None."""
    if val is None:
        return None
    s = str(val).strip()
    if s in ('', '--', '-', 'E', 'Even'):
        return 'E' if s in ('E', 'Even', '') else None
    try:
        n = int(s)
        return str(n) if n != 0 else 'E'
    except ValueError:
        return None

def round_score_to_par(strokes, par=72):
    """Convert stroke total → to-par integer string."""
    if strokes is None:
        return None
    try:
        n = int(strokes) - par
        return str(n) if n != 0 else 'E'
    except (ValueError, TypeError):
        return None

def fetch_espn():
    req = urllib.request.Request(
        ESPN_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; PoolApp/1.0)",
            "Accept": "application/json",
        }
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())

def build_rows(competitors, par):
    rows = []
    for c in competitors:
        athlete = c.get("athlete", {})
        name = athlete.get("displayName", "").strip()
        if not name:
            continue

        # Country
        flag = athlete.get("flag", {})
        country = flag.get("alt", "") or athlete.get("countryCode", "")
        # ESPN uses full country names in flag.alt — map common ones to 3-letter codes
        # the app's FLAGS dict expects. Fall back to raw value; app will just skip flag.
        COUNTRY_MAP = {
            "United States": "USA", "England": "ENG", "Scotland": "SCO",
            "Wales": "WAL", "Northern Ireland": "NIR", "Ireland": "IRL",
            "Australia": "AUS", "New Zealand": "NZL", "South Africa": "RSA",
            "Canada": "CAN", "Mexico": "MEX", "Spain": "ESP", "Germany": "GER",
            "France": "FRA", "Italy": "ITA", "Sweden": "SWE", "Norway": "NOR",
            "Denmark": "DEN", "Japan": "JPN", "South Korea": "KOR", "Korea": "KOR",
            "China": "CHN", "Chile": "CHI", "Argentina": "ARG", "Brazil": "BRA",
            "Colombia": "COL", "Fiji": "FIJ", "Thailand": "THA", "India": "IND",
            "Zimbabwe": "ZIM", "Namibia": "NAM", "Austria": "AUT", "Belgium": "BEL",
            "Netherlands": "NED", "Great Britain": "GBR", "Taiwan": "TWN",
            "Venezuela": "VEN", "Puerto Rico": "PUR", "Paraguay": "PAR",
        }
        country_code = COUNTRY_MAP.get(country, country[:3].upper() if country else "")

        # Position
        status = c.get("status", {})
        pos_display = c.get("status", {}).get("position", {}).get("displayName", "") \
                      or c.get("sortOrder", "")
        # ESPN uses "T2", "CUT", "WD", "MDF", numeric, etc.
        pos = str(pos_display).strip() or "—"

        # Thru — ESPN gives "F" for finished, hole number for in-progress, tee time string
        thru_val = status.get("thru") or status.get("displayValue", "")
        thru = str(thru_val).strip() if thru_val is not None else "—"
        # ESPN sometimes returns 0 for "not started" — treat as tee time placeholder
        if thru == "0":
            thru = "—"

        # Score (to par)
        linescores = c.get("linescores", [])  # list of {value, displayValue} per round
        round_scores = []
        for ls in linescores:
            val = ls.get("displayValue") or ls.get("value")
            round_scores.append(val)

        # Pad to 4 rounds
        while len(round_scores) < 4:
            round_scores.append(None)

        r1, r2, r3, r4 = round_scores[0], round_scores[1], round_scores[2], round_scores[3]

        # ESPN linescores are stroke totals for the round; convert to to-par
        def rnd_to_par(v):
            if v is None or str(v).strip() in ('', '--'):
                return None
            try:
                strokes = int(str(v).strip())
                if strokes == 0:
                    return None
                diff = strokes - par
                return str(diff) if diff != 0 else 'E'
            except ValueError:
                return None

        r1_par = rnd_to_par(r1)
        r2_par = rnd_to_par(r2)
        r3_par = rnd_to_par(r3)
        r4_par = rnd_to_par(r4)

        # Overall to-par score from ESPN
        score_stats = c.get("statistics", [])
        score_raw = None
        for stat in score_stats:
            if stat.get("name") in ("scoreToPar", "toPar", "score"):
                score_raw = stat.get("displayValue") or stat.get("value")
                break
        # Fallback: sum round to-par values
        if score_raw is None:
            pars = [r1_par, r2_par, r3_par, r4_par]
            nums = []
            for p in pars:
                if p is None:
                    continue
                nums.append(0 if p == 'E' else int(p))
            score_raw = str(sum(nums)) if nums else None

        score = parse_score(score_raw) if score_raw is not None else "E"

        # Today (current round to-par)
        today_raw = None
        for stat in score_stats:
            if stat.get("name") in ("currentRoundScore", "today"):
                today_raw = stat.get("displayValue") or stat.get("value")
                break
        today = parse_score(today_raw) if today_raw else "E"

        # CUT / WD / MDF detection
        pos_upper = pos.upper()
        is_cut = pos_upper in ("CUT", "WD", "MDF", "DQ")
        if is_cut:
            thru = pos_upper  # app's isCutStatus checks thru for these values

        rows.append({
            "PLAYER":  name,
            "COUNTRY": country_code,
            "POS":     pos,
            "SCORE":   score or "E",
            "TODAY":   today or "E",
            "THRU":    thru,
            "R1":      r1_par,
            "R2":      r2_par,
            "R3":      r3_par,
            "R4":      r4_par,
        })

    return rows

def main():
    print("Fetching ESPN golf scoreboard…")
    try:
        data = fetch_espn()
    except urllib.error.HTTPError as e:
        print(f"HTTP error {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Fetch failed: {e}", file=sys.stderr)
        sys.exit(1)

    events = data.get("events", [])
    if not events:
        print("No events found in ESPN response — no major currently in progress.")
        # Write an empty/inactive marker so the app knows ESPN was checked
        out = {"active": False, "updated": datetime.now(timezone.utc).isoformat(), "rows": []}
        with open("data/leaderboard.json", "w") as f:
            json.dump(out, f)
        return

    # Pick the first (and usually only) event — ESPN only surfaces the active event
    event = events[0]
    event_name = event.get("name", "")
    major_key = detect_major(event_name)
    if not major_key:
        print(f"Could not map event '{event_name}' to a major key — skipping.")
        out = {"active": False, "updated": datetime.now(timezone.utc).isoformat(), "rows": []}
        with open("data/leaderboard.json", "w") as f:
            json.dump(out, f)
        return

    print(f"Event: {event_name}  →  major key: {major_key}")

    # Year
    season = event.get("season", {}).get("year") or datetime.now().year
    year = str(season)

    # Par — try to get from venue info
    competitions = event.get("competitions", [])
    par = 72  # safe default
    if competitions:
        venue = competitions[0].get("venue", {})
        # ESPN doesn't always expose par; 72 is correct for all 4 majors
        par = int(venue.get("par", 72) or 72)

    # Competitors
    competitors = []
    for comp in competitions:
        competitors.extend(comp.get("competitors", []))

    if not competitors:
        print("No competitors found.")
        out = {"active": False, "updated": datetime.now(timezone.utc).isoformat(), "rows": []}
        with open("data/leaderboard.json", "w") as f:
            json.dump(out, f)
        return

    rows = build_rows(competitors, par)
    print(f"Built {len(rows)} player rows.")

    out = {
        "major":   major_key,
        "year":    year,
        "updated": datetime.now(timezone.utc).isoformat(),
        "active":  True,
        "rows":    rows,
    }

    import os
    os.makedirs("data", exist_ok=True)
    with open("data/leaderboard.json", "w") as f:
        json.dump(out, f, indent=2)

    print(f"Written data/leaderboard.json  ({len(rows)} players, {major_key} {year})")

if __name__ == "__main__":
    main()

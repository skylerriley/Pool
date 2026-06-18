#!/usr/bin/env python3
"""
GitHub Actions script: fetches tournament-winner odds for the active major
from The Odds API and writes data/odds.json in the shape the Pool app expects.

THE FIX (vs the previous version):
  - Always writes "fetched_at"  = when THIS script actually ran (UTC, real time).
  - Always writes "bookmaker_updated" = when the book last moved prices (from the API).
  - Keeps "updated" for backward-compatibility (mirrors fetched_at).

The app shows "fetched_at" first, so once this runs, the timestamp will match
your cron cadence instead of the bookmaker's last price move.

Output shape:
{
  "major": "US Open",
  "sport_key": "golf_us_open_winner",
  "updated": "2026-06-18T16:20:03Z",            # mirror of fetched_at (legacy field)
  "fetched_at": "2026-06-18T16:20:03Z",         # when this workflow ran  <-- THE FIX
  "bookmaker_updated": "2026-06-18T16:18:55Z",  # when odds last moved at the book
  "source": "fanduel_or_median",
  "odds": { "Scottie Scheffler": 700, ... }
}
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from statistics import median

# ── Config ────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("ODDS_API_KEY", "").strip()

# Set these to match the active major when it changes.
SPORT_KEY   = os.environ.get("SPORT_KEY",   "golf_us_open_winner")
MAJOR_LABEL = os.environ.get("MAJOR_LABEL", "US Open")

REGIONS = "us"
MARKETS = "outrights"
ODDS_FORMAT = "american"

API_URL = (
    f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/odds"
    f"?regions={REGIONS}&markets={MARKETS}&oddsFormat={ODDS_FORMAT}&apiKey={API_KEY}"
)

OUT_PATH = "data/odds.json"


def now_iso() -> str:
    # Real fetch time, whole seconds, Z suffix
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_odds():
    req = urllib.request.Request(API_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def main():
    fetched_at = now_iso()

    if not API_KEY:
        print("ERROR: ODDS_API_KEY is not set (add it as a repo secret).", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching odds for {SPORT_KEY} at {fetched_at} ...")
    try:
        data = fetch_odds()
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.reason} — not overwriting odds.json", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Fetch failed: {e} — not overwriting odds.json", file=sys.stderr)
        sys.exit(1)

    if not data:
        print("API returned no events (book may not be up yet) — not overwriting.", file=sys.stderr)
        sys.exit(0)

    event = data[0]
    bookmakers = event.get("bookmakers", [])

    # Collect prices per player across books; prefer FanDuel, else median.
    player_prices = {}
    fanduel = {}
    last_updates = []

    for bk in bookmakers:
        if bk.get("last_update"):
            last_updates.append(bk["last_update"])
        for market in bk.get("markets", []):
            if market.get("key") != "outrights":
                continue
            for outcome in market.get("outcomes", []):
                name = outcome.get("name")
                price = outcome.get("price")
                if name is None or price is None:
                    continue
                player_prices.setdefault(name, []).append(price)
                if bk.get("key") == "fanduel":
                    fanduel[name] = price

    final_odds = {}
    for name, prices in player_prices.items():
        final_odds[name] = fanduel[name] if name in fanduel else int(median(prices))

    if not final_odds:
        print("No outright prices found in response — not overwriting.", file=sys.stderr)
        sys.exit(0)

    bookmaker_updated = max(last_updates) if last_updates else ""

    out = {
        "major": MAJOR_LABEL,
        "sport_key": event.get("sport_key", SPORT_KEY),
        "updated": fetched_at,              # legacy mirror so old readers still work
        "fetched_at": fetched_at,           # <-- THE FIX: real run time, always populated
        "bookmaker_updated": bookmaker_updated,
        "source": "fanduel_or_median",
        "odds": final_odds,
    }

    os.makedirs("data", exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    print(f"Wrote {len(final_odds)} players to {OUT_PATH}")
    print(f"  fetched_at        = {fetched_at}")
    print(f"  bookmaker_updated = {bookmaker_updated or '(none provided)'}")


if __name__ == "__main__":
    main()

"""Read-only point-in-time audit using public Research endpoints.

This script never writes to Railway, the Research database, or Production.
It reports prediction quality and a chronological W39 -> W42 replay.
"""
from __future__ import annotations

import concurrent.futures
from collections import defaultdict
from datetime import datetime
import json
import math
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://quantbet-research-production.up.railway.app"
OUTPUT = Path("/tmp/quantbet-forensics-report.json")
EXTRA_LEAGUES = (39, 40, 41, 42, 43, 44, 45, 72, 75, 135, 236, 365, 595)
W39, W42 = "2026-W39", "2026-W42"


def get_json(path: str, params: dict | None = None) -> dict:
    url = BASE + path + ("?" + urlencode(params) if params else "")
    last = None
    for attempt in range(3):
        try:
            req = Request(
                url,
                headers={"User-Agent": "QuantBet-readonly-forensic-v1", "Accept": "application/json"},
            )
            with urlopen(req, timeout=45) as stream:
                return json.load(stream)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            last = exc
            time.sleep(1.0 + attempt)
    raise RuntimeError(f"GET {path} failed: {last}")


def week(row: dict) -> str:
    date = datetime.fromisoformat(row["kickoff_at"].replace("Z", "+00:00"))
    year, iso_week, _ = date.isocalendar()
    return f"{year}-W{iso_week:02d}"


def decided(row: dict) -> bool:
    return row.get("outcome") in ("WIN", "LOSS")


def ret(row: dict) -> float:
    return float(row["odds"]) - 1.0 if row["outcome"] == "WIN" else -1.0


def metric(rows: list[dict]) -> dict:
    rows = [r for r in rows if decided(r)]
    n = len(rows)
    if not n:
        return {"n": 0}
    wins = sum(r["outcome"] == "WIN" for r in rows)
    roi = sum(ret(r) for r in rows) / n
    out = {
        "n": n, "wins": wins, "losses": n - wins,
        "win_pct": round(100 * wins / n, 3),
        "roi_pct": round(100 * roi, 3),
        "avg_odds": round(sum(float(r["odds"]) for r in rows) / n, 4),
    }
    for label, key in (("dc", "model_probability"), ("market", "market_fair_probability")):
        ps = [min(1 - 1e-9, max(1e-9, float(r[key]))) for r in rows]
        ys = [int(r["outcome"] == "WIN") for r in rows]
        out[label] = {
            "mean_p": round(sum(ps) / n, 6),
            "brier": round(sum((p-y)**2 for p, y in zip(ps, ys)) / n, 6),
            "logloss": round(-sum(y * math.log(p) + (1-y) * math.log(1-p) for p, y in zip(ps, ys)) / n, 6),
        }
    out["constant_50"] = {
        "brier": 0.25,
        "logloss": round(math.log(2), 6),
    }
    return out


def odds_bin(odds: float) -> str:
    if odds < 1.8: return "lt1.80"
    if odds < 2.0: return "1.80-1.99"
    if odds < 2.5: return "2.00-2.49"
    if odds < 3.0: return "2.50-2.99"
    return "3.00+"


def rule(row: dict) -> tuple:
    return (row.get("market"), row.get("selection"), odds_bin(float(row["odds"])))


def main() -> None:
    snap = get_json("/research/analytics.json")
    leagues = {
        (int(r["league_id"]), int(r["season"]))
        for r in snap.get("cohorts", {}).get("league_season", [])
        if r.get("league_id") and r.get("season")
    }
    leagues.update((league, season) for league in EXTRA_LEAGUES for season in (2025, 2026))
    print(f"Read-only audit: league-season requests={len(leagues)}", flush=True)

    def fetch(pair: tuple[int, int]) -> tuple[tuple[int, int], list[dict], str | None]:
        league, season = pair
        try:
            response = get_json("/research/analytics/league.json", {"league_id": league, "season": season})
            return pair, response.get("rows", []), None
        except Exception as exc:
            return pair, [], str(exc)[:200]

    records: dict[str, dict] = {}
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for i, (pair, items, error) in enumerate(pool.map(fetch, sorted(leagues)), 1):
            if error:
                failures.append({"scope": pair, "error": error})
            for row in items:
                key = str(row.get("fixture_id") or row.get("evaluation_id"))
                if key and key not in records:
                    records[key] = row
            if i % 40 == 0:
                print(f"Progress: {i}/{len(leagues)} scopes, {len(records)} unique records", flush=True)

    all_rows = list(records.values())
    graded = [r for r in all_rows if decided(r) and r.get("kickoff_at")]
    perweek = defaultdict(list)
    for r in graded:
        perweek[week(r)].append(r)
    a, b = perweek[W39], perweek[W42]
    result = {
        "scope": "public Research league JSON plus explicitly re-read historical blocked league IDs",
        "league_requests": len(leagues),
        "errors": failures,
        "all_rows": len(all_rows),
        "decided_rows": len(graded),
        "whole": metric(graded),
        "weeks": {w: metric(perweek[w]) for w in sorted(perweek)},
    }

    if a and b:
        mean_p = sum(int(r["outcome"] == "WIN") for r in a) / len(a)
        result["simple_w39_winrate_baseline_on_w42"] = {
            "trained_p": round(mean_p, 6),
            "w42_brier": round(sum((mean_p - int(r["outcome"] == "WIN"))**2 for r in b) / len(b), 6),
            "w42_logloss": round(-sum((int(r["outcome"] == "WIN") * math.log(mean_p) + int(r["outcome"] == "LOSS") * math.log(1-mean_p)) for r in b) / len(b), 6),
        }
        w39_groups = defaultdict(list)
        w42_groups = defaultdict(list)
        for r in a: w39_groups[rule(r)].append(r)
        for r in b: w42_groups[rule(r)].append(r)
        selected = sorted(
            (key for key, rows in w39_groups.items() if len(rows) >= 6 and metric(rows)["roi_pct"] > 0),
            key=lambda k: (-len(w39_groups[k]), k),
        )
        forward = [r for r in b if rule(r) in selected]
        result["frozen_w39_profitable_rules_on_w42"] = {
            "rule_count": len(selected),
            "rules": [{"key": key, "train_w39": metric(w39_groups[key]), "forward_w42": metric(w42_groups[key])} for key in selected],
            "forward_total": metric(forward),
            "coverage_pct": round(100 * len(forward) / len(b), 2),
            "warning": "Rules were selected in-sample on W39; this is a forward holdout, not a randomized comparison.",
        }
        overlap = [key for key, rows in w39_groups.items() if key in w42_groups]
        coverage = sum(len(w39_groups[key]) for key in overlap) / len(a)
        adjusted = sum(
            len(w39_groups[key]) / sum(len(w39_groups[k]) for k in overlap)
            * (metric(w42_groups[key])["roi_pct"])
            for key in overlap
        ) if overlap else None
        result["w42_standardized_to_w39_market_selection_odds_mix"] = {
            "overlap_w39_pct": round(100*coverage, 2),
            "comparable_rule_count": len(overlap),
            "w42_mix_adjusted_roi_pct": round(adjusted, 3) if adjusted is not None else None,
            "limitation": "Only common strata; descriptive reweighting, not a causal estimate.",
        }
    result["ev_bands"] = {}
    cuts = ((0.0, 0.15), (0.15, 0.2), (0.2, 0.3), (0.3, float("inf")))
    for low, high in cuts:
        key = f"{low:.2f}-{high:.2f}" if math.isfinite(high) else "0.30+"
        result["ev_bands"][key] = {
            name: metric([r for r in subset if low <= float(r.get("expected_value") or 0) < high])
            for name, subset in (("all", graded), (W39, a), (W42, b))
        }

    group_version = defaultdict(list)
    for r in b: group_version[str(r.get("model_version_id") or "UNKNOWN")].append(r)
    result["w42_model_versions"] = sorted(
        ({"model": k[:26], **metric(rows)} for k, rows in group_version.items()),
        key=lambda x: -x["n"],
    )[:25]
    byleague = defaultdict(list)
    for r in b: byleague[(r.get("league_id"), r.get("competition_name"))].append(r)
    result["w42_league_losses"] = sorted(
        ({"league": str(k), **metric(rows)} for k, rows in byleague.items()),
        key=lambda x: x["roi_pct"] * x["n"],
    )[:25]
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    print("RESULT_JSON_BEGIN")
    compact = {key: result[key] for key in (
        "league_requests", "all_rows", "decided_rows", "whole",
        "simple_w39_winrate_baseline_on_w42",
        "frozen_w39_profitable_rules_on_w42",
        "w42_standardized_to_w39_market_selection_odds_mix",
        "ev_bands", "w42_model_versions", "w42_league_losses",
    ) if key in result}
    print(json.dumps(compact, ensure_ascii=False))
    print("RESULT_JSON_END")
    print(f"Scopes failed: {len(failures)}", flush=True)


if __name__ == "__main__":
    main()

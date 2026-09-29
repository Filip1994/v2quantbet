"""Human-readable GoalLab pick explanations backed by exact numeric evidence."""

from __future__ import annotations

import math
from html import escape
from typing import Any


_METRIC_LABELS = {
    "goals_for": "dati golovi po meču",
    "goals_against": "primljeni golovi po meču",
    "ppg": "bodovi po meču",
    "win": "udeo pobeda",
    "draw": "udeo remija",
    "clean_sheet": "udeo mečeva bez primljenog gola",
    "failed_to_score": "udeo mečeva bez datog gola",
    "btts": "udeo BTTS mečeva",
    "over25": "udeo mečeva sa 3+ gola",
    "goal_difference": "gol-razlika po meču",
    "shots_for": "šutevi po meču",
    "shots_against": "dozvoljeni šutevi po meču",
    "sot_for": "šutevi u okvir po meču",
    "sot_against": "dozvoljeni šutevi u okvir po meču",
    "possession": "posed",
    "corners_for": "korneri po meču",
    "corners_against": "dozvoljeni korneri po meču",
    "pass_accuracy": "tačnost dodavanja",
    "finishing_conversion": "realizacija šuteva u okvir",
    "save_proxy": "odbranjeni udarci — proxy",
    "inside_box_for": "šutevi iz kaznenog prostora",
    "shot_quality_proxy": "proxy kvaliteta šuta",
    "territorial_proxy": "teritorijalni pritisak",
    "set_piece_pressure": "pritisak iz prekida",
}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _fmt(value: Any, digits: int = 2) -> str:
    number = _number(value)
    return "—" if number is None else f"{number:.{digits}f}"


def _pct(value: Any, digits: int = 1) -> str:
    number = _number(value)
    return "—" if number is None else f"{number * 100:.{digits}f}%"


def _pp(value: Any, digits: int = 1) -> str:
    number = _number(value)
    if number is None:
        return "—"
    return f"{number * 100:+.{digits}f} pp"


def _team(prefix: str) -> str:
    return "Domaćin" if prefix == "home" else "Gost"


def human_feature_name(name: str) -> str:
    """Translate common structural feature names into simple Serbian."""
    for prefix in ("home", "away"):
        team = _team(prefix)
        marker = f"{prefix}_"
        if not name.startswith(marker):
            continue
        rest = name[len(marker):]
        for window in (3, 5, 10):
            token = f"l{window}_"
            if rest.startswith(token):
                metric = rest[len(token):]
                label = _METRIC_LABELS.get(metric, metric.replace("_", " "))
                return f"{team}: {label}, poslednjih {window}"
        if rest.startswith("venue_l5_"):
            metric = rest[len("venue_l5_"):]
            label = _METRIC_LABELS.get(metric, metric.replace("_", " "))
            venue = "kod kuće" if prefix == "home" else "u gostima"
            return f"{team}: {label} {venue}, poslednjih 5"
        if rest.startswith("season_"):
            metric = rest[len("season_"):]
            label = _METRIC_LABELS.get(metric, metric.replace("_", " "))
            return f"{team}: {label}, sezona"
        if rest == "rest_days":
            return f"{team}: dani odmora"
        if rest.startswith("matches_last_") and rest.endswith("d"):
            days = rest[len("matches_last_"):-1]
            return f"{team}: broj mečeva u poslednjih {days} dana"
        if rest == "history_match_count":
            return f"{team}: broj istorijskih mečeva u modelu"
        if rest == "season_match_count":
            return f"{team}: broj mečeva ove sezone u uzorku"
        if rest == "standings_rank":
            return f"{team}: mesto na tabeli"
        if rest == "standings_points":
            return f"{team}: bodovi na tabeli"
        if rest == "standings_ppg":
            return f"{team}: bodovi po meču na tabeli"
        if rest == "standings_goal_difference":
            return f"{team}: gol-razlika na tabeli"
        if rest == "unavailable_player_count":
            return f"{team}: nedostupni igrači"
        if rest == "injury_count":
            return f"{team}: povrede"
        if rest == "suspension_count":
            return f"{team}: suspenzije"
        if rest == "manager_tenure_days":
            return f"{team}: dani trenutnog trenera"
        if rest == "matches_under_manager":
            return f"{team}: mečevi pod trenutnim trenerom"
        if rest == "recent_manager_change_flag":
            return f"{team}: skoro promenjen trener"
        if rest.startswith("projected_xi_"):
            metric = rest[len("projected_xi_"):].replace("_", " ")
            labels = {
                "count": "broj projektovanih igrača",
                "rolling rating": "prosečna ocena projektovane postave",
                "shots per90": "šutevi projektovane postave na 90 min",
                "sot per90": "šutevi u okvir projektovane postave na 90 min",
                "key passes per90": "ključna dodavanja projektovane postave na 90 min",
                "goals assists per90": "golovi + asistencije projektovane postave na 90 min",
                "defensive actions per90": "defanzivne akcije projektovane postave na 90 min",
                "duel win rate": "udeo dobijenih duela projektovane postave",
            }
            return f"{team}: {labels.get(metric, metric)}"
        if rest == "attack_opponent_adjusted_l5":
            return f"{team}: napad L5 korigovan kvalitetom protivnika"
        if rest == "defence_opponent_adjusted_l5":
            return f"{team}: odbrana L5 korigovana kvalitetom protivnika"
        if rest == "sot_opponent_adjusted_l5":
            return f"{team}: šutevi u okvir L5 korigovani protivnicima"

    direct = {
        "h2h_goals_per_match_l3": "Međusobni mečevi: prosečno golova, poslednja 3",
        "h2h_goals_per_match_l5": "Međusobni mečevi: prosečno golova, poslednjih 5",
        "h2h_btts_rate_l5": "Međusobni mečevi: BTTS udeo, poslednjih 5",
        "h2h_over25_rate_l5": "Međusobni mečevi: Over 2.5 udeo, poslednjih 5",
        "h2h_sample_size": "Međusobni mečevi: veličina uzorka",
        "standings_rank_differential": "Razlika pozicije na tabeli (domaćin − gost)",
        "standings_points_differential": "Razlika bodova (domaćin − gost)",
        "standings_ppg_differential": "Razlika bodova po meču (domaćin − gost)",
        "standings_goal_difference_differential": "Razlika gol-razlike na tabeli",
        "match_importance_proxy": "Procena važnosti meča iz stanja na tabeli",
        "unavailable_count_differential": "Razlika broja nedostupnih igrača",
        "player_quality_differential": "Razlika ocene projektovanih postava",
        "matchup_goal_attack_x_defence_home": "Domaći napad × gostujuća odbrana",
        "matchup_goal_attack_x_defence_away": "Gostujući napad × domaća odbrana",
        "matchup_sot_attack_x_defence_home": "Domaći šutevi u okvir × gostujuća odbrana",
        "matchup_sot_attack_x_defence_away": "Gostujući šutevi u okvir × domaća odbrana",
        "league_season_goals_per_team_match": "Liga: prosečno golova po timu i meču",
    }
    if name in direct:
        return direct[name]
    if name.endswith("__missing"):
        return f"Nedostaje podatak za: {human_feature_name(name[:-9])}"
    return name.replace("_", " ")


def _market_pick_text(row: dict[str, Any]) -> str:
    market = str(row.get("market_key") or "")
    selection = str(row.get("selection") or "")
    if market == "OU_25":
        return "više od 2.5 gola" if selection == "OVER" else "manje od 2.5 gola"
    if market == "BTTS":
        return "oba tima daju gol" if selection == "YES" else "bar jedan tim ne daje gol"
    line = row.get("line")
    line_text = "" if line is None else f" {line}"
    return f"{market} {selection}{line_text}".strip()


def _raw_features(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("feature_payload")
    if not isinstance(payload, dict):
        return {}
    raw = payload.get("raw_features")
    return raw if isinstance(raw, dict) else {}


def _actual_rank(row: dict[str, Any]) -> tuple[int | None, int | None]:
    payload = row.get("selection_rank_payload")
    if not isinstance(payload, dict):
        return None, None
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return None, _int(payload.get("candidate_count"))
    for item in candidates:
        if not isinstance(item, dict):
            continue
        if (
            str(item.get("market_key") or "") == str(row.get("market_key") or "")
            and str(item.get("selection") or "") == str(row.get("selection") or "")
            and str(item.get("bookmaker_name") or "") == str(row.get("bookmaker_name") or "")
        ):
            return _int(item.get("rank")), _int(payload.get("candidate_count"))
    return None, _int(payload.get("candidate_count"))


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _context_lines(row: dict[str, Any]) -> list[str]:
    raw = _raw_features(row)
    lines: list[str] = []

    hgf = _number(raw.get("home_l5_goals_for"))
    hga = _number(raw.get("home_l5_goals_against"))
    agf = _number(raw.get("away_l5_goals_for"))
    aga = _number(raw.get("away_l5_goals_against"))
    if None not in (hgf, hga, agf, aga):
        lines.append(
            "Forma golova L5: domaćin daje "
            f"{hgf:.2f} i prima {hga:.2f} gola po meču; gost daje "
            f"{agf:.2f} i prima {aga:.2f}."
        )

    hs = _number(raw.get("home_l5_shots_for"))
    hst = _number(raw.get("home_l5_sot_for"))
    ass = _number(raw.get("away_l5_shots_for"))
    ast = _number(raw.get("away_l5_sot_for"))
    if None not in (hs, hst, ass, ast):
        lines.append(
            "Šutevi L5: domaćin "
            f"{hs:.2f} šuteva / {hst:.2f} u okvir po meču; gost "
            f"{ass:.2f} / {ast:.2f}."
        )

    hvenue = _number(raw.get("home_venue_l5_goals_for"))
    aven = _number(raw.get("away_venue_l5_goals_for"))
    if hvenue is not None or aven is not None:
        parts = []
        if hvenue is not None:
            parts.append(f"domaćin kod kuće daje {hvenue:.2f}")
        if aven is not None:
            parts.append(f"gost u gostima daje {aven:.2f}")
        lines.append("Venue forma L5: " + "; ".join(parts) + " gola po meču.")

    hrank = _number(raw.get("home_standings_rank"))
    arank = _number(raw.get("away_standings_rank"))
    hpoints = _number(raw.get("home_standings_points"))
    apoints = _number(raw.get("away_standings_points"))
    if None not in (hrank, arank, hpoints, apoints):
        lines.append(
            "Tabela: domaćin je "
            f"{hrank:.0f}. sa {hpoints:.0f} bodova, gost {arank:.0f}. sa {apoints:.0f}."
        )

    injury_coverage = _number(raw.get("injury_coverage_flag"))
    if injury_coverage == 1.0:
        hu = _number(raw.get("home_unavailable_player_count"))
        au = _number(raw.get("away_unavailable_player_count"))
        hi = _number(raw.get("home_injury_count"))
        ai = _number(raw.get("away_injury_count"))
        hsusp = _number(raw.get("home_suspension_count"))
        asusp = _number(raw.get("away_suspension_count"))
        if None not in (hu, au):
            lines.append(
                "Izostanci: domaćin ima "
                f"{hu:.0f} nedostupnih ({_fmt(hi, 0)} povreda, {_fmt(hsusp, 0)} suspenzija); "
                f"gost {au:.0f} ({_fmt(ai, 0)} povreda, {_fmt(asusp, 0)} suspenzija)."
            )

    hrest = _number(raw.get("home_rest_days"))
    arest = _number(raw.get("away_rest_days"))
    h7 = _number(raw.get("home_matches_last_7d"))
    a7 = _number(raw.get("away_matches_last_7d"))
    if hrest is not None or arest is not None:
        parts = []
        if hrest is not None:
            parts.append(f"domaćin odmara {hrest:.1f} dana")
        if arest is not None:
            parts.append(f"gost {arest:.1f} dana")
        if h7 is not None and a7 is not None:
            parts.append(f"mečevi u 7 dana: {h7:.0f}–{a7:.0f}")
        lines.append("Odmor i raspored: " + "; ".join(parts) + ".")

    h2h_n = _number(raw.get("h2h_sample_size"))
    h2h_goals = _number(raw.get("h2h_goals_per_match_l5"))
    h2h_o25 = _number(raw.get("h2h_over25_rate_l5"))
    h2h_btts = _number(raw.get("h2h_btts_rate_l5"))
    if h2h_n is not None and h2h_n > 0:
        parts = [f"uzorak {h2h_n:.0f}"]
        if h2h_goals is not None:
            parts.append(f"{h2h_goals:.2f} gola po meču")
        if h2h_o25 is not None:
            parts.append(f"Over 2.5 {_pct(h2h_o25)}")
        if h2h_btts is not None:
            parts.append(f"BTTS {_pct(h2h_btts)}")
        lines.append("Međusobni mečevi: " + "; ".join(parts) + ".")

    home_rating = _number(raw.get("home_projected_xi_rolling_rating"))
    away_rating = _number(raw.get("away_projected_xi_rolling_rating"))
    home_ga90 = _number(raw.get("home_projected_xi_goals_assists_per90"))
    away_ga90 = _number(raw.get("away_projected_xi_goals_assists_per90"))
    if home_rating is not None or away_rating is not None:
        parts = []
        if home_rating is not None:
            parts.append(
                f"domaća projektovana postava ocena {home_rating:.2f}"
                + ("" if home_ga90 is None else f", G+A/90 {home_ga90:.2f}")
            )
        if away_rating is not None:
            parts.append(
                f"gostujuća ocena {away_rating:.2f}"
                + ("" if away_ga90 is None else f", G+A/90 {away_ga90:.2f}")
            )
        lines.append("Igrači iz istorije nastupa: " + "; ".join(parts) + ".")

    return lines


def _contributions(
    row: dict[str, Any],
    contract: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(contract, dict):
        return []
    params = contract.get("parameters")
    means = contract.get("feature_means")
    scales = contract.get("feature_scales")
    if not isinstance(params, dict) or not isinstance(means, dict) or not isinstance(scales, dict):
        return []

    model_names = tuple(params.get("model_feature_names") or ())
    base_names = tuple(params.get("base_feature_names") or ())
    beta_home = tuple(params.get("beta_home") or ())
    beta_away = tuple(params.get("beta_away") or ())
    if not model_names or len(beta_home) != len(model_names) or len(beta_away) != len(model_names):
        return []

    raw = _raw_features(row)
    base_set = set(base_names)
    rows: list[dict[str, Any]] = []
    for index, name_raw in enumerate(model_names):
        name = str(name_raw)
        raw_value: float | None = None
        standardized = 0.0
        missing = False
        training_mean: float | None = None
        training_scale: float | None = None

        if name in base_set:
            raw_value = _number(raw.get(name))
            training_mean = _number(means.get(name))
            training_scale = _number(scales.get(name))
            if (
                raw_value is not None
                and training_mean is not None
                and training_scale is not None
                and abs(training_scale) > 1e-12
            ):
                standardized = (raw_value - training_mean) / training_scale
            else:
                missing = raw_value is None
                standardized = 0.0
        elif name.endswith("__missing"):
            base = name[:-9]
            missing = _number(raw.get(base)) is None
            standardized = 1.0 if missing else 0.0
        else:
            continue

        home_contribution = standardized * float(beta_home[index])
        away_contribution = standardized * float(beta_away[index])
        rows.append(
            {
                "feature": name,
                "label": human_feature_name(name),
                "raw_value": raw_value,
                "training_mean": training_mean,
                "training_scale": training_scale,
                "standardized": standardized,
                "home_eta_contribution": home_contribution,
                "away_eta_contribution": away_contribution,
                "impact": abs(home_contribution) + abs(away_contribution),
                "missing": missing,
            }
        )
    return sorted(rows, key=lambda item: (-float(item["impact"]), str(item["feature"])))


def build_goal_pick_explanation(
    row: dict[str, Any],
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return deterministic Serbian explanation using only persisted numeric evidence."""
    model_p = _number(row.get("model_probability"))
    market_p = _number(row.get("market_probability"))
    edge = _number(row.get("edge"))
    ev = _number(row.get("expected_value"))
    odds = _number(row.get("odds"))
    home_xg = _number(row.get("expected_home_goals"))
    away_xg = _number(row.get("expected_away_goals"))
    total_xg = None if home_xg is None or away_xg is None else home_xg + away_xg
    home = str(row.get("home_team") or "domaćin")
    away = str(row.get("away_team") or "gost")
    pick_text = _market_pick_text(row)

    summary = (
        f"Model je za {home} – {away} izabrao „{pick_text}“. "
        f"Procena modela je {_pct(model_p)}, a tržišna procena iz dve kvote {_pct(market_p)}. "
        f"Razlika je {_pp(edge)}. Na kvoti {_fmt(odds)} očekivana vrednost je {_pct(ev)}."
    )
    if home_xg is not None and away_xg is not None:
        summary += (
            f" Model očekuje {home_xg:.2f} gola za domaćina i {away_xg:.2f} za gosta, "
            f"ukupno {total_xg:.2f}."
        )

    pick_policy = str(
        row.get("pick_policy_version")
        or row.get("policy_version")
        or "NEPOZNATA_POLITIKA"
    )
    if pick_policy == "GOALLAB_DC_PLUS_PICK_POLICY_V4":
        gate = (
            "Po aktuelnom V4 pravilu, pik ulazi u završni izbor samo ako ima pozitivan EV "
            "i prođe filtere za raspon kvote, svežinu kvote i dovoljno vremena do početka. "
            f"Ovde je EV {_pct(ev)}, a edge {_pp(edge)}. Edge pomaže pri rangiranju, "
            "ali više nije obavezan prag od 3 procentna poena."
            if ev is not None and ev > 0
            else "Ovaj zapis po V4 pravilu nema pozitivan EV i ne bi bio kvalifikovan za novi pik."
        )
    else:
        gate = (
            f"Ovaj pik je sačuvan po istorijskom pravilu {pick_policy}. "
            f"Za njega su zabeleženi EV {_pct(ev)} i edge {_pp(edge)}; "
            "objašnjenje ispod koristi tačno podatke koji su bili sačuvani uz taj pik."
        )

    rank, candidate_count = _actual_rank(row)
    ranking = None
    if candidate_count:
        ranking = (
            f"Među {candidate_count} kandidata koji su prošli filtere, ovaj izbor je rangiran "
            f"#{rank or 1}. Redosled odlučivanja je: EV, zatim edge, modelska verovatnoća i kvota."
        )

    contributions = _contributions(row, contract)
    top = [item for item in contributions if float(item["impact"]) > 1e-12][:10]
    payload = row.get("feature_payload")
    payload = payload if isinstance(payload, dict) else {}
    model_feature_names = tuple(payload.get("model_feature_names") or ())

    notes = [
        "Brojevi ispod su tačno oni koji su bili dostupni modelu u trenutku odluke.",
        "Kvote nisu ulaz u DC+ procenu golova; koriste se posle modela da se izračunaju market probability, edge i EV.",
    ]
    if payload.get("target_match_live_stats_used") is False:
        notes.append("Nisu korišćene live statistike sa utakmice koja tek treba da počne.")

    return {
        "summary": summary,
        "gate": gate,
        "ranking": ranking,
        "context_lines": _context_lines(row),
        "top_contributions": top,
        "all_contributions": contributions,
        "active_feature_count": len(model_feature_names) or len(contributions),
        "notes": notes,
    }


def render_goal_pick_note_html(
    row: dict[str, Any],
    contract: dict[str, Any] | None,
    *,
    detail_href: str,
) -> str:
    """Render a compact notes popover from exact persisted evidence."""
    explanation = build_goal_pick_explanation(row, contract)
    context = "".join(
        f"<li>{escape(str(line))}</li>"
        for line in explanation["context_lines"][:7]
    )
    contribution_rows: list[str] = []
    for item in explanation["top_contributions"][:6]:
        if item["missing"]:
            detail = "podatak nedostaje; model koristi eksplicitni missing flag"
        else:
            detail = (
                f"vrednost {_fmt(item['raw_value'])}; "
                f"prosek na trening podacima {_fmt(item['training_mean'])}; "
                f"odstupanje od proseka {float(item['standardized']):+.2f}; "
                f"uticaj na procenu golova domaćina {float(item['home_eta_contribution']):+.3f}, "
                f"gosta {float(item['away_eta_contribution']):+.3f}"
            )
        contribution_rows.append(
            f"<li><b>{escape(str(item['label']))}</b>: {escape(detail)}</li>"
        )
    contributions = "".join(contribution_rows)
    ranking = (
        ""
        if not explanation["ranking"]
        else f'<p class="note-ranking">{escape(str(explanation["ranking"]))}</p>'
    )
    return (
        '<details class="pick-note goal-pick-note">'
        '<summary title="Prosto objašnjenje zašto je ovaj pik izabran">📝</summary>'
        '<div class="note-popover goal-note-popover">'
        '<b>Zašto je izabran ovaj pik</b>'
        f'<p>{escape(str(explanation["summary"]))}</p>'
        f'<p>{escape(str(explanation["gate"]))}</p>'
        f"{ranking}"
        + (
            '<h4>Najvažniji brojevi koje je model video</h4><ul>' + context + "</ul>"
            if context
            else ""
        )
        + (
            '<h4>Šta je najviše guralo model ka ovom izboru</h4><ul>'
            + contributions
            + "</ul>"
            if contributions
            else (
                "<p>Za ovaj zapis nema dovoljno model-contract podataka "
                "za tačan decomposition.</p>"
            )
        )
        + f'<a class="note-detail-link" href="{escape(detail_href, quote=True)}">'
        "Otvori sve brojke i sve varijable →</a>"
        + "</div></details>"
    )

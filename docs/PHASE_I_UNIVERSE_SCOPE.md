# QuantBet — Phase I Universe Scope

## Purpose

This document defines the initial fixture universe for Phase I: the daily bulletin and subsequent pre-kickoff monitoring.

The scope is intentionally conservative. The system should first operate on competitions with sufficiently reliable senior-level football data and should exclude competition types that introduce unnecessary heterogeneity or data-quality risk.

## Included by default

The initial universe includes senior football competitions that are not excluded below. This may include:

- top divisions and established lower divisions outside the explicitly excluded tiers;
- domestic league competitions;
- international senior competitions;
- established senior club and national-team competitions;
- other senior competitions for which fixture, odds, and lifecycle data are reliable.

The inclusion decision must ultimately be based on normalized competition metadata, not on free-text display names alone.

## Explicit exclusions

The Phase I fixture universe must exclude:

### 1. African competitions

Exclude African leagues and competitions from the initial bulletin universe.

### 2. Youth and junior competitions

Exclude all youth/junior competitions, including but not limited to:

- U19;
- U20;
- U21;
- U23;
- U17 and younger;
- youth, junior, academy, reserve-youth and similar competitions.

The exclusion must use competition metadata and robust name classification where metadata is incomplete.

### 3. Women's football

Exclude women's football from the entire QuantBet football universe, including production and QuantLab research. The classifier uses normalized competition and team metadata and recognizes common localized women's-football markers plus women-only competition names such as NWSL, WSL, Liga F, WE League, Damallsvenskan, Toppserien and Kvindeliga.

The exclusion is a hard gate before fixture-specific odds, context, standings or statistics acquisition. Global date-shard fixture discovery remains provider-wide and is filtered locally.

### 4. English fourth tier and below

Exclude:

- English League Two, the fourth tier of the English league system;
- all lower English divisions and non-league tiers below it.

The initial scope may retain the English Premier League, Championship and League One, subject to normal data-quality checks.

### 5. German fourth tier and below

Exclude:

- German fourth tier and lower competitions;
- Regionalliga and lower levels;
- other competitions identified as fourth tier or below in the German league hierarchy.

The initial scope may retain the German Bundesliga, 2. Bundesliga and 3. Liga, subject to normal data-quality checks.

### 6. Explicit competition blocklist

Exclude specifically blocked competitions whose production behavior is not accepted even when
the provider classifies them as senior leagues.

Current explicit exclusion:

- Czech-Republic `3. liga - MSFL`.

### 7. Cup competitions

Exclude all cup and knockout competitions from Phase I, including but not limited to:

- domestic cups;
- national cups;
- league cups;
- super cups;
- continental cups and knockout tournaments;
- competitions classified as cup, knockout or similar.

League competitions and senior international league-style competitions may remain eligible when their normalized competition type is not cup/knockout.

## Classification requirements

The fixture-universe filter must:

1. prefer structured provider metadata such as country, league name, league type, league level and competition category;
2. normalize case, accents, punctuation and whitespace;
3. use explicit competition IDs or configuration where provider metadata is ambiguous;
4. fail closed for ambiguous competitions rather than silently including them in the bulletin;
5. preserve the exclusion reason for every rejected fixture;
6. be deterministic and unit-tested;
7. remain separate from quant calculations and bookmaker quote normalization.

## Required rejection reasons

Rejected fixtures should expose a stable reason code, for example:

- `EXCLUDED_AFRICAN_COMPETITION`;
- `EXCLUDED_YOUTH_COMPETITION`;
- `EXCLUDED_WOMENS_FOOTBALL`;
- `EXCLUDED_ENGLISH_TIER_4_OR_LOWER`;
- `EXCLUDED_GERMAN_TIER_4_OR_LOWER`;
- `EXCLUDED_CUP_COMPETITION`;
- `EXCLUDED_EXPLICIT_COMPETITION`;
- `AMBIGUOUS_COMPETITION_METADATA`.

## Phase I policy

This scope applies to the initial bulletin and its monitoring lifecycle. It does not permanently prohibit future research or expansion. Any later expansion must be supported by explicit configuration, data-quality validation and a separate evaluation of model behavior by competition.

# Task 005 — Canonical Football Universe Ban Policy

Status: ready for Codex implementation.

## Objective

Unify fixture-universe eligibility across Production, Research and every QuantLab lab behind
one canonical hard-ban policy.

The same fixture metadata must produce the same hard-ban result in:

- Production fixture discovery / eligibility;
- Research universe admission;
- QuantLab fixture discovery;
- GoalLab;
- CornerLab;
- CardLab.

Research remains a superset of Production only after this shared universe gate. QuantLab
may keep lab-specific market/model requirements after the shared gate, but it must not
re-admit a fixture rejected by the canonical ban policy.

## Canonical policy

Remove the existing broad regional, tier and cup bans unless explicitly retained below.

### Hard-banned categories

1. Women's football.
2. Youth football:
   - U5-U23 / Under-age competitions;
   - youth / junior competitions.
3. Academy, reserve, B-team, second-team and amateur football.
4. Friendly matches and friendly competitions:
   - club friendlies;
   - international friendlies;
   - provider variants/aliases that clearly represent friendlies.
5. National-team / representative football:
   - senior national teams;
   - youth national teams are already rejected by the youth rule, but must remain rejected;
   - international tournaments and qualifiers involving national teams are out of universe,
     even when the competition itself is not named "Friendly".
6. All football whose competition country is Serbia.
7. All football whose competition country is Bosnia and Herzegovina.
8. All football whose competition country is North Macedonia / Macedonia.

Country matching must be normalized and cover provider aliases such as:

- Serbia;
- Bosnia, Bosnia and Herzegovina, Bosnia-Herzegovina;
- North Macedonia, Macedonia, Macedonia FYR / FYR Macedonia.

### Explicitly allowed / no longer globally banned

Unless another retained hard-ban rule above applies, allow:

- Australia, including A-League and other senior club competitions;
- Africa;
- Asia and Far East;
- Middle East;
- cups and knockout club competitions;
- lower English tiers;
- lower German tiers;
- Czech 3. liga - MSFL;
- Brazil Serie B (API-Football league ID 72);
- Brazil Serie C (ID 75);
- Russia First League (ID 236);
- Sweden Division 2 - Södra Svealand (ID 595);
- other senior club leagues previously excluded only by regional/tier/cup policy.

The old global league-ID blacklist {72, 75, 236, 595} must therefore be removed.

Australia must have an explicit positive regression case proving it remains eligible.

## Single source of truth

Create one obvious, auditable policy module for hard bans. Suggested location:

`src/h2h/domain/competition_bans.py`

The exact filename may differ, but the result must satisfy all of the following:

1. Country bans are defined in one named constant/registry.
2. Explicit league-ID bans, when added in the future, are defined in one named constant/registry.
3. Category bans / classifiers are discoverable from the same module or directly adjacent
   canonical helpers.
4. Production and QuantLab must import/reuse this policy instead of maintaining duplicated
   Africa / Asia / Far-East / tier / cup lists.
5. No lab may contain a hidden country or league hard-ban list that changes universe
   eligibility independently.
6. The module must carry a version constant, e.g. `FOOTBALL_UNIVERSE_POLICY_V2`.
7. Add a short documentation section identifying this exact file as the place where future
   league/country bans are added.

This task is specifically designed so future removals can be made by editing a single
registry rather than hunting through Production, Research, GoalLab, CornerLab and CardLab.

## Required classification semantics

### Women

Preserve the existing localized women's-football detection, including team-name evidence.

### Youth / reserve / amateur

Use normalized competition and team metadata. Preserve robust detection for:

- Uxx / Under xx;
- youth / junior;
- academy;
- reserve / reserves;
- B / II / second-team suffixes where provider data identifies a reserve side;
- amateur.

Avoid false-positive bans from arbitrary letters inside normal senior team names.

### Friendlies

Add a canonical friendly classifier. It must cover at minimum:

- `Friendly`;
- `Friendlies`;
- `Club Friendlies`;
- `International Friendlies`;
- equivalent provider competition type/name variants after normalization.

Do not infer "friendly" merely because a match has no standings.

### National / representative teams

National-team rejection must not depend only on the word `World` or on one competition
name. Use provider metadata available in the current fixture adapter and deterministic
competition/team classification.

The implementation must document the exact evidence used to identify representative
football and fail closed only when the metadata positively identifies it as such.
Ordinary international club competitions must remain eligible unless another hard-ban
rule applies.

Examples that must remain eligible:

- UEFA Champions League club matches;
- UEFA Europa League club matches;
- Copa Libertadores club matches;
- AFC Champions League club matches involving eligible clubs;
- Australian senior club football.

Examples that must be rejected:

- Serbia national team vs another national team;
- Brazil vs Argentina senior international;
- World Cup / continental national-team tournament fixtures;
- international friendlies;
- club friendlies.

## Remove legacy restrictions

Refactor or delete behavior corresponding solely to:

- `EXCLUDED_AFRICAN_COMPETITION`;
- `EXCLUDED_ASIAN_COMPETITION`;
- `EXCLUDED_ENGLISH_TIER_4_OR_LOWER`;
- `EXCLUDED_GERMAN_TIER_4_OR_LOWER`;
- generic cup/knockout exclusion;
- Czech MSFL explicit exclusion;
- QuantLab `_AFRICA_COUNTRIES`;
- QuantLab `_FAR_EAST_COUNTRIES`;
- any CardLab/CornerLab/GoalLab universe behavior that differs from the canonical hard-ban
  decision;
- global blacklist IDs 72/75/236/595.

Historical reason codes may remain readable for old persisted evidence, but new decisions
must use the new canonical policy semantics.

## Parity / alignment test

Add a dedicated cross-system regression test whose purpose is policy drift detection.

Suggested file:

`tests/domain/test_universe_policy_parity.py`

The test matrix must run the same normalized fixture cases through the Production canonical
scope and QuantLab shared scope and assert the same hard-ban boolean/reason family.

Minimum cases:

### MUST REJECT

- women's league;
- women's team in otherwise generic competition;
- U19;
- reserve/B-team;
- amateur;
- club friendly;
- international friendly;
- senior national-team competitive match;
- Serbia senior club league;
- Serbian cup;
- Bosnia and Herzegovina senior club league;
- Bosnian cup;
- North Macedonia senior club league;
- Macedonian cup.

### MUST ALLOW

- Australia A-League;
- Australia senior cup club match if not a friendly;
- Japan J1 League;
- Saudi Pro League;
- South Africa Premier Soccer League;
- Egypt Premier League;
- Brazil Serie B / league ID 72;
- Brazil Serie C / league ID 75;
- Russia First League / league ID 236;
- Sweden Division 2 - Södra Svealand / league ID 595;
- England League Two;
- English non-league senior club competition;
- Germany Regionalliga;
- Germany Oberliga senior club competition;
- Czech 3. liga - MSFL;
- senior domestic club cup;
- UEFA Champions League club match;
- Copa Libertadores club match.

The parity test must fail if a future Production/Research change is not inherited by
QuantLab or vice versa.

## Research contract

Research admission must continue to originate after the canonical Production universe
eligibility boundary. A hard-banned fixture must never appear as a normal Research
candidate.

Add/update a Research regression proving:

`canonical hard ban -> no Research universe candidate`.

## QuantLab contract

QuantLab may still perform global/date-shard provider discovery, but hard-banned fixtures
must be rejected locally before fixture-specific odds/context/statistics spend wherever
possible.

Every lab must use the same canonical hard-ban result.

GoalLab, CornerLab and CardLab may add lab-specific capability/market gates after that
decision; those are not universe bans and must not be represented as such.

## Observability

Make bans visible in system diagnostics.

At minimum:

1. Persist/log canonical universe policy version.
2. Preserve a stable rejection reason for rejected fixtures.
3. Add a small documentation table listing active hard bans and their registry source.
4. If the existing dashboard/health surface already exposes discovery rejection counts,
   group them by canonical reason; do not create a large new UI solely for this task.

Suggested stable reason families:

- `BANNED_WOMENS_FOOTBALL`;
- `BANNED_YOUTH_OR_DEVELOPMENT`;
- `BANNED_FRIENDLY`;
- `BANNED_NATIONAL_TEAM`;
- `BANNED_COUNTRY`;
- `AMBIGUOUS_COMPETITION_METADATA` only where existing fail-closed metadata requirements
  are still necessary for safe classification.

For `BANNED_COUNTRY`, audit output should include the normalized matched country.

## Documentation updates

Update all documentation that currently describes Africa, Asia/Far East, cup or tier bans,
including at minimum:

- `docs/PHASE_I_UNIVERSE_SCOPE.md`;
- `QuantLab/ARCHITECTURE.md`;
- relevant GoalLab / CornerLab / CardLab README files;
- `QuantLab/WORKLOG.md`.

Documentation must point to the canonical policy registry as the only place to add future
hard league/country bans.

## Non-goals

Do not change:

- model mathematics;
- EV/edge ranking;
- staking/bankroll;
- bookmaker policy;
- settlement semantics;
- one-pick-per-fixture rules;
- GoalLab/CornerLab/CardLab model-specific feature or qualification logic.

This task changes only fixture-universe hard-ban policy and its observability.

## Definition of done

- One canonical hard-ban source is used by Production, Research and QuantLab.
- Active bans are exactly:
  - women;
  - youth/junior/development/reserve/B-team/amateur;
  - friendlies;
  - national/representative teams;
  - Serbia;
  - Bosnia and Herzegovina;
  - North Macedonia.
- Australia is explicitly allowed.
- Africa/Asia/Far East/Middle East are not regionally banned.
- Cups and lower tiers are not generically banned.
- IDs 72/75/236/595 are no longer globally banned.
- Cross-system parity matrix passes.
- Existing focused scope/discovery tests are updated.
- Full pytest and Ruff pass.
- Documentation clearly identifies the one future-ban registry.
- No production model, bankroll or settlement behavior changes.

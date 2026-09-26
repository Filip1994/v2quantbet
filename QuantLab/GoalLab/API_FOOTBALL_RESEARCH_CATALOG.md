# GoalLab — API-Football Research Catalog

Status: active research reference.

This document is the canonical catalog of API-Football data that QuantBet may use for
GoalLab DC+, CardLab, CornerLab and adjacent football research.

## Provider capacity

QuantBet currently operates against a **75,000 requests/day football provider envelope**.

QuantLab calls remain attributable under the `quantlab_context` request category, but
there is no separate 1,000/day QuantLab hard cap. All football services share the same
provider envelope and durable request telemetry.

Budget size does **not** remove the need for:

- request deduplication;
- persistent capture watermarks;
- endpoint-specific TTLs;
- coverage checks;
- timestamp/leakage controls;
- canonical market semantics.

Those controls protect data quality rather than API spend.

## Coverage-first rule

Before spending feature-specific requests, use league/season coverage metadata when
available. Coverage flags indicate whether a competition/season supports:

- events;
- lineups;
- fixture statistics;
- player statistics;
- standings;
- players;
- top scorers / assists / cards;
- injuries;
- predictions;
- odds.

A positive flag means the provider aims to collect that data; it does not guarantee every
fixture has every field. Missing/null values remain missing and must never be fabricated.

## Endpoint catalog

### /fixtures

Primary fixture identity and schedule source.

Useful raw fields include:

- fixture ID;
- UTC kickoff;
- status;
- venue;
- referee when available;
- league / season / round;
- home / away team IDs;
- full-time and period scores for completed matches.

Derived research variables:

- rest days;
- matches in last 7 / 14 / 21 days;
- fixture congestion;
- consecutive home/away run;
- season/round progress;
- historical goals for/against;
- recent points/form;
- first-half scoring profiles when period scores are available.

### /fixtures?date=...

Global date-shard discovery source.

Use:

- build the independent QuantLab fixture universe;
- avoid inheriting production competition filters;
- discover all competitions first, then apply market/coverage logic locally.

### /fixtures?id=... and /fixtures?ids=...

Fixture detail source. Provider supports batched fixture IDs where documented.

Potentially exposes or links:

- referee;
- venue;
- events;
- lineups;
- statistics;
- players.

QuantLab must snapshot the availability time of any pre-match fact before using it.

### /fixtures/headtohead

Historical meetings between two team IDs.

Potential DC+ features:

- recency-weighted H2H goals;
- H2H BTTS rate;
- H2H Over 2.5 rate;
- H2H home/away scoring;
- H2H result distribution;
- H2H goal-difference trend.

H2H is a low-sample feature block and must be regularized heavily.

### /fixtures/statistics

Per-team match statistics for played/live fixtures.

Documented statistics include:

- shots on target;
- shots off target;
- total shots;
- blocked shots;
- shots inside the box;
- shots outside the box;
- fouls;
- corner kicks;
- offsides;
- ball possession;
- yellow cards;
- red cards;
- goalkeeper saves;
- total passes;
- accurate passes;
- pass accuracy.

Derived historical features:

- rolling shots for/against;
- rolling SOT for/against;
- shot differential;
- SOT differential;
- shot share;
- SOT share;
- shots inside-box share;
- finishing conversion;
- goals per SOT;
- opponent conversion allowed;
- goalkeeper save rate;
- possession mean/differential;
- pass volume;
- pass accuracy;
- territorial/control proxy;
- corners for/against/share;
- fouls and card intensity.

API-Football does **not** provide a native documented xG value in this fixture statistics
set. Any xG-like feature built from shots, SOT, box location and penalties must be named a
**shot-quality/xG proxy**, not xG.

### /fixtures/events

Chronological match events.

Documented event types include:

- goals;
- own goals;
- penalties;
- missed penalties;
- yellow cards;
- red cards;
- second-yellow/red;
- substitutions;
- assists.

Derived research features:

- scoring timing distributions;
- first-goal timing;
- red-card exposure;
- penalty frequency;
- substitution timing;
- game-state adjusted historical stats.

Post-kickoff target-match events are never eligible for a pre-match prediction.

### /fixtures/lineups

Starting XI, formation, bench and coaching staff.

Typical availability is shortly before kickoff, commonly around 20–60 minutes depending on
competition/provider timing.

Derived DC+ late-model features:

- starting-XI continuity;
- regular-starter count;
- changes from previous XI;
- formation;
- formation change;
- bench depth;
- lineup attacking contribution;
- lineup defensive contribution;
- lineup minutes/goals/assists share;
- lineup average recent rating.

Lineups belong to a separate **late pre-match layer** because they are not reliably
available hours before kickoff.

### /fixtures/players

Per-player match performance for completed/live fixtures.

Documented fields include:

- minutes;
- position;
- rating;
- substitute indicator;
- shots / SOT;
- goals;
- assists;
- total/key passes;
- pass accuracy;
- tackles;
- interceptions;
- duels;
- dribbles;
- fouls;
- cards;
- penalty statistics.

Historical derived features:

- rolling player rating;
- attacking contribution;
- creator/key-pass contribution;
- defensive contribution;
- goalkeeper form;
- projected XI strength;
- replacement-quality delta.

### /teams/statistics

Team season aggregate endpoint by league/season/team, with optional historical date
boundary where supported.

Useful fields include:

- matches played;
- wins/draws/losses;
- goals for/against;
- form;
- clean sheets;
- failed-to-score;
- home/away splits;
- goal timing/distributions where returned.

Derived features:

- season PPG;
- season GF/GA per match;
- home GF/GA;
- away GF/GA;
- clean-sheet rate;
- failed-to-score rate;
- form score;
- team scoring rate relative to league average.

Historical queries must be bounded to facts available before the target fixture.

### /standings

League/table state.

Useful raw fields include:

- rank;
- points;
- goal difference;
- played;
- wins/draws/losses;
- home/away record;
- recent form.

Derived variables:

- points per game;
- rank percentile;
- points gap to leader;
- points gap to title/promotion/continental zone;
- points gap to relegation;
- table pressure;
- mathematical importance;
- home/away table strength.

### /injuries

Pre-match injuries and suspensions. Fixture-scoped queries are preferred for target-match
availability.

Raw information includes:

- player;
- team;
- type: injury/suspension;
- reason;
- fixture context.

Derived variables:

- unavailable count;
- injury count;
- suspension count;
- starter absences;
- missing minutes share;
- missing goals share;
- missing assists share;
- missing attacking contribution;
- missing defensive contribution;
- goalkeeper absence flag;
- availability-strength differential.

### /sidelined

Historical injury/suspension record for player or coach.

Derived variables:

- injury recurrence;
- days unavailable;
- recent return;
- durability;
- long-term absence history.

Use only if historical timestamp semantics can be reconstructed safely.

### /players

Player profile and season statistics.

Potential inputs:

- appearances;
- starts;
- minutes;
- goals;
- assists;
- shots;
- SOT;
- passes;
- key passes;
- pass accuracy;
- dribbles;
- tackles;
- interceptions where returned;
- fouls;
- cards;
- penalties;
- injured flag;
- position.

Derived team/lineup aggregates:

- weighted attack strength;
- weighted creator strength;
- weighted defensive strength;
- squad depth;
- replacement quality;
- contribution concentration.

### /players/squads

Current squad membership when available.

Derived uses:

- squad depth;
- position depth;
- roster continuity;
- lineup candidate set.

### Top-player endpoints

Where coverage exists:

- top scorers;
- top assists;
- top yellow cards;
- top red cards.

These can provide league-relative player strength/risk features, though direct /players
data is preferable for model reproducibility.

### /coachs

Current coach and career/team history.

Derived variables:

- recent manager change;
- days under current coach;
- matches under coach;
- coach continuity;
- new-manager flag.

### /transfers

Player/team transfer history.

Derived variables:

- squad turnover;
- incoming/outgoing count;
- recent key-player departure;
- recent key-player arrival;
- early-season continuity score.

Transfer fees are strings and should not be treated as clean numeric market values without
a separate parser/validation layer.

### /predictions

API-Football's own model output.

Documented outputs include:

- winner;
- win-or-draw;
- predicted goals;
- Under/Over suggestion;
- home/draw/away percentages;
- attack comparison;
- defence comparison;
- Poisson comparison;
- form;
- H2H comparison.

This is **not** part of structural DC+ Core. It belongs in a separately versioned
provider-prediction ensemble experiment to avoid hiding an external model inside DC+.

### /odds

Pre-match bookmaker markets.

QuantLab currently ingests one all-market fixture response and retains Bet365 and 1xBet.

Research uses:

- complete two-sided quotes;
- de-vig probabilities;
- bookmaker disagreement;
- price movement;
- line movement;
- opening/current/closing observations where captured;
- market availability by league/market.

Odds are not structural DC+ Core inputs. They belong in a separately evaluated
**DC+ Market-Aware** ensemble so structural skill can be measured independently.

### /odds/live

In-play odds.

Not part of the current pre-match GoalLab DC+ contract. If used later, it must live in a
separate live/in-play experiment because target timing and leakage rules are different.

### /leagues

Competition/season metadata and feature coverage flags.

This endpoint should be used as a coverage registry so research acquisition can skip
unsupported endpoint calls without reintroducing arbitrary league allowlists.

### Teams / venues

Team identity, country, venue/stadium metadata.

Potential low-priority features:

- venue continuity;
- neutral-venue flag where derivable;
- stadium/surface context when coverage is reliable.

## Provider update cadence / acquisition guidance

Provider documentation currently describes approximately:

- standings: hourly;
- injuries: every ~4 hours;
- coaches: daily;
- teams/statistics: twice daily;
- predictions: hourly;
- pre-match odds: around every 3 hours at provider level, with limited provider-side
  history;
- lineups: normally appear shortly before kickoff;
- fixture statistics / fixture players: update during live play.

QuantBet may poll more frequently than provider publication cadence when it needs a durable
timestamped observation series, but identical payloads should still be deduplicated.

## Timestamp safety classes

### Class A — structural historical

Safe when computed only from matches completed before target decision time:

- goals/results;
- fixture statistics;
- player historical performance;
- H2H;
- prior lineups;
- prior manager tenure.

### Class B — target pre-match

Safe only if captured before decision time:

- standings;
- injuries/suspensions;
- target referee;
- target fixture context;
- target lineups;
- target odds.

### Class C — target live/post-match

Never eligible for a pre-match DC+ decision:

- target-match events after kickoff;
- target fixture statistics after kickoff;
- target player match statistics after kickoff;
- final result.

## Market-driven CardLab / CornerLab rule

CardLab and CornerLab no longer use a domestic Top-10 competition allowlist.

The research universe is market-driven:

1. discover fixtures globally;
2. request all-market pre-match odds within the shared provider budget;
3. classify returned markets as GOAL / CORNER / CARD / UNCLASSIFIED;
4. retain CARD/CORNER evidence wherever the provider actually publishes a supported market;
5. request CardLab context only when CARD evidence exists;
6. run a shadow decision only when the market has explicit canonical semantics.

A broad raw market can be collected without automatically being eligible for a PICK.
Ambiguous settlement semantics remain research-only until explicitly canonicalized.

## Canonical source references

Provider reference:

- https://www.api-football.com/
- https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide

The repository implementation, persisted raw provider payloads and timestamped QuantLab
observations remain authoritative for any specific experiment.

# API-Football historical training contract

## Scope

The production historical-results boundary acquires one explicit API-Football
league, season and timezone-aware interval. `ApiFootballTrainingScope`
normalizes its endpoints to UTC and defines the logical interval as
`[start_at, end_at)`. The client sends the covering inclusive provider calendar
dates plus `league`, `season`, `status=FT` and `timezone=UTC`; the acquisition
layer applies the exact half-open timestamp filter after normalization.

There is no default league, season or lookback period.

The encoded provider contract is based on the current API-Football v3
documentation: its standard envelope defines `errors`, `results`, `paging` and
`response`; `/fixtures` supports timezone and date-range filtering and returns
top-level score plus halftime/full-time/extra-time/penalty breakdowns; and `FT`,
`AET` and `PEN` are distinct completed statuses. The provider's completed-match
tutorial likewise queries `/fixtures` with explicit league, season and status.
See the official [v3 getting-started guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide)
and [completed-fixture tutorial](https://www.api-football.com/news/post/how-to-get-all-fixtures-data-from-one-league).

## Complete-response requirement

Acquisition checks the API-Football envelope before adapting records. Provider
errors, malformed `response`/`results`/`paging` fields, a result-count mismatch,
or any paging state other than `current=1, total=1` aborts the operation. This
bounded implementation does not collect later pages and never returns a first
page as a complete dataset. A valid complete response containing zero records
returns a valid empty dataset; transport and validation failures raise instead.

## Completed-match and score policy

Only exact `fixture.status.short == "FT"` is accepted. `AET`, `PEN`, live,
postponed, cancelled, awarded and every other status fail closed even though the
request itself specifies `status=FT`.

For an accepted FT fixture, the ordinary result is read from top-level
`goals.home` / `goals.away` and must exactly equal
`score.fulltime.home` / `score.fulltime.away`. Both pairs must contain explicit
nonnegative, non-boolean integers. `score.extratime` and `score.penalty` must be
objects whose `home` and `away` values are both present and null. The adapter
never adds period fields and therefore cannot
turn extra-time goals or shootout kicks into Dixon-Coles goals. The record
retains the accepted semantic as
`goals=score.fulltime;extratime.home/away=null;penalty.home/away=null` for
auditability.

Fixture identity uses the existing API-Football canonical allocator. Fixture,
league, season and ordered team IDs must be positive non-boolean integers; home
and away IDs must differ. Returned league and season must equal the requested
scope. Kickoff must be an offset-bearing ISO timestamp and is normalized to UTC.
Team names are not identity inputs.

## Atomic normalization and duplicates

Every response item is normalized and validated before the dataset is returned,
including provider calendar spillover outside the logical interval. Records are
deduplicated by canonical API-Football fixture identity. Identical normalized
duplicates collapse to one; any disagreement in a record field aborts the whole
acquisition. Conflict detection occurs before the half-open window filter.
Successful records are immutable and sorted by UTC kickoff, then numeric
provider fixture ID.

## Provenance-aware fitting

`ApiFootballTrainingDataset` has no supported caller constructor. The sole
supported provenance-minting path starts at
`build_trusted_api_football_historical_results(settings)`. That production
factory accepts no transport, base URL, response loader, adapter or normalizer;
it internally selects the repository's `UrllibJsonTransport`, daily-budget
wrapper and canonical `https://v3.football.api-sports.io` endpoint. It returns
a frozen acquisition service whose client configuration is not exposed through
the supported API. Only that service can create the internal dataset authority,
and only after complete response validation, strict FT adaptation, scope checks
and conflict handling. The resulting team namespace is internally derived and
read-only as `api-football`.

`ApiFootballClient` intentionally remains a general, injectable low-level
client for unit tests and other non-proven use. Likewise,
`normalize_api_football_historical_response()` deterministically applies the
strict envelope, score, scope and conflict rules to caller-supplied payloads.
Neither an injected client nor those normalized records can construct a trusted
dataset or enter `fit_api_football_dixon_coles()`. This is an application trust
boundary, not a cryptographic guarantee against private-internal access,
monkey-patching or a hostile process.

`fit_api_football_dixon_coles()` accepts only that trusted dataset and supplies
its derived namespace to the unchanged `DixonColesModel.fit()` API. Callers
still provide the existing fitting configuration (`reference_time`, `xi`,
`ridge`, `min_matches`) but cannot select or repeat the namespace at this
boundary. The fitted model therefore exposes
`team_id_namespace == "api-football"` and is namespace-compatible with an
authoritative API-Football prediction target.

This contract does not add model artifacts, scheduled retraining, durable
training/prediction provenance, AET/PEN support, cross-provider mapping or
production fixture-to-model orchestration.

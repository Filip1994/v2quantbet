# Codex Verification Report

## Scope and environment

- **Checked at:** 2026-09-15 13:43:21 +02:00 (Europe/Belgrade)
- **Repository / branch:** `Filip1994/v2quantbet`, `main`
- **Checked commit:** `4d61b8bc33274af82a0c072d951c9e01d189677c` — *Test pick registration identity and timestamp validation*
- **Working tree before adding this report:** clean and aligned with `origin/main`.
- **Python requested by project:** `.python-version` contains `3.11`; `pyproject.toml` requires `>=3.11`.
- **Python used:** CPython 3.11.16 (managed by uv).
- **uv:** 0.12.14 (`ce3bd7931`, 2026-09-14).

The project is a `src/`-layout Python package (`h2h-v2`) with 312 collected
pytest tests, SQL migrations, SQLite and PostgreSQL persistence implementations,
and three GitHub Actions workflows (`ci.yml`, `api-football-odds.yml`, and
`api-football-discovery.yml`).  `pyproject.toml` locks runtime numerical and
PostgreSQL dependencies through `uv.lock`; its `dev` extra provides pytest and
ruff.

## Commands executed

```text
git clone --branch main --single-branch https://github.com/Filip1994/v2quantbet.git v2quantbet
python --version                         # not on initial PATH
uv --version                             # not on initial PATH
uv sync --locked --extra dev
uv run python --version
uv run python -m ruff check .
uv run python -m pytest
uv run python -m pytest --basetemp .verification-tmp/pytest
```

The first pytest invocation used pytest's default Windows temporary directory
and exposed an access-denied environment problem.  It produced 10 setup errors
unrelated to the tests themselves.  The second invocation uses an explicit
writable base temp directory and is the authoritative test result below.

## Dependency installation

`uv sync --locked --extra dev` **passed**.  It downloaded CPython 3.11.16,
created `.venv`, resolved 14 locked packages, built `h2h-v2`, and installed all
dependencies.  The initial environment did not have a usable Python launcher or
uv on PATH; uv was installed solely to perform this requested verification.

## Ruff

`uv run python -m ruff check .` **failed: 7 findings**.  No autofix was run.
All findings are in test files, not production modules:

| Count | Location | Finding | Classification |
| ---: | --- | --- | --- |
| 1 | `tests/domain/test_pick_registration.py:62` | `DTZ001`: naive `datetime()` | Test-quality lint failure |
| 4 | `tests/integration/test_postgres_quote_history_integration.py:12-17` | `RUF100`: unused `# noqa: E402` | Stale test lint directives |
| 2 | `tests/integration/test_postgres_quote_history_integration.py:63,82` | `SIM117`: nested context managers | Test-style lint failure |

## Test suite

Authoritative command: `uv run python -m pytest --basetemp .verification-tmp/pytest`

| Collected | Passed | Failed | Skipped | Errors |
| ---: | ---: | ---: | ---: | ---: |
| 312 | 288 | 18 | 6 | 0 |

The six skipped tests are exactly the PostgreSQL integration tests.  The
initial, unmodified command required by the task had the intermediate result
`278 passed, 18 failed, 6 skipped, 10 errors`; each error was a
`PermissionError: [WinError 5] Access is denied` while pytest attempted to scan
`C:\Users\User\AppData\Local\Temp\pytest-of-User`.  Re-running with a
writable base temp made all 10 affected tests pass, so this is classified as an
**environment problem**, not an application failure.

### Reproduced failures

The failure summaries below retain the relevant exception chain and assertion.
They are grouped where one cause produces several tests.  No source, test, or
configuration change was made during this verification.

| Tests | Reproduced summary | Classification / production assessment |
| --- | --- | --- |
| `tests/domain/test_canonical_quote.py::test_unsupported_market_is_rejected` | `CanonicalQuote(..., market="CORRECT_SCORE")` raises `TypeError: market must be a Market`; the test expects any `ValueError`. | **Stale/incorrect test expectation**, not a reproduced production bug. The current domain contract requires a `Market` enum before validation. |
| `tests/odds/test_api_football_adapter.py::test_rejects_unsupported_api_football_bookmaker`; `...::test_rejects_api_football_bookmaker_name_mismatch` | `resolve_api_football_bookmaker` correctly raises `UnsupportedBookmakerError`, but `ApiFootballQuoteAdapter.adapt()` catches it through `ValueError` and rethrows `QuoteNormalizationError: invalid API-Football odds payload: ...`. Tests expect `UnsupportedBookmakerError`. | **Potential production/API-contract regression.** The rejection is correct, so bookmaker mapping is enforced; however, callers cannot catch the documented policy exception at this adapter boundary. Requires an intentional contract decision before any change. |
| `tests/odds/test_api_football_adapter.py::test_accepts_valid_numeric_odd_forms[2]` | With input `odd=2`, adapted value is `2.0`; assertion expects `2.2`. | **Incorrect parametrized test**, not a production bug. An integer 2 cannot validly normalize to 2.2. |
| `tests/odds/test_api_football_ingestion_adapter.py::test_ingests_api_football_response_into_canonical_quotes` | Test fixture sends API-Football bookmaker id 7 / `William Hill`; mapping rejects it with `QuoteNormalizationError` wrapping `UnsupportedBookmakerError: unsupported API-Football bookmaker id: 7`. | **Stale test fixture** under the current API-Football allowlist; no evidence that mapping itself is wrong. |
| `tests/odds/test_http.py::test_timeout_must_be_positive` | Code raises `ValueError: timeout must be a positive number`; test regex expects `greater than zero`. | **Stale assertion text**, not a production bug: timeout zero is rejected correctly. |
| `tests/odds/test_provider_adapter.py::test_normalizing_adapter_returns_canonical_quote`; `...::test_normalizing_adapter_preserves_normalizer_validation`; `tests/odds/test_snapshot_builder.py::test_build_market_snapshot_adapts_all_payloads`; `...::test_build_market_snapshot_rejects_incomplete_market` | Shared test payload contains `bookmaker_name="Example Bookmaker"`; generic normalization rejects it: `QuoteNormalizationError: unsupported bookmaker: 'example bookmaker'; supported values: ['1xbet', 'bet365', 'superbet']`. The intended odd/incomplete-market assertions are never reached. | **Stale test fixtures / masked tests**, not a reproduced production bug. The existing bookmaker policy tests pass. |
| `tests/persistence/test_postgres_quote_history.py::test_series_for_fixture_reconstructs_rows`; `...::test_append_snapshots_rejects_unknown_series`; `...::test_append_and_read_snapshot`; `...::test_append_snapshots_is_idempotent_for_matching_snapshot`; `...::test_append_snapshots_rejects_conflicting_snapshot` | `FakeCursor` assumes `series_for_fixture` has four query parameters and assumes `series_id` lookup receives a hashable scalar. Production code now uses a one-parameter fixture query and `ANY(%s)` with a list. Consequences are `IndexError: tuple index out of range` and `TypeError: unhashable type: 'list'` in the fake cursor. | **Outdated unit-test double**, not evidence of a PostgreSQL production bug. Actual PostgreSQL integration remains unexecuted (see below). |
| `tests/persistence/test_quote_history.py::test_append_snapshots_preserves_history_and_is_idempotent`; `...::test_snapshots_for_series_filters_other_series`; `...::test_append_snapshots_is_atomic_on_conflict` | In-memory repository rejects the tests' duplicate natural identities with `QuoteHistoryConflictError: conflicting observation for snapshot natural identity` or `conflicting definition for quote series natural identity`; final test then mismatches expected `snapshot ID` wording. | **Tests inconsistent with current quote-history natural-identity semantics.** Not classified as a production bug: current in-memory behavior matches the documented PostgreSQL uniqueness shape, but parity still requires an integration run. |

## Specific consistency checks

- **Bookmaker mapping / API-Football odds path:** Existing `test_bookmaker_policy.py` (11 tests) and most API-Football adapter/client tests passed.  The failures show strict mapping rejection works.  The exception-type wrapping described above is the sole potential boundary-contract issue.
- **CanonicalQuote:** 33 of 34 canonical-quote tests passed.  The sole failure is an exception-class expectation rather than acceptance of an invalid market.
- **Ingestion and SQLite persistence:** SQLite persistence, migrations, application construction, quote ingestion, HTTP transport behavior, and API-Football client tests passed after the temp-directory environment correction.
- **PostgreSQL quote history:** Unit tests using an obsolete fake connection fail; actual integration tests were skipped, so real-database parity is not verified.
- **PickRegistration:** All six tests passed.  The latest commit's new timezone-aware validation test is also the source of the one Ruff `DTZ001` test lint finding.
- **CI:** `.github/workflows/ci.yml` correctly provisions PostgreSQL 16, supplies `QUANTBET_TEST_DATABASE_URL`, runs the locked sync, Ruff, and pytest.  In its current checked state, CI should fail at least on the seven Ruff findings and the reproduced 18 test failures until the code/test-contract discrepancies are intentionally resolved.

## PostgreSQL status

PostgreSQL 16 integration tests were **not executed**.  This workstation has no
`docker` command, no detected `postgres*` service, no `psql`, and no
`QUANTBET_TEST_DATABASE_URL`.  Therefore no database was started and the six
tests in `tests/integration/test_postgres_quote_history_integration.py` were
skipped for their declared reason.  This is an **environment/configuration
blocker**, not a test failure or a claim about PostgreSQL correctness.

## Conclusion and next step

The repository is **not currently fully verified**: dependency installation
works, 288 tests pass, but Ruff fails and 18 tests reproducibly fail.  Most
failures are stale fixtures, assertions, or fake-database test infrastructure
after stricter bookmaker and natural-identity contracts; they should not be
silently changed without reviewing the intended contract.  One item needs
explicit attention as a possible production API regression: whether
`ApiFootballQuoteAdapter` must preserve `UnsupportedBookmakerError` rather than
wrap it as `QuoteNormalizationError`.

The concrete next step is to provision PostgreSQL 16 (matching CI), set
`QUANTBET_TEST_DATABASE_URL`, and run the six integration tests.  Then review
and intentionally update the stale test fixtures/doubles and decide the
adapter exception contract before modifying any production code.  No claim is
made that the system is fully correct merely because the passing subset passed.

## Triage / remediation

**Remediated at:** 2026-09-15 14:23:45 +02:00 (Europe/Belgrade)

The initial failure count was triaged against the current implementation and
its contracts.  Each row below accounts for one of the original 18 failed test
nodes.  No bookmaker allowlist, numeric bookmaker identity, quote-history
natural identity, mathematical model, or CI workflow was changed.

| Initial failure | Status and category | Root cause / remediation | Production code changed | Relevant test |
| --- | --- | --- | --- | --- |
| `test_unsupported_market_is_rejected` | Fixed — **A: stale/incorrect test** | `CanonicalQuote` explicitly requires a `Market`; the test now asserts its documented `TypeError`. | No | `test_untyped_market_is_rejected` |
| `test_rejects_unsupported_api_football_bookmaker` | Fixed — **D: genuine production bug** | Policy rejection was unintentionally caught through the `ValueError` base class and wrapped. | Yes: re-raise `UnsupportedBookmakerError`. | Existing policy-boundary regression test |
| `test_rejects_api_football_bookmaker_name_mismatch` | Fixed — **D: genuine production bug** | Same unintended catch-and-wrap behavior as the unsupported-ID case. | Yes: same minimal re-raise. | Existing policy-boundary regression test |
| `test_accepts_valid_numeric_odd_forms[2]` | Fixed — **A: stale/incorrect test** | Integer input `2` correctly normalizes to `2.0`, not `2.2`; parameterized expected values now express each input. | No | `test_accepts_valid_numeric_odd_forms` |
| `test_ingests_api_football_response_into_canonical_quotes` | Fixed — **B: stale test fixture** | Fixture used rejected id 7 / William Hill despite the documented allowlist and mapping. It now uses mapped id 8 / Bet365. | No | `test_ingests_api_football_response_into_canonical_quotes` |
| `test_timeout_must_be_positive` | Fixed — **A: stale/incorrect test** | Runtime correctly rejects zero; only its asserted message had drifted to `positive number`. | No | `test_timeout_must_be_positive` |
| `test_normalizing_adapter_returns_canonical_quote` | Fixed — **B: stale test fixture** | Generic fixture used non-allowlisted `Example Bookmaker`, preventing the test from exercising normalization. | No | `test_normalizing_adapter_returns_canonical_quote` |
| `test_normalizing_adapter_preserves_normalizer_validation` | Fixed — **B: stale test fixture** | Same invalid fixture masked the intended odds validation assertion. | No | `test_normalizing_adapter_preserves_normalizer_validation` |
| `test_build_market_snapshot_adapts_all_payloads` | Fixed — **B: stale test fixture** | Snapshot fixture used a rejected bookmaker instead of an allowlisted canonical name. | No | `test_build_market_snapshot_adapts_all_payloads` |
| `test_build_market_snapshot_rejects_incomplete_market` | Fixed — **B: stale test fixture** | Same rejected fixture prevented evaluation of incomplete-market behavior. | No | `test_build_market_snapshot_rejects_incomplete_market` |
| `test_series_for_fixture_reconstructs_rows` | Fixed — **C: obsolete fake/mock** | `FakeCursor` assumed a four-parameter natural lookup while production now performs a one-parameter fixture query. | No | `test_series_for_fixture_reconstructs_rows` |
| `test_append_snapshots_rejects_unknown_series` | Fixed — **C: obsolete fake/mock** | `FakeCursor` did not model the repository's batched `series_id = ANY(%s)` lookup. | No | `test_append_snapshots_rejects_unknown_series` |
| `test_append_and_read_snapshot` | Fixed — **C: obsolete fake/mock** | Fake did not model the full snapshot natural-key read after insert. | No | `test_append_and_read_snapshot` |
| `test_append_snapshots_is_idempotent_for_matching_snapshot` | Fixed — **C: obsolete fake/mock** | Same `ANY(%s)` fake mismatch prevented idempotency behavior from being reached. | No | `test_append_snapshots_is_idempotent_for_matching_snapshot` |
| `test_append_snapshots_rejects_conflicting_snapshot` | Fixed — **C: obsolete fake/mock** | Fake was updated for the current query contract; its assertion now matches the production `snapshot ID` conflict contract. | No | `test_append_snapshots_rejects_conflicting_snapshot` |
| `test_append_snapshots_preserves_history_and_is_idempotent` | Fixed — **A: stale/incorrect test** | Two observations accidentally shared the documented snapshot natural key. The second now uses a distinct capture time. | No | `test_append_snapshots_preserves_history_and_is_idempotent` |
| `test_snapshots_for_series_filters_other_series` | Fixed — **A: stale/incorrect test** | The second series reused the documented series natural identity. It now uses `Selection.UNDER`. | No | `test_snapshots_for_series_filters_other_series` |
| `test_append_snapshots_is_atomic_on_conflict` | Fixed — **A: stale/incorrect test** | The batch first collided on natural identity, masking its intended snapshot-ID atomicity check. Its first candidate now has a unique capture time. | No | `test_append_snapshots_is_atomic_on_conflict` |

### Adapter exception contract decision

`UnsupportedBookmakerError` propagation is an established contract, not an
unresolved design choice.  The allowlist document requires rejection before a
quote enters the canonical model, and the policy-boundary tests were introduced
with the API-Football mapping specifically to assert this exception type.  The
adapter's broad `ValueError` handler accidentally captured that policy error.
`ApiFootballQuoteAdapter.adapt()` now re-raises `UnsupportedBookmakerError` and
continues to translate malformed payload and mapping errors into
`QuoteNormalizationError`.

### Final verification

Commands run after remediation:

```text
uv run python -m pytest [changed-area targets] --basetemp .verification-tmp/targeted
uv run python -m ruff check .
uv run python -m pytest --basetemp .verification-tmp/pytest
```

| Check | Result |
| --- | --- |
| Targeted changed-area tests | `101 passed, 6 skipped` |
| Ruff | `All checks passed!` |
| Full pytest suite | `306 passed, 6 skipped, 0 failed, 0 errors` |
| PostgreSQL integration | Not executed: all six tests skipped because `QUANTBET_TEST_DATABASE_URL` is unset and no local PostgreSQL/Docker service is available. |

The only remaining blocker is real PostgreSQL 16 execution.  The local pytest
run also emitted a non-failing `PytestCacheWarning` because this environment
cannot write `.pytest_cache`; it does not affect collection or test outcomes.

## Observation-identity regression remediation — 2026-09-15

Base: `c934d8f6791f5c03025f83cdeb20b42f52f3d861`.
Branch: `codex/postgres-observation-identity`; reviewer approval required before merge.
Implementation: `cea53a990c602c9d53d7a62ec64d8c62c92ef359`.

Classification F was statically confirmed: migration 002 removes `captured_at`
from snapshot uniqueness, but the regressed adapter still targeted four columns.
The canonical identity is `(series_id, observed_at, source)`. Both repositories
now use it, preserve original capture provenance on semantic replay, and reject
changed odds/incompatible reused IDs. Migrations remain unchanged.

This supersedes earlier claims above that capture-time-separated fixtures matched
the documented snapshot identity. Those earlier runs did not verify the fully
migrated database. Integration bootstrap now uses the normal migration runner,
including 002, rather than manually executing only 001.

Actual local executions (Python 3.11.16, pytest 9.1.1):

| Execution | Actual result |
| --- | --- |
| Initial targeted persistence/migration tests | 44 passed, 4 setup errors: missing parent of external pytest basetemp; environment issue, not code failures |
| Same targets after creating the parent directory | 48 passed |
| Ruff before full run | All checks passed |
| Full suite, once | 356 passed, 1 failed, 15 skipped, 0 errors; 372 collected |
| Final targeted tests, including corrected ingestion test | 51 passed |
| Final Ruff after test correction | All checks passed |

The full-run failure was
`tests/use_cases/test_quote_history.py::test_changed_odd_creates_new_snapshot_when_capture_changes`.
It expected a changed odd at the same provider observation time to become a new
row merely because capture time changed. The repository correctly raised
`QuoteHistoryConflictError: conflicting observation for snapshot natural identity`
from `append_snapshots()`, called by `QuoteHistoryIngestionService.ingest()`.
This stale test was rewritten to expect conflict and preserve the first row.
It passes in the final targeted run. The local full suite was NOT rerun; do not
reinterpret its recorded result as an all-green final run.

Commands:

```text
uv run python -m pytest tests/persistence/test_quote_history.py tests/persistence/test_postgres_quote_history.py tests/persistence/test_migrations.py --basetemp <external-temp>/targeted -o cache_dir=<external-temp>/cache
uv run python -m ruff check .
uv run python -m pytest --basetemp <external-temp>/full -o cache_dir=<external-temp>/cache
uv run python -m pytest tests/persistence/test_quote_history.py tests/persistence/test_postgres_quote_history.py tests/persistence/test_migrations.py tests/use_cases/test_quote_history.py --basetemp <external-temp>/targeted-final -o cache_dir=<external-temp>/cache
uv run python -m ruff check .
```

`<external-temp>` was `C:/Users/User/Documents/ChatGPT/fudbal/quantbet-observation-remediation`.
Local `QUANTBET_TEST_DATABASE_URL` was unset and no PostgreSQL Windows service was
found. No PostgreSQL/Docker provisioning or Railway operation was performed.
All 15 local integration cases were skipped. Fake-cursor tests do not validate
PostgreSQL constraint inference. Draft PR #2 uses the existing PostgreSQL 16 CI
workflow; its observed result follows.

### Real PostgreSQL CI verification

On 2026-09-15 at 17:24 UTC, [CI run 35000997862](https://github.com/Filip1994/v2quantbet/actions/runs/35000997862)
for draft PR #2 / implementation head `cea53a990c602c9d53d7a62ec64d8c62c92ef359`
completed successfully. Job `104489067044` logs show PostgreSQL **16.15**, Python
3.11.16, Ruff **All checks passed**, and **372 passed, 0 failed, 0 skipped, 0 errors**.
All **15 real PostgreSQL integration cases passed**, including migration-chain
and final-schema assertions, fresh insertion, semantic replay, conflicts and
atomic rollback. This establishes the tested fully migrated PostgreSQL behavior;
it does not establish concurrent-writer coverage or live Railway verification.
The subsequent documentation-only commit does not alter the verified code/tests.

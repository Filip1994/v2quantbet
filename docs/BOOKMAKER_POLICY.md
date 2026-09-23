# QuantBet — Bookmaker Policy

## Production best-price universe

Production compares only Bet365 (`8`), 1xBet (`11`) and Superbet (`34`). One unfiltered
API-Football request can return all three without tripling budget use; normalization rejects
every other bookmaker. Quotes are comparable only for the same fixture, market, selection,
source and settlement semantics. Highest executable decimal odds win, with provider ID as a
deterministic tie-breaker.

The winner receives a mandatory bookmaker-specific final refresh. Unavailable, incomplete,
stale or no-longer-playable prices fall back to the next ranked approved bookmaker. Initial
and final observations remain in append-only history; registered bookmaker and Entry never
change afterward.

## 1. Allowlist

QuantBet may ingest, retain, compare, and display betting quotes only from the following bookmakers:

- `superbet`
- `1xbet`
- `bet365`

These are the only bookmakers approved for the Serbia operating context.

## 2. Enforcement rules

- The allowlist is a hard boundary, not a recommendation.
- A quote from a bookmaker outside the allowlist must be rejected before it can enter the canonical quote, market snapshot, decision, pick, or dashboard projection.
- The system must not silently substitute an unapproved bookmaker when an approved bookmaker has no available quote.
- Missing approved-bookmaker coverage must be represented as missing data; it must never be filled with an invented or unapproved price.
- Every persisted quote and pick reference must retain the normalized bookmaker identifier and the original source/provenance.
- Adding a bookmaker requires an explicit product and risk decision, followed by implementation, tests, and documentation.

## 3. Normalization

Bookmaker identifiers must be normalized before allowlist evaluation. Normalization should be deterministic and should not broaden the allowlist through fuzzy matching.

Recommended canonical identifiers:

| Display name | Canonical ID |
|---|---|
| Superbet | `superbet` |
| 1xBet | `1xbet` |
| Bet365 | `bet365` |

Unknown, empty, malformed, or ambiguous bookmaker identifiers are rejected.

## 4. Dashboard implication

The dashboard may display betting references only when the underlying quote belongs to an allowlisted bookmaker. It must show the bookmaker identity alongside the odds checkpoint and must not present an external bookmaker as an actionable reference if it is outside this policy.

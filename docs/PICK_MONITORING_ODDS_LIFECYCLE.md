# Pick monitoring, odds lifecycle, and Daily Bulletin

## Bookmaker continuity

Monitoring refreshes the bookmaker frozen on each registered pick. Pick odds, current
same-bookmaker, closing same-bookmaker and CLV therefore remain one continuous series. Best
current is a separate read-only comparison across the approved bookmakers and never rewrites
Entry, Closing, CLV, settlement, exposure or stake.

Task #11 extends durable `registered_picks`; it does not reinterpret Task #10 Entry.

## Odds checkpoints

- **Opening** is the first valid quote actually captured for Entry's exact series and source,
  ordered by `captured_at`, `observed_at`, then `snapshot_id`. It is derived from immutable
  quote history.
- **Entry** is exactly `registered_picks.entry_snapshot_id`.
- **Current** is the latest valid pre-match observation, ordered by `observed_at`,
  `captured_at`, then `snapshot_id`. Freshness is a separate `FRESH`/`STALE` quality.
- **Closing** exists only after explicit finalization. It is either an immutable snapshot
  reference or an explicit `NO_VALID_QUOTE`/`STALE_QUOTE` outcome with no invented price.

The cutoff is the persisted fixture observation's `kickoff_at` selected by finalization and
is exclusive. Both quote timestamps must precede the cutoff and the contemporaneous fixture
observation known at capture must describe an approved pre-match state. Source is pinned to
Entry. A finalized Current is pinned to the finalization candidate and Closing never moves.

## Monitoring lifecycle

The only states are `REGISTERED -> MONITORING -> CLOSED_FOR_ODDS`. `REGISTERED` is the Task 10
pick before a monitoring row exists. PostgreSQL stores a mutable state projection and the
append-only `MONITORING_STARTED` and `ODDS_CLOSED` transition facts.

Quote insertion and finalization use the same transaction advisory lock derived from the
selected series. Finalization stores one immutable fact. Restart reconciliation starts missing
monitoring rows and finalizes overdue picks from PostgreSQL; browser state is irrelevant.

## Daily Bulletin

The Bulletin reads actual registered picks only. Membership is based on `registered_at` in the
configured IANA timezone (`Europe/Belgrade` for V1), using local midnight inclusive through the
next local midnight exclusive. Zone conversion handles DST. No publication table, ranking,
classification, selection, settlement, P&L, or CLV is introduced.

## Configuration

Task #11 requires a complete lifecycle configuration:

- `QUANTBET_PICK_MONITOR_INTERVAL_SECONDS`
- `QUANTBET_CURRENT_MAX_AGE_SECONDS`
- `QUANTBET_CLOSING_MAX_AGE_SECONDS`
- `QUANTBET_BULLETIN_TIMEZONE`

The three positive duration values are pinned when monitoring starts. Partial configuration
fails closed. The V1 cutoff offset is zero.

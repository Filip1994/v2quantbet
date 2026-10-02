# CardLab referee history collection

CardLab needs five completed referee matches with pre-decision yellow and red card statistics before it can evaluate a shadow pick. API-Football returns referee names with a country suffix in some older seasons (`Espen Eskas, Norway`) and without it in newer seasons (`Espen Eskas`). History matching uses the name before the comma and ignores case and surrounding spaces.

The collector first searches the upcoming fixture's league and up to three prior seasons. It also scans completed fixtures by UTC date across competitions, newest dates first. A day is marked complete only after every API page has been processed. The scan stores fixture and referee context for completed matches with a known referee. Existing targeted statistics backfill then requests card statistics only for referees on current CardLab candidates. Feature snapshots are refreshed when a referee's complete sample grows.

The default scan window is 1,100 days and the collector processes 12 previously unscanned days per cycle. Progress is durable in `quantlab_referee_day_scans`. Configure with:

- `QUANTBET_QUANTLAB_CARD_REFEREE_HISTORY_LOOKBACK_DAYS` (default `1100`)
- `QUANTBET_QUANTLAB_CARD_REFEREE_PRIOR_SEASONS` (default `3`, zero disables prior-season scans)
- `QUANTBET_QUANTLAB_CARD_REFEREE_DAYS_PER_CYCLE` (default `12`)
- `QUANTBET_QUANTLAB_CARD_REFEREE_SCOPES_PER_CYCLE` (default `24`)
- `QUANTBET_QUANTLAB_CARD_REFEREE_STATS_PER_CYCLE` (default `128`)

A statistics observation with missing yellow or red cards does not by itself satisfy the referee sample requirement. For matches where the provider supplies both yellow counts but omits a red count, the collector also fetches the card event timeline. It accepts the canonical 1xBet card total only when the event yellow count agrees with fixture statistics. An event backed match then counts toward the referee sample. Targeted statistics backfill can retry other incomplete matches after `QUANTBET_QUANTLAB_CARD_REFEREE_STATS_RETRY_SECONDS` (default one day), and prioritizes fixtures with no previous statistics request before retries. The statistics cycle cap also bounds event requests separately.

To check progress, count rows in `quantlab_referee_day_scans` and group `quantlab_card_feature_snapshots` by `referee_sample_size`. CardLab V5's decision reasons should move beyond `INSUFFICIENT_REFEREE_HISTORY` only when snapshots reach at least five complete referee matches. More history does not guarantee a value pick.


## Public-web referee enrichment

CardLab V4 adds a low-rate StatBunker referee profile source on top of the existing
API-Football fixture/statistics ledger. API-Football remains the fixture identity
and timestamp backbone; public-web data is supplementary raw referee evidence.

The web source is deliberately restricted to the five major domestic leagues:

- England Premier League
- Spain La Liga
- Italy Serie A
- Germany Bundesliga
- France Ligue 1

Each scrape is persisted in append-only `quantlab_referee_web_captures` and
`quantlab_referee_web_profiles` rows. Feature construction only reads captures
whose `captured_at <= decision_at`, preserving the same no-leakage contract as
the API-backed evidence.

The scraper collects the public season referee table: appearances, home cards,
away cards, yellow cards, second-yellow cards, red cards, yellow cards per match
and cards per match. CardLab aggregates available current/prior-season rows into
web referee rates and adds `web_referee_cards_per_match` as an independent raw
anchor.

CardLab V7 fails closed for new V4 snapshots:

- unsupported league -> `UNSUPPORTED_REFEREE_WEB_LEAGUE`
- fewer than 10 web referee matches -> `INSUFFICIENT_REFEREE_WEB_HISTORY`
- 10+ web referee matches -> normal raw-stat line evaluation can continue

EV, edge and odds remain diagnostic ledger fields and are not PICK gates.

Configuration:

- `QUANTBET_QUANTLAB_REFEREE_WEB_ENABLED` (default `true`)
- `QUANTBET_QUANTLAB_REFEREE_WEB_TIMEOUT_SECONDS` (default `10`)
- `QUANTBET_QUANTLAB_CARD_REFEREE_WEB_REFRESH_SECONDS` (default `21600`)
- `QUANTBET_QUANTLAB_CARD_REFEREE_WEB_SEASONS` (default `3`)

League/season source IDs are validated against page content before data is
accepted. A stale or repurposed source page therefore fails closed and leaves the
existing API-Football referee evidence untouched.

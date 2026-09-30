# CardLab referee history collection

CardLab needs five completed referee matches with pre-decision yellow and red card statistics before it can evaluate a shadow pick. API-Football returns referee names with a country suffix in some older seasons (`Espen Eskas, Norway`) and without it in newer seasons (`Espen Eskas`). History matching uses the name before the comma and ignores case and surrounding spaces.

The collector first searches the upcoming fixture's league and up to three prior seasons. It also scans completed fixtures by UTC date across competitions, newest dates first. A day is marked complete only after every API page has been processed. The scan stores fixture and referee context for completed matches with a known referee. Existing targeted statistics backfill then requests card statistics only for referees on current CardLab candidates. Feature snapshots are refreshed when a referee's complete sample grows.

The default scan window is 1,100 days and the collector processes 12 previously unscanned days per cycle. Progress is durable in `quantlab_referee_day_scans`. Configure with:

- `QUANTBET_QUANTLAB_CARD_REFEREE_HISTORY_LOOKBACK_DAYS` (default `1100`)
- `QUANTBET_QUANTLAB_CARD_REFEREE_PRIOR_SEASONS` (default `3`, zero disables prior-season scans)
- `QUANTBET_QUANTLAB_CARD_REFEREE_DAYS_PER_CYCLE` (default `12`)
- `QUANTBET_QUANTLAB_CARD_REFEREE_SCOPES_PER_CYCLE` (default `24`)
- `QUANTBET_QUANTLAB_CARD_REFEREE_STATS_PER_CYCLE` (default `128`)

To check progress, count rows in `quantlab_referee_day_scans` and group `quantlab_card_feature_snapshots` by `referee_sample_size`. CardLab V5's decision reasons should move beyond `INSUFFICIENT_REFEREE_HISTORY` only when snapshots reach at least five complete referee matches. More history does not guarantee a value pick.

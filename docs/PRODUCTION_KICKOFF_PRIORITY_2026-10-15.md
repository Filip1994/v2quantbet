# Production kickoff-priority intake (2026-10-15)

## Operator intent
Production should not register fixtures nearly 70 hours ahead, occupying the shared RSD 4,500 exposure cap long before kickoff. Preserve 72-hour discovery and research, the existing approved buckets, C5 > C4 > remaining ROI bucket priority, and all historic records.

## New policy (proposed)
- Production alone admits source picks with `now < kickoff_at <= now + 24 hours` (UTC-aware timestamps); configured by `QUANTBET_PRODUCTION_INTAKE_MAX_LEAD_HOURS` (1..72, default 24). A value of 72 provides a simple rollback.
- Within the **same bucket-priority tier**, prefer earlier kickoff before EV and edge. C5 still outranks C4, and both outrank the dynamically ranked Research buckets, even if kickoff is later inside the allowed window.
- Candidate SQL applies the upper kickoff limit **before** source query `LIMIT 5000`; each source queries earliest kickoffs first.
- Contract fingerprint changes to `PRODUCTION_FUNNEL_INTAKE_V5` and includes the effective horizon, so new picks can be attributed to this policy.
- Existing registered Production picks, exposure, PENDING/PLAYED/SKIPPED decisions and settlement history are unchanged. Nothing is deleted, voided, or preempted.

## Limitations and acceptance
- This is an **admission gate**, not a price refresh. Source decisions made 70 hours earlier can still be cloned when their kickoff enters the 24-hour window. The existing quote/market data and provenance stay unchanged; quote recency must be assessed separately before relying on a pick.
- The exposure cap can still fill early inside the 24-hour window; intra-cycle ordering is not a reservation for future arrivals.
- Roll out only after CI review. On rollout, inspect logged `intake_max_lead_hours=24`, `cloned_picks` and `open_exposure_minor`; confirm newly cloned kickoff is inside 24h, existing historical picks are retained, and no blocked competition or de-selected bucket is admitted.
- No DB migration, extra Railway service or new market-data API calls required.

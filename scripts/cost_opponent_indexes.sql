-- Run outside a transaction. Does not modify match/decision/ledger rows.
-- Concurrent builds do not block normal reads/writes. They may wait for old
-- snapshots from archive SELECTs. Rollback retains these optional indexes and
-- redeploy e1808a0. Index removal is unnecessary for a functional rollback.
SET lock_timeout = '0';
SET statement_timeout = '20min';
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_quantlab_fixture_home_history_cost
  ON quantlab_fixture_observations (home_team_id, kickoff_at, fixture_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_quantlab_fixture_away_history_cost
  ON quantlab_fixture_observations (away_team_id, kickoff_at, fixture_id);

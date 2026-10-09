-- Compatibility marker for migration version 066.
--
-- The original file was a one-off manual GoalLab settlement targeting a single
-- historical Production fixture. It required a terminal provider observation
-- that cannot exist in a brand-new database. Executing it as part of schema
-- setup made every clean PostgreSQL migration chain (including CI) fail.
--
-- The original operator-only SQL is archived, unchanged, at:
-- ops/manual_settlements/066_manual_settle_94e1448785.sql
--
-- Keep this file in the numbered migration chain so existing schema_migrations
-- version records remain stable. The runner tracks filenames rather than
-- checksums: databases that already applied version 066 keep their prior
-- settlement facts untouched. New databases apply this inert compatibility
-- marker without inventing a historical settlement.
--
-- Any future manual settlement must be explicitly authorized and run through
-- a separate, audited operational procedure; never automatic schema setup.

SELECT 1;

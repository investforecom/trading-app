-- 019_thesis_run_name.sql
-- Optional user-given name for a saved DCF/thesis run, so multiple scenarios
-- for the same ticker (e.g. "Bear case China ban", "Base") can be told apart
-- in the history list. Runs remain append-only by default (new save = new
-- row), but a run can now also be explicitly overwritten in place — see the
-- /generate endpoint's overwrite_run_id.

ALTER TABLE investment_theses ADD COLUMN name TEXT;

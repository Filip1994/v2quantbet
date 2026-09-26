-- Retire the plain Dixon-Coles GoalLab control picks.
-- The immutable quantlab_goal_decisions audit is intentionally preserved.
-- Only shadow-bet rows produced by the plain control model are removed.

DELETE FROM quantlab_shadow_bets
WHERE lab = 'GOAL'
  AND model_name = 'Dixon-Coles Control';

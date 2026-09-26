# GoalLab

GoalLab owns QuantLab experiments for goals and BTTS.

## Initial model family

DC+ Core keeps current Dixon-Coles as the control/base and tests incremental structural
features:

- recent goals for/against
- recent points/form
- home/away splits
- rest-day differential
- fixture congestion

Market-aware variants must be evaluated separately from structural DC+ so that market
information is not silently mixed into an independent sports probability model.

## League scope

GoalLab uses GOAL_SCOPE_V1 and intentionally has a much broader universe than CardLab
and CornerLab.

Eligible by default: professional senior competitions not explicitly excluded.

Excluded locally before fixture-specific QuantLab requests:

- youth competitions U13 through U23 and equivalent Under labels;
- academy, reserve/reserves and amateur/amateurs competitions;
- reserve-team suffixes such as B and II where detected by the deterministic rule;
- all African countries plus competitions explicitly identified as CAF/Africa;
- Far East countries in the V1 region registry: Brunei, Cambodia, China, Chinese Taipei,
  Hong Kong, Indonesia, Japan, Laos, Macau/Macao, Malaysia, Mongolia, Myanmar, North
  Korea, Philippines, Singapore, South Korea, Taiwan, Thailand, Timor-Leste and Vietnam.

The scope is versioned in src/h2h/quantlab/scope.py. Scope changes require documentation
and a new/updated version rather than ad-hoc runtime inference.

## Markets

For eligible fixtures, GoalLab can ingest every returned Bet365/1xBet market. Goal
ownership is assigned by the shared versioned classifier; unsupported/unknown markets
are retained as UNCLASSIFIED. Canonical modeling and settlement support remain explicit
and versioned.

## Referee variables

Referee card/foul variables do not belong to GoalLab v1.

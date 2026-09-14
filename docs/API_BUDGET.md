# Daily API budget

QuantBet uses `DailyApiBudget` to protect the provider quota.

## Defaults

- Provider daily limit: `7,500` calls.
- Operational reserve: `1,500` calls.
- Normal application traffic may therefore consume at most `6,000` calls per UTC day.

Both values are configurable when constructing `DailyApiBudget`.

## Behavior

- The budget is shared by wrapping the provider-neutral `JsonTransport` in `BudgetedJsonTransport`.
- A call is counted before the underlying transport is invoked.
- Failed requests still consume budget because the provider has received an attempt.
- Once the operational limit is reached, `ApiBudgetExceededError` is raised and no network request is made.
- Usage resets automatically at the next UTC calendar day.
- The budget layer is provider-neutral and does not enter the quant/domain layer.

The guard is an in-process counter. A multi-instance deployment requires a shared store such as Redis or a database-backed atomic counter before production scaling.

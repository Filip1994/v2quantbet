# Legacy Migration Notes

The existing `Filip1994/h2h` repository is reference material only.

Likely candidates for controlled migration include:

- Dixon-Coles model
- probability generation
- calibration
- pricing / EV / edge calculations
- risk mathematics

The following are explicitly NOT to be copied as architecture:

- JSON files as canonical production state
- Git commits as runtime state coordination
- overlapping GitHub Actions as state writers
- legacy dashboard reconstruction logic
- provider-specific odds structures passed directly into quant

Every migrated mathematical component must receive regression/golden-master coverage before
the surrounding infrastructure is considered complete.

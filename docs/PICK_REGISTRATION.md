# Pick registration

## Svrha

`PickRegistration` predstavlja nepromenljiv zapis o tačno onom value pick-u koji je registrovan za bulletin ili monitoring.

## Sadržaj

- `pick_id` — eksplicitni, stabilni identitet registracije;
- `value_pick` — snapshot model-vs-market evaluacije;
- `registered_at` — vreme registracije sa timezone informacijom;
- `status` — lifecycle stanje (`registered`, `voided` ili `settled`).

## Pravila

- Registracija je immutable (`frozen=True`, `slots=True`).
- Prazan identitet nije dozvoljen.
- `registered_at` mora biti `datetime` objekat.
- Status mora biti član `PickStatus` enumeracije.
- Fixture identitet se izvodi iz sačuvanog canonical quote-a i ne može se promeniti nezavisno od value pick-a.

Ovaj model je samo domen-snapshot. Persistencija, status-transition use-case-i i settlement logika ostaju zasebne celine.

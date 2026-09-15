# Pick registration

## Svrha

`PickRegistration` predstavlja nepromenljiv zapis o tačno onom value pick-u koji je registrovan za bulletin ili monitoring.

## Sadržaj

- `pick_id` — eksplicitni, stabilni identitet registracije;
- `value_pick` — snapshot model-vs-market evaluacije;
- `registered_at` — vreme registracije sa timezone informacijom;
- `status` — lifecycle stanje (`registered`, `voided` ili `settled`).
- `eligibility_decision_id` — opcioni keyword-only ID odluke; nova registraciona
  funkcija ga obavezno preuzima iz odobrene odluke.

## Pravila

- Registracija je immutable (`frozen=True`, `slots=True`).
- Prazan identitet nije dozvoljen.
- `registered_at` mora biti `datetime` objekat.
- Status mora biti član `PickStatus` enumeracije.
- Fixture identitet se izvodi iz sačuvanog canonical quote-a i ne može se promeniti nezavisno od value pick-a.

Ovaj model je samo domen-snapshot. Persistencija, status-transition use-case-i i settlement logika ostaju zasebne celine.

## Eksplicitna registraciona granica

`h2h.use_cases.register_pick.register_pick(decision, *, pick_id, registered_at)`
prihvata `EligibilityDecision`, ne običan `ValuePick`. Odbijena odluka izaziva
`RejectedPickRegistrationError`; odobrena odluka daje immutable registraciju sa
istim `ValuePick` objektom i `eligibility_decision_id`. Funkcija nema argument za
zamenu valuacije. ID pika i vreme i dalje proverava postojeći domen-konstruktor.

Direktna konstrukcija `PickRegistration` ostaje kompatibilna, sa podrazumevanim
`eligibility_decision_id=None`. Nova granica se sprovodi u use-case-u; sam domen
objekat nije dokaz da je odluka prošla kroz njega. ID odluke je minimalna referenca,
bez provere globalne jedinstvenosti ili persistencije. Pun provenance iz
`VALUE_DECISION_CONTRACT.md` §7 ostaje delimično neimplementiran.

Implementirano: valuacija -> eksplicitna odluka -> registracija odobrene odluke.
Nije implementirano: politika koja donosi betting odluku i njeni pragovi.
Testovi koriste sintetičke odluke; odobrenje u testu ne predstavlja betting
strategiju. Nema publisher-a ili automatskog objavljivanja.

Testovi: `tests/use_cases/test_register_pick.py` proverava gate, identitet valuacije,
nemogućnost zamene, provenance, immutability i postojeću ID/time validaciju;
`tests/domain/test_pick_registration.py` ostaje kompatibilan.

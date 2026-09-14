# API-Football odds service

`ApiFootballOddsService` povezuje HTTP klijent sa postojećim ingestion pipeline-om.

Tok je:

1. `ApiFootballClient.fetch_odds()` preuzima sirovi API-Football odgovor.
2. `ingest_api_football_odds()` flatten-uje i normalizuje kvote u `CanonicalQuote` objekte.
3. `build_api_football_market_snapshots()` grupiše kvote i validira `MarketSnapshot` objekte.

Servis ne sadrži provider-specifičnu logiku, već samo orkestrira postojeće granice. HTTP transport se i dalje ubrizgava kroz `ApiFootballClient`, što omogućava determinističke testove bez mrežnog poziva.

## Upotreba

```python
service = ApiFootballOddsService(client)
quotes = service.fetch_quotes(fixture_id=42)
snapshots = service.fetch_market_snapshots(fixture_id=42)
```

Servis trenutno ne upisuje podatke u bazu. Persistence ostaje odvojena odgovornost aplikacionog sloja.

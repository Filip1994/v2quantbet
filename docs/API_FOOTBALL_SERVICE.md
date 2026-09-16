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
quotes = service.fetch_quotes(fixture_identity=resolved_fixture_identity)
snapshots = service.fetch_market_snapshots(fixture_identity=resolved_fixture_identity)
```

Service accepts the resolved canonical/provider fixture identity. It uses the positive numeric provider ID only for the API-Football transport call and passes the canonical `api-football:<id>` identity into quote ingestion. It does not write to the database; persistence remains the application-layer responsibility.

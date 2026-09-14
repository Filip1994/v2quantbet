# QuantBet — Perfect Scaling Plan

> Cilj ovog plana nije da izgradimo prekomplikovanu platformu, već da dođemo do **pouzdanog sistema koji generiše dnevni bilten sa pikovima**, uz jasan, neinteraktivan dashboard za nadzor sistema.

## 1. Glavni cilj

QuantBet treba da pređe kroz sledeći kompletan tok:

```text
API-Football
    ↓
Preuzimanje utakmica i kvota
    ↓
Normalizacija i validacija podataka
    ↓
SQLite persistence
    ↓
Quant model / Dixon–Coles baseline
    ↓
Procena verovatnoća
    ↓
Fair odds / edge / value calculation
    ↓
Filtriranje i rangiranje pikova
    ↓
Dnevni bilten
    ↓
Neinteraktivni system dashboard
```

Krajnji proizvod nije samo kolekcija adaptera i modela. Krajnji proizvod je **ponovljiv proces koji svakog dana izdvaja obrazložene pikove i jasno pokazuje stanje sistema**.

---

## 2. Principi projekta

1. **MVP first** — prvo završiti funkcionalan put od podataka do biltena.
2. **Minimalna arhitektura** — uvoditi apstrakcije samo kada rešavaju stvaran problem.
3. **Provider-neutral domain** — model i persistence ne smeju zavisiti od API-Football detalja.
4. **Reproducibilnost** — svaki bilten mora imati timestamp, verziju modela, ulazne podatke i pravila selekcije.
5. **Fail closed** — ne generisati pik ako su podaci nepotpuni, zastareli ili kontradiktorni.
6. **Bez lažne sigurnosti** — sistem prikazuje procenu vrednosti, ne garantuje dobitak.
7. **Svaka celina ima testove i dokumentaciju.**
8. **CI je obavezan gate** pre prelaska na sledeću funkcionalnu celinu.

---

## 3. Faza A — Stabilizacija postojeće osnove

### Status

Već je postavljena osnova za:

- Dixon–Coles baseline i quant domen;
- canonical quote modele;
- provider-neutral quote normalizaciju;
- API-Football adapter i ingestion;
- validaciju snapshot-a i deduplikaciju kvota;
- in-memory i SQLite persistence;
- quote application use-case;
- konfiguraciju preko environment promenljivih;
- HTTP transport;
- retry politiku;
- rate-limit obradu;
- dnevni API budžet;
- osnovni cache API-Football odgovora.

### Preostalo u ovoj fazi

- potvrditi da je poslednji cache commit zelen na CI-u;
- proveriti da su testovi cache-a stabilni;
- ukloniti eventualne duplikate i nepotrebne javne API-je;
- proveriti da dokumentacija odgovara stvarnom kodu.

**Izlazni kriterijum:** postojeća osnova je zelena na CI-u i nema poznatih regresija.

---

## 4. Faza B — Stvarni ingestion pipeline

Implementirati jedan jasan application flow:

1. učitaj konfiguraciju;
2. inicijalizuj transport, budžet, retry i cache;
3. preuzmi utakmice za ciljani datum/ligu;
4. preuzmi kvote za relevantne fixture-e;
5. validiraj API odgovor;
6. normalizuj kvote u canonical modele;
7. odbaci nevalidne ili konfliktne zapise;
8. upiši validne podatke u SQLite;
9. zabeleži rezultat ingestion-a.

### Obavezna pravila

- nema upisa nevalidnih kvota;
- isti zapis mora biti idempotentan;
- konflikt se odbija eksplicitno;
- API greška ne sme biti predstavljena kao prazan uspešan rezultat;
- zastareli podaci moraju biti označeni ili izostavljeni iz analize.

### Testovi

- validan API response;
- nevalidan/malformed response;
- prazan response;
- HTTP greška;
- rate limit;
- prekoračenje dnevnog budžeta;
- ponovljeni ingestion;
- konflikt kvota;
- end-to-end API → SQLite tok.

**Izlazni kriterijum:** izvorni podaci pouzdano završavaju u lokalnom persistence sloju.

---

## 5. Faza C — Quant engine za pikove

Ovo je centralna poslovna faza.

### 5.1. Input

Za svaku utakmicu koristiti samo podatke koji su dostupni pre početka utakmice:

- timovi;
- datum i vreme;
- liga/sezona;
- forma i istorijski rezultati, ako su dostupni;
- home/away kontekst;
- modelirane očekivane vrednosti;
- tržišne kvote;
- timestamp poslednjeg osvežavanja.

### 5.2. Model output

Za podržana tržišta izračunati:

- model probability;
- bookmaker implied probability;
- fair odds;
- edge;
- expected value;
- confidence/quality flags;
- model version;
- data freshness.

Osnovne formule:

```text
implied_probability = 1 / bookmaker_odds
fair_odds = 1 / model_probability
edge = model_probability - implied_probability
EV = model_probability * bookmaker_odds - 1
```

Kod tržišta sa marginom potrebno je jasno definisati da li se koristi sirova ili margin-adjusted implied probability.

### 5.3. Pravila za validan pik

Pik može ući u bilten samo ako:

- kvota je pozitivna i validna;
- model probability je u dozvoljenom opsegu;
- podaci nisu zastareli;
- nema konflikta između izvora;
- postoji minimalan edge/EV prag;
- model ima dovoljan kvalitet podataka;
- utakmica nije počela;
- tržište je podržano i pravilno mapirano.

### 5.4. Rangiranje

Pikove rangirati po kombinaciji:

1. očekivane vrednosti;
2. kvaliteta i svežine podataka;
3. stabilnosti modela;
4. likvidnosti/relevantnosti tržišta;
5. rizika i neizvesnosti.

Ne koristiti samo najveći edge kao jedini kriterijum.

### 5.5. Testovi

- deterministički testovi formula;
- golden-master testovi za postojeći model;
- testovi granica probability/odds vrednosti;
- testovi za edge i EV;
- testovi filtriranja;
- testovi rangiranja;
- testovi da se utakmice u prošlosti ne pojavljuju u budućem biltenu;
- testovi protiv data leakage-a.

**Izlazni kriterijum:** sistem može iz sirovih kvota izračunati proverljive i rangirane kandidate za pikove.

---

## 6. Faza D — Generator dnevnog biltena

Bilten je prvi stvarni korisnički proizvod.

### 6.1. Generator

Napraviti deterministički use-case, na primer:

```text
generate_daily_bulletin(date, filters, model_version) -> Bulletin
```

Generator treba da:

1. učita relevantne utakmice;
2. učita poslednje validne kvote;
3. izračuna model outputs;
4. primeni pravila za izbor;
5. rangira kandidate;
6. odredi konačne pikove;
7. generiše objašnjenje za svaki pik;
8. sačuva snapshot biltena;
9. izveze bilten u Markdown i JSON format.

### 6.2. Sadržaj biltena

Svaki bilten treba da sadrži:

- datum i vreme generisanja;
- model version;
- broj analiziranih utakmica;
- broj odbačenih kandidata i razlog;
- konačne pikove;
- utakmicu i tržište;
- bookmaker i kvotu;
- model probability;
- fair odds;
- implied probability;
- edge/EV;
- data freshness;
- kratak razlog za izbor;
- upozorenja i ograničenja.

### 6.3. Važno

Bilten ne sme da prikazuje samo broj ili tip. Mora da prikaže **zašto je pik izabran i koliko je procena pouzdana**.

**Izlazni kriterijum:** jednim pozivom možemo generisati kompletan dnevni bilten bez ručnog rada.

---

## 7. Faza E — Slavni Super Dashboard

Dashboard treba da bude **neinteraktivan operativni pregled**, odnosno "oči u sistem".

Ne praviti kompleksan frontend pre nego što bilten radi.

### 7.1. Prva verzija dashboarda

Dashboard može biti statički HTML ili server-rendered stranica koja prikazuje:

- poslednji uspešan ingestion;
- status API konekcije;
- iskorišćenost dnevnog API budžeta;
- broj preuzetih fixture-a;
- broj validnih kvota;
- broj odbačenih kvota;
- poslednji generisani bilten;
- broj pikova;
- model version;
- starost podataka;
- poslednje greške i upozorenja;
- stanje SQLite baze;
- vreme poslednjeg uspešnog pipeline-a.

### 7.2. Šta dashboard ne treba da radi u prvoj verziji

- nema kompleksnu navigaciju;
- nema ručno uređivanje kvota;
- nema interaktivno modeliranje;
- nema trading izvršavanje;
- nema automatsko klađenje;
- nema korisničke naloge;
- nema real-time streaming ako nije potreban.

### 7.3. Izlaz

Jedna stranica treba da odgovori na pitanja:

- Da li sistem radi?
- Kada su podaci poslednji put osveženi?
- Koliko API budžeta je potrošeno?
- Koliko utakmica i kvota je obrađeno?
- Da li postoji novi bilten?
- Koliko pikova je izabrano?
- Da li postoje greške koje zahtevaju pažnju?

**Izlazni kriterijum:** dashboard daje pouzdan pregled sistema bez potrebe za čitanjem logova.

---

## 8. Faza F — Operativno pokretanje

Za MVP je dovoljna jednostavna operativa:

- jedan scheduled job za ingestion;
- jedan scheduled job za generisanje biltena;
- SQLite kao početni storage;
- environment konfiguracija;
- Railway deployment;
- logovi dostupni kroz platformu;
- statički ili server-rendered dashboard;
- ručno pokretanje pipeline-a za debugging.

### Minimalne environment promenljive

- `API_FOOTBALL_KEY`;
- `QUANTBET_DATABASE_PATH`;
- `QUANTBET_ENV`;
- pragovi za edge/EV;
- maksimalan broj pikova;
- ciljani datum ili vremenska zona, gde je potrebno.

Secrets nikada ne smeju biti u repozitorijumu, biltenu, dashboardu ili logovima.

---

## 9. Faza G — Quality, security i production gate

Pre prvog realnog korišćenja proveriti:

- svi testovi prolaze;
- CI je zelen;
- nema hardkodovanih secrets;
- API ključ se ne loguje;
- inputi su validirani;
- API response se validira pre obrade;
- pipeline je idempotentan;
- bilten je reproducibilan;
- model version se čuva uz bilten;
- timezone pravila su jasna;
- utakmice nakon početka se ne uključuju;
- greške se razlikuju od praznih rezultata;
- SQLite fajl i direktorijum imaju odgovarajuće dozvole;
- dashboard ne otkriva poverljive podatke;
- postoji backup/export strategija za biltene i rezultate.

---

## 10. Šta je namerno izbačeno iz MVP-a

Sledeće nije potrebno pre prvog funkcionalnog biltena:

- mikroservisi;
- distribuirani cache;
- event bus;
- Kafka ili sličan broker;
- kompleksan metrics stack;
- Kubernetes;
- napredni tracing;
- real-time websocket infrastruktura;
- automatsko klađenje;
- portfolio optimization;
- multi-tenant korisnički sistem;
- napredni frontend;
- višestruke baze bez realne potrebe;
- preuranjena optimizacija.

Ove stvari mogu doći tek kada postoje stvarni podaci o opterećenju, korisnicima ili poslovnoj potrebi.

---

## 11. Precizan redosled implementacije

1. Potvrditi CI za cache i stabilizovati postojeću osnovu.
2. Završiti API response validation.
3. Implementirati end-to-end ingestion test.
4. Implementirati quant output: fair odds, edge i EV.
5. Implementirati candidate filtering i ranking.
6. Implementirati `generate_daily_bulletin` use-case.
7. Sačuvati bulletin snapshot u SQLite.
8. Generisati Markdown i JSON bilten.
9. Dodati osnovni operational logging.
10. Dodati neinteraktivan dashboard.
11. Povezati scheduled execution na Railway-u.
12. Dodati production/security audit.
13. Pokrenuti finalni CI i napraviti production gate checklist.
14. Tek nakon toga razmatrati skaliranje.

---

## 12. Definition of Done

QuantBet je spreman za prvi realni MVP ciklus kada:

- može da preuzme podatke bez ručnog rada;
- validira i čuva kvote;
- izračunava modelirane verovatnoće;
- izračunava fair odds, edge i EV;
- izdvaja pikove po eksplicitnim pravilima;
- generiše dnevni bilten;
- čuva verziju biltena i modela;
- prikazuje stanje sistema na dashboardu;
- radi na Railway-u;
- ima zelene testove i CI;
- ne izlaže secrets;
- jasno prikazuje ograničenja i kvalitet podataka.

## Zaključak

**Da, ovaj smer ima smisla.** Fokus treba da bude na sledećem lancu:

> **pouzdani podaci → proverljiv model → rangirani pikovi → dnevni bilten → dashboard koji pokazuje stanje sistema.**

Sve što ne doprinosi tom lancu odlaže se dok ne postoji konkretna potreba. To je pravi put ka skaliranju bez overengineering-a.

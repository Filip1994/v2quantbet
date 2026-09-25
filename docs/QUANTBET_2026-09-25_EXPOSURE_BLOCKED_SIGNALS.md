# QuantBet — Exposure-blocked signals — 2026-09-25

## Purpose

This document is the research ledger for value signals that qualified on the model/value rules but were prevented from progressing because the PLAYED open-exposure cap was already full.

The objective is not to assume that a larger logged EV is automatically a better bet. The objective is to preserve enough evidence to answer, with data:

- which model-probability ranges are actually calibrated;
- which EV bands produce positive realized yield;
- which odds ranges and markets produce the strongest CLV;
- whether high-EV signals are genuine value or model overconfidence;
- whether the 3,000 RSD exposure cap is rejecting profitable capacity;
- whether staking should remain fixed or later move to capped fractional Kelly.

## Production state at capture

- Date: **2026-09-25** (Europe/Belgrade)
- Fixed stake: **300 RSD**
- Hard PLAYED exposure cap: **3,000 RSD**
- Latest observed open exposure: **3000 RSD**
- Latest PLAYED count occupying risk: **10**
- Latest SKIPPED count: **7**
- SKIPPED exposure is excluded from the hard risk cap.
- Current value thresholds: **minimum edge 7% / minimum EV 7%**.

## Important definitions

- **Model probability** is the model's estimate of the probability of the selected outcome.
- **Market fair probability** is the proportional two-way de-vig probability from the paired bookmaker prices.
- **Edge** = model probability - market fair probability.
- **EV** = model probability × decimal odds - 1.
- **CLV** compares the entry price with the closing price for the same market/bookmaker methodology.

A higher **model probability** means the model assigns a higher chance to the outcome. A higher **EV** does **not** necessarily mean a higher outcome probability because EV also depends on the offered odds.

## Capture completeness

Railway runtime logs were read in three bounded windows covering local midnight onward:

- 2026-09-24 22:00–2026-09-25 02:00 UTC
- 2026-09-25 02:00–06:00 UTC
- 2026-09-25 06:00–10:00 UTC

Only events whose sole rejection reason was `MAX_OPEN_EXPOSURE_EXCEEDED` are included below. Signals that also failed edge, EV, odds, kickoff-window, or another rule are excluded.

Captured exposure-only evaluation events: **263**  
Unique fixtures with at least one exposure-only signal: **82**

## Extreme blocked signals

Extreme here is an analytical label only: **best logged EV >= 30% for the fixture**. These signals require special scrutiny for calibration/model overconfidence.

| Provider fixture | Exact match mapping | Best signal | Odds | Model p | Market fair p | Edge | EV | Logged time (Belgrade) |
|---|---|---|---:|---:|---:|---:|---:|---|
| `1577943` | **PENDING exact DB/provider lookup** | BTTS NO | 2.27 | 86.42% | 41.34% | 45.08% | **96.17%** | 11:40 |
| `1508557` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 2.75 | 58.73% | 33.73% | 25.00% | **61.51%** | 03:55 |
| `1504314` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 2.62 | 60.38% | 34.50% | 25.88% | **58.20%** | 04:29 |
| `1583933` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 2.43 | 65.07% | 37.21% | 27.86% | **58.11%** | 09:20 |
| `1577950` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 2.15 | 71.28% | 43.72% | 27.56% | **53.25%** | 00:21 |
| `1510861` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 3.00 | 50.63% | 31.19% | 19.44% | **51.90%** | 04:13 |
| `1568188` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 2.05 | 74.05% | 46.05% | 28.00% | **51.81%** | 00:33 |
| `1569112` | **PENDING exact DB/provider lookup** | BTTS NO | 2.50 | 59.30% | 36.71% | 22.59% | **48.24%** | 06:33 |
| `1517355` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 2.08 | 71.21% | 45.41% | 25.80% | **48.11%** | 05:40 |
| `1536042` | **PENDING exact DB/provider lookup** | BTTS NO | 1.95 | 74.84% | 47.72% | 27.12% | **45.94%** | 01:26 |
| `1634028` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 2.10 | 67.70% | 44.00% | 23.70% | **42.17%** | 05:44 |
| `1504316` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 2.52 | 56.29% | 35.88% | 20.41% | **41.86%** | 02:16 |
| `1536710` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 1.74 | 81.21% | 53.10% | 28.11% | **41.30%** | 06:59 |
| `1536706` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 2.00 | 70.60% | 46.24% | 24.37% | **41.21%** | 04:01 |
| `1640771` | **PENDING exact DB/provider lookup** | OU_25 OVER | 2.00 | 70.31% | 47.37% | 22.94% | **40.63%** | 06:42 |
| `1495566` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 2.55 | 54.98% | 36.25% | 18.73% | **40.19%** | 04:43 |
| `1577491` | **PENDING exact DB/provider lookup** | BTTS NO | 1.78 | 78.70% | 52.02% | 26.67% | **40.08%** | 09:34 |
| `1499660` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 1.62 | 85.40% | 58.14% | 27.26% | **38.35%** | 06:17 |
| `1640090` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 2.66 | 51.73% | 34.00% | 17.74% | **37.61%** | 11:44 |
| `1583932` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 2.88 | 47.55% | 31.43% | 16.12% | **36.94%** | 09:47 |
| `1640272` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 2.00 | 68.34% | 47.37% | 20.97% | **36.68%** | 03:34 |
| `1501485` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 2.05 | 66.52% | 44.74% | 21.77% | **36.36%** | 10:16 |
| `1504315` | **PENDING exact DB/provider lookup** | BTTS NO | 2.01 | 67.48% | 45.82% | 21.66% | **35.63%** | 04:49 |
| `1499654` | **PENDING exact DB/provider lookup** | BTTS YES | 2.62 | 51.73% | 35.47% | 16.27% | **35.54%** | 05:28 |
| `1521619` | **PENDING exact DB/provider lookup** | BTTS NO | 2.34 | 57.38% | 40.15% | 17.22% | **34.26%** | 05:06 |
| `1511228` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 2.75 | 48.70% | 33.73% | 14.96% | **33.91%** | 05:52 |
| `1504561` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 2.69 | 49.23% | 33.58% | 15.65% | **32.43%** | 04:12 |
| `1517353` | **PENDING exact DB/provider lookup** | BTTS NO | 2.15 | 61.10% | 42.67% | 18.43% | **31.36%** | 09:17 |
| `1490497` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 2.10 | 62.50% | 44.74% | 17.77% | **31.26%** | 11:59 |
| `1635426` | **PENDING exact DB/provider lookup** | OU_25 UNDER | 3.25 | 40.34% | 29.04% | 11.30% | **31.11%** | 04:20 |

### Mapping status

The exact home/away/competition mapping is **not inferred or fabricated** in this revision.

Railway Agent was explicitly asked to:
1. query production PostgreSQL read-only; and
2. alternatively use the engine's existing API-Football credential internally for fixture lookup.

The agent reported that its available toolset can do observability/configuration/container-file inspection but **cannot execute arbitrary SQL and cannot make authenticated outbound provider HTTP calls**. Therefore the provider fixture IDs above remain the authoritative identifiers until a direct read-only DB/provider lookup surface is available.

## All exposure-only fixtures — best signal per fixture

This table keeps one representative row per fixture: the highest logged EV that was rejected **only** because exposure was full.

| Provider fixture | Signal | Odds | Model p | Market fair p | Edge | EV | Exposure-only observations |
|---|---|---:|---:|---:|---:|---:|---:|
| `1577943` | BTTS NO | 2.27 | 86.42% | 41.34% | 45.08% | 96.17% | 2 |
| `1508557` | OU_25 UNDER | 2.75 | 58.73% | 33.73% | 25.00% | 61.51% | 6 |
| `1504314` | OU_25 UNDER | 2.62 | 60.38% | 34.50% | 25.88% | 58.20% | 4 |
| `1583933` | OU_25 UNDER | 2.43 | 65.07% | 37.21% | 27.86% | 58.11% | 2 |
| `1577950` | OU_25 UNDER | 2.15 | 71.28% | 43.72% | 27.56% | 53.25% | 9 |
| `1510861` | OU_25 UNDER | 3.00 | 50.63% | 31.19% | 19.44% | 51.90% | 2 |
| `1568188` | OU_25 UNDER | 2.05 | 74.05% | 46.05% | 28.00% | 51.81% | 6 |
| `1569112` | BTTS NO | 2.50 | 59.30% | 36.71% | 22.59% | 48.24% | 9 |
| `1517355` | OU_25 UNDER | 2.08 | 71.21% | 45.41% | 25.80% | 48.11% | 4 |
| `1536042` | BTTS NO | 1.95 | 74.84% | 47.72% | 27.12% | 45.94% | 2 |
| `1634028` | OU_25 UNDER | 2.10 | 67.70% | 44.00% | 23.70% | 42.17% | 2 |
| `1504316` | OU_25 UNDER | 2.52 | 56.29% | 35.88% | 20.41% | 41.86% | 4 |
| `1536710` | OU_25 UNDER | 1.74 | 81.21% | 53.10% | 28.11% | 41.30% | 2 |
| `1536706` | OU_25 UNDER | 2.00 | 70.60% | 46.24% | 24.37% | 41.21% | 2 |
| `1640771` | OU_25 OVER | 2.00 | 70.31% | 47.37% | 22.94% | 40.63% | 6 |
| `1495566` | OU_25 UNDER | 2.55 | 54.98% | 36.25% | 18.73% | 40.19% | 1 |
| `1577491` | BTTS NO | 1.78 | 78.70% | 52.02% | 26.67% | 40.08% | 2 |
| `1499660` | OU_25 UNDER | 1.62 | 85.40% | 58.14% | 27.26% | 38.35% | 4 |
| `1640090` | OU_25 UNDER | 2.66 | 51.73% | 34.00% | 17.74% | 37.61% | 6 |
| `1583932` | OU_25 UNDER | 2.88 | 47.55% | 31.43% | 16.12% | 36.94% | 2 |
| `1640272` | OU_25 UNDER | 2.00 | 68.34% | 47.37% | 20.97% | 36.68% | 3 |
| `1501485` | OU_25 UNDER | 2.05 | 66.52% | 44.74% | 21.77% | 36.36% | 1 |
| `1504315` | BTTS NO | 2.01 | 67.48% | 45.82% | 21.66% | 35.63% | 4 |
| `1499654` | BTTS YES | 2.62 | 51.73% | 35.47% | 16.27% | 35.54% | 4 |
| `1521619` | BTTS NO | 2.34 | 57.38% | 40.15% | 17.22% | 34.26% | 1 |
| `1511228` | OU_25 UNDER | 2.75 | 48.70% | 33.73% | 14.96% | 33.91% | 2 |
| `1504561` | OU_25 UNDER | 2.69 | 49.23% | 33.58% | 15.65% | 32.43% | 4 |
| `1517353` | BTTS NO | 2.15 | 61.10% | 42.67% | 18.43% | 31.36% | 2 |
| `1490497` | OU_25 UNDER | 2.10 | 62.50% | 44.74% | 17.77% | 31.26% | 2 |
| `1635426` | OU_25 UNDER | 3.25 | 40.34% | 29.04% | 11.30% | 31.11% | 4 |
| `1637846` | OU_25 OVER | 2.15 | 60.41% | 43.72% | 16.69% | 29.87% | 3 |
| `1635453` | OU_25 UNDER | 3.00 | 43.25% | 31.19% | 12.05% | 29.74% | 4 |
| `1508560` | OU_25 UNDER | 2.05 | 63.00% | 44.74% | 18.25% | 29.14% | 1 |
| `1511408` | OU_25 UNDER | 2.62 | 48.80% | 34.50% | 14.30% | 27.86% | 8 |
| `1577487` | OU_25 OVER | 2.19 | 58.24% | 43.56% | 14.69% | 27.55% | 1 |
| `1504312` | OU_25 UNDER | 2.88 | 44.09% | 31.43% | 12.66% | 26.98% | 12 |
| `1640270` | OU_25 UNDER | 1.69 | 74.96% | 54.32% | 20.64% | 26.68% | 3 |
| `1504562` | OU_25 UNDER | 2.00 | 63.13% | 47.37% | 15.76% | 26.26% | 4 |
| `1569111` | OU_25 OVER | 1.57 | 80.34% | 59.95% | 20.40% | 26.14% | 7 |
| `1635454` | OU_25 UNDER | 2.88 | 43.59% | 31.43% | 12.16% | 25.54% | 4 |
| `1499659` | OU_25 UNDER | 1.62 | 76.89% | 58.14% | 18.75% | 24.56% | 4 |
| `1511410` | BTTS NO | 2.41 | 51.16% | 38.05% | 13.12% | 23.30% | 8 |
| `1536474` | OU_25 UNDER | 1.85 | 66.48% | 50.00% | 16.48% | 23.00% | 2 |
| `1536277` | BTTS NO | 2.05 | 59.94% | 45.33% | 14.61% | 22.88% | 1 |
| `1583773` | OU_25 OVER | 2.00 | 61.35% | 47.37% | 13.98% | 22.69% | 2 |
| `1520899` | BTTS YES | 2.20 | 55.69% | 42.41% | 13.28% | 22.51% | 8 |
| `1511023` | OU_25 UNDER | 2.38 | 51.43% | 39.13% | 12.30% | 22.40% | 6 |
| `1640772` | OU_25 UNDER | 1.75 | 69.83% | 53.95% | 15.88% | 22.20% | 3 |
| `1637844` | OU_25 OVER | 2.05 | 59.35% | 46.05% | 13.29% | 21.66% | 2 |
| `1493706` | OU_25 UNDER | 2.10 | 57.23% | 44.74% | 12.49% | 20.18% | 8 |
| `1510864` | OU_25 UNDER | 2.63 | 45.65% | 35.38% | 10.27% | 20.06% | 2 |
| `1493709` | OU_25 UNDER | 2.62 | 45.78% | 35.47% | 10.31% | 19.95% | 4 |
| `1568807` | OU_25 UNDER | 2.74 | 43.72% | 33.17% | 10.55% | 19.79% | 1 |
| `1520898` | OU_25 OVER | 2.25 | 53.05% | 41.86% | 11.19% | 19.36% | 2 |
| `1640770` | OU_25 OVER | 2.15 | 55.19% | 43.72% | 11.47% | 18.65% | 4 |
| `1493705` | OU_25 UNDER | 2.08 | 56.71% | 45.41% | 11.30% | 17.95% | 4 |
| `1600705` | OU_25 UNDER | 1.65 | 70.29% | 57.14% | 13.15% | 15.98% | 1 |
| `1554169` | OU_25 OVER | 2.20 | 52.70% | 42.11% | 10.60% | 15.94% | 2 |
| `1493708` | OU_25 UNDER | 1.80 | 64.37% | 52.63% | 11.74% | 15.87% | 4 |
| `1577948` | OU_25 OVER | 1.44 | 80.42% | 64.53% | 15.89% | 15.80% | 2 |
| `1549799` | OU_25 OVER | 1.85 | 62.37% | 51.32% | 11.05% | 15.38% | 2 |
| `1504556` | OU_25 OVER | 1.67 | 67.99% | 56.28% | 11.70% | 13.54% | 3 |
| `1577490` | OU_25 OVER | 2.13 | 53.24% | 44.82% | 8.42% | 13.39% | 1 |
| `1536709` | BTTS NO | 1.71 | 66.28% | 54.88% | 11.40% | 13.34% | 1 |
| `1500131` | BTTS YES | 2.62 | 42.98% | 35.47% | 7.52% | 12.62% | 1 |
| `1505278` | BTTS YES | 1.62 | 69.31% | 57.59% | 11.72% | 12.28% | 4 |
| `1520896` | OU_25 UNDER | 2.00 | 56.10% | 47.37% | 8.74% | 12.21% | 4 |
| `1493715` | OU_25 OVER | 1.53 | 73.28% | 60.87% | 12.41% | 12.12% | 4 |
| `1499658` | BTTS YES | 2.20 | 50.64% | 42.41% | 8.23% | 11.40% | 1 |
| `1501486` | OU_25 UNDER | 1.86 | 59.84% | 49.32% | 10.52% | 11.30% | 1 |
| `1637847` | OU_25 OVER | 2.15 | 51.08% | 43.72% | 7.37% | 9.83% | 2 |
| `1549649` | BTTS NO | 1.71 | 63.95% | 53.91% | 10.04% | 9.36% | 1 |
| `1499651` | OU_25 UNDER | 1.46 | 74.90% | 62.76% | 12.14% | 9.35% | 3 |
| `1637845` | BTTS NO | 1.46 | 74.81% | 62.76% | 12.06% | 9.23% | 2 |
| `1492983` | OU_25 OVER | 1.44 | 75.68% | 64.53% | 11.15% | 8.99% | 3 |
| `1505279` | OU_25 OVER | 1.50 | 72.64% | 62.50% | 10.14% | 8.96% | 1 |
| `1577493` | BTTS NO | 1.87 | 58.04% | 49.46% | 8.59% | 8.54% | 1 |
| `1641144` | OU_25 UNDER | 1.65 | 65.68% | 57.14% | 8.54% | 8.37% | 2 |
| `1536711` | OU_25 OVER | 1.80 | 60.18% | 51.35% | 8.83% | 8.33% | 1 |
| `1549706` | BTTS NO | 1.73 | 62.57% | 53.49% | 9.08% | 8.25% | 1 |
| `1498829` | BTTS NO | 1.50 | 71.84% | 62.50% | 9.34% | 7.76% | 2 |
| `1490496` | BTTS YES | 1.40 | 76.46% | 66.27% | 10.19% | 7.04% | 1 |

## Raw exposure-only signal ledger

Rows below are the individual logged preliminary evaluations, not registered picks. Multiple rows may belong to the same fixture, market, selection, bookmaker observation, or quote variant.

| Time (Belgrade) | Provider fixture | Market | Selection | Odds | Model p | Market fair p | Edge | EV |
|---|---|---|---|---:|---:|---:|---:|---:|
| 00:21 | `1577950` | OU_25 | UNDER | 2.15 | 71.28% | 43.72% | 27.56% | 53.25% |
| 00:21 | `1577950` | OU_25 | UNDER | 2.13 | 71.28% | 43.05% | 28.23% | 51.83% |
| 00:21 | `1577950` | BTTS | NO | 2.24 | 63.17% | 40.90% | 22.28% | 41.51% |
| 00:22 | `1569111` | BTTS | YES | 1.43 | 79.03% | 64.16% | 14.87% | 13.01% |
| 00:22 | `1569111` | OU_25 | OVER | 1.57 | 80.34% | 59.95% | 20.40% | 26.14% |
| 00:22 | `1569111` | OU_25 | OVER | 1.48 | 80.34% | 61.15% | 19.19% | 18.91% |
| 00:24 | `1569112` | OU_25 | UNDER | 2.62 | 54.72% | 35.47% | 19.25% | 43.37% |
| 00:24 | `1569112` | OU_25 | UNDER | 2.59 | 54.72% | 34.92% | 19.80% | 41.73% |
| 00:24 | `1569112` | BTTS | NO | 2.41 | 59.30% | 38.05% | 21.25% | 42.90% |
| 00:26 | `1504312` | OU_25 | UNDER | 2.88 | 44.09% | 31.43% | 12.66% | 26.98% |
| 00:26 | `1504312` | OU_25 | UNDER | 2.75 | 44.09% | 33.73% | 10.36% | 21.25% |
| 00:26 | `1504312` | BTTS | NO | 2.27 | 52.42% | 40.58% | 11.85% | 19.00% |
| 00:26 | `1504312` | BTTS | NO | 2.20 | 52.42% | 42.41% | 10.01% | 15.33% |
| 00:27 | `1640090` | OU_25 | UNDER | 2.38 | 51.73% | 39.13% | 12.60% | 23.12% |
| 00:27 | `1640090` | OU_25 | UNDER | 2.30 | 51.73% | 39.31% | 12.42% | 18.98% |
| 00:33 | `1568188` | OU_25 | UNDER | 2.05 | 74.05% | 46.05% | 28.00% | 51.81% |
| 00:33 | `1568188` | OU_25 | UNDER | 1.94 | 74.05% | 47.28% | 26.77% | 43.66% |
| 00:33 | `1568188` | BTTS | NO | 2.13 | 65.94% | 43.05% | 22.89% | 40.45% |
| 00:35 | `1492983` | OU_25 | OVER | 1.44 | 75.68% | 64.53% | 11.15% | 8.99% |
| 00:35 | `1492983` | OU_25 | OVER | 1.42 | 75.68% | 63.68% | 12.00% | 7.47% |
| 00:35 | `1640770` | OU_25 | OVER | 2.15 | 55.19% | 43.72% | 11.47% | 18.65% |
| 00:35 | `1640770` | OU_25 | OVER | 2.11 | 55.19% | 43.43% | 11.76% | 16.45% |
| 00:37 | `1640771` | OU_25 | OVER | 1.80 | 70.31% | 50.95% | 19.36% | 26.56% |
| 00:37 | `1640771` | OU_25 | OVER | 1.73 | 70.31% | 54.59% | 15.72% | 21.64% |
| 00:37 | `1640771` | BTTS | YES | 1.82 | 63.37% | 50.41% | 12.96% | 15.34% |
| 00:39 | `1493706` | OU_25 | UNDER | 2.10 | 57.23% | 44.74% | 12.49% | 20.18% |
| 00:39 | `1493706` | OU_25 | UNDER | 2.05 | 57.23% | 44.74% | 12.48% | 17.32% |
| 00:39 | `1493706` | BTTS | NO | 2.25 | 52.70% | 40.94% | 11.76% | 18.59% |
| 00:39 | `1493706` | BTTS | NO | 2.20 | 52.70% | 42.41% | 10.30% | 15.95% |
| 00:40 | `1493715` | OU_25 | OVER | 1.53 | 73.28% | 60.87% | 12.41% | 12.12% |
| 00:40 | `1493715` | BTTS | YES | 1.53 | 72.49% | 60.87% | 11.62% | 10.91% |
| 01:26 | `1536042` | BTTS | NO | 1.95 | 74.84% | 47.72% | 27.12% | 45.94% |
| 01:26 | `1536042` | OU_25 | UNDER | 1.75 | 83.24% | 52.83% | 30.41% | 45.68% |
| 01:44 | `1536277` | BTTS | NO | 2.05 | 59.94% | 45.33% | 14.61% | 22.88% |
| 01:52 | `1640772` | OU_25 | UNDER | 1.75 | 69.83% | 53.95% | 15.88% | 22.20% |
| 01:52 | `1640772` | OU_25 | UNDER | 1.71 | 69.83% | 53.66% | 16.17% | 19.40% |
| 01:52 | `1640772` | BTTS | NO | 1.81 | 63.64% | 50.68% | 12.96% | 15.20% |
| 01:59 | `1504556` | OU_25 | OVER | 1.67 | 67.99% | 56.28% | 11.70% | 13.54% |
| 01:59 | `1504556` | OU_25 | OVER | 1.63 | 67.99% | 56.30% | 11.69% | 10.82% |
| 01:59 | `1504556` | BTTS | YES | 1.62 | 66.92% | 57.59% | 9.33% | 8.41% |
| 02:10 | `1504562` | OU_25 | UNDER | 2.00 | 63.13% | 47.37% | 15.76% | 26.26% |
| 02:10 | `1504562` | OU_25 | UNDER | 1.93 | 63.13% | 47.55% | 15.58% | 21.84% |
| 02:10 | `1504562` | BTTS | NO | 1.82 | 65.02% | 50.68% | 14.34% | 18.34% |
| 02:10 | `1504562` | BTTS | NO | 1.80 | 65.02% | 51.48% | 13.54% | 17.04% |
| 02:16 | `1504316` | OU_25 | UNDER | 2.52 | 56.29% | 35.88% | 20.41% | 41.86% |
| 02:16 | `1504316` | OU_25 | UNDER | 2.50 | 56.29% | 37.50% | 18.79% | 40.73% |
| 02:16 | `1504316` | BTTS | NO | 2.50 | 53.86% | 36.87% | 16.99% | 34.66% |
| 02:16 | `1504316` | BTTS | NO | 2.38 | 53.86% | 39.13% | 14.73% | 28.19% |
| 02:45 | `1583773` | OU_25 | OVER | 2.00 | 61.35% | 47.37% | 13.98% | 22.69% |
| 02:45 | `1583773` | OU_25 | OVER | 1.96 | 61.35% | 46.74% | 14.61% | 20.24% |
| 03:01 | `1505279` | OU_25 | OVER | 1.50 | 72.64% | 62.50% | 10.14% | 8.96% |
| 03:24 | `1499651` | OU_25 | UNDER | 1.46 | 74.90% | 62.76% | 12.14% | 9.35% |
| 03:24 | `1499651` | OU_25 | UNDER | 1.44 | 74.90% | 64.53% | 10.37% | 7.85% |
| 03:24 | `1499651` | BTTS | NO | 1.67 | 64.17% | 55.11% | 9.06% | 7.16% |
| 03:28 | `1640270` | OU_25 | UNDER | 1.69 | 74.96% | 54.32% | 20.64% | 26.68% |
| 03:28 | `1640270` | OU_25 | UNDER | 1.57 | 74.96% | 59.95% | 15.01% | 17.69% |
| 03:28 | `1640270` | BTTS | NO | 1.88 | 65.54% | 48.77% | 16.77% | 23.22% |
| 03:34 | `1640272` | OU_25 | UNDER | 2.00 | 68.34% | 47.37% | 20.97% | 36.68% |
| 03:34 | `1640272` | OU_25 | UNDER | 1.95 | 68.34% | 47.01% | 21.33% | 33.26% |
| 03:34 | `1640272` | BTTS | NO | 1.75 | 76.70% | 52.45% | 24.25% | 34.22% |
| 03:35 | `1637847` | OU_25 | OVER | 2.15 | 51.08% | 43.72% | 7.37% | 9.83% |
| 03:35 | `1637847` | OU_25 | OVER | 2.11 | 51.08% | 43.43% | 7.65% | 7.78% |
| 03:39 | `1549706` | BTTS | NO | 1.73 | 62.57% | 53.49% | 9.08% | 8.25% |
| 03:43 | `1577943` | BTTS | NO | 2.18 | 86.42% | 43.08% | 43.34% | 88.39% |
| 03:44 | `1577948` | OU_25 | OVER | 1.40 | 80.42% | 66.27% | 14.15% | 12.58% |
| 03:48 | `1511023` | OU_25 | UNDER | 2.38 | 51.43% | 39.13% | 12.30% | 22.40% |
| 03:48 | `1511023` | OU_25 | UNDER | 2.38 | 51.43% | 38.02% | 13.41% | 22.40% |
| 03:48 | `1511023` | BTTS | NO | 2.50 | 46.97% | 36.71% | 10.26% | 17.41% |
| 03:49 | `1511408` | OU_25 | UNDER | 2.52 | 48.80% | 35.88% | 12.92% | 22.98% |
| 03:49 | `1511408` | OU_25 | UNDER | 2.50 | 48.80% | 37.50% | 11.30% | 22.00% |
| 03:49 | `1511408` | BTTS | NO | 2.56 | 48.00% | 35.84% | 12.16% | 22.88% |
| 03:49 | `1511408` | BTTS | NO | 2.50 | 48.00% | 37.50% | 10.50% | 20.00% |
| 03:55 | `1508557` | OU_25 | UNDER | 2.75 | 58.73% | 33.73% | 25.00% | 61.51% |
| 03:55 | `1508557` | OU_25 | UNDER | 2.74 | 58.73% | 33.01% | 25.73% | 60.93% |
| 03:55 | `1508557` | BTTS | NO | 1.50 | 79.68% | 62.50% | 17.18% | 19.52% |
| 04:01 | `1536706` | OU_25 | UNDER | 2.00 | 70.60% | 46.24% | 24.37% | 41.21% |
| 04:01 | `1536706` | BTTS | NO | 1.99 | 67.64% | 47.21% | 20.43% | 34.60% |
| 04:12 | `1504561` | OU_25 | UNDER | 2.69 | 49.23% | 33.58% | 15.65% | 32.43% |
| 04:12 | `1504561` | OU_25 | UNDER | 2.62 | 49.23% | 35.47% | 13.76% | 28.99% |
| 04:12 | `1504561` | BTTS | NO | 2.59 | 45.47% | 35.57% | 9.90% | 17.77% |
| 04:12 | `1504561` | BTTS | NO | 2.50 | 45.47% | 37.50% | 7.97% | 13.68% |
| 04:13 | `1510861` | OU_25 | UNDER | 3.00 | 50.63% | 31.19% | 19.44% | 51.90% |
| 04:13 | `1510861` | BTTS | NO | 2.93 | 46.00% | 31.70% | 14.30% | 34.79% |
| 04:20 | `1635426` | OU_25 | UNDER | 3.25 | 40.34% | 29.04% | 11.30% | 31.11% |
| 04:20 | `1635426` | OU_25 | UNDER | 3.08 | 40.34% | 29.36% | 10.98% | 24.25% |
| 04:20 | `1635426` | BTTS | NO | 3.05 | 38.87% | 30.21% | 8.67% | 18.56% |
| 04:20 | `1635426` | BTTS | NO | 3.00 | 38.87% | 31.19% | 7.68% | 16.61% |
| 04:21 | `1511410` | BTTS | NO | 2.41 | 51.16% | 38.05% | 13.12% | 23.30% |
| 04:21 | `1511410` | BTTS | NO | 2.20 | 51.16% | 42.41% | 8.75% | 12.56% |
| 04:21 | `1511410` | OU_25 | UNDER | 2.59 | 45.28% | 34.92% | 10.35% | 17.27% |
| 04:21 | `1511410` | OU_25 | UNDER | 2.50 | 45.28% | 37.50% | 7.78% | 13.19% |
| 04:25 | `1520899` | BTTS | YES | 2.20 | 55.69% | 42.41% | 13.28% | 22.51% |
| 04:25 | `1520899` | BTTS | YES | 2.05 | 55.69% | 45.19% | 10.50% | 14.16% |
| 04:25 | `1520899` | OU_25 | OVER | 2.15 | 56.14% | 43.72% | 12.42% | 20.70% |
| 04:25 | `1520899` | OU_25 | OVER | 2.08 | 56.14% | 44.83% | 11.31% | 16.77% |
| 04:29 | `1504314` | OU_25 | UNDER | 2.62 | 60.38% | 34.50% | 25.88% | 58.20% |
| 04:29 | `1504314` | OU_25 | UNDER | 2.50 | 60.38% | 37.50% | 22.88% | 50.96% |
| 04:29 | `1504314` | BTTS | NO | 2.50 | 61.03% | 36.87% | 24.16% | 52.57% |
| 04:29 | `1504314` | BTTS | NO | 2.38 | 61.03% | 39.13% | 21.90% | 45.24% |
| 04:43 | `1495566` | OU_25 | UNDER | 2.55 | 54.98% | 36.25% | 18.73% | 40.19% |
| 04:49 | `1504315` | BTTS | NO | 2.01 | 67.48% | 45.82% | 21.66% | 35.63% |
| 04:49 | `1504315` | BTTS | NO | 1.83 | 67.48% | 50.00% | 17.48% | 23.48% |
| 04:49 | `1504315` | OU_25 | UNDER | 1.80 | 71.77% | 50.95% | 20.82% | 29.19% |
| 04:49 | `1504315` | OU_25 | UNDER | 1.75 | 71.77% | 53.95% | 17.83% | 25.60% |
| 05:01 | `1505278` | BTTS | YES | 1.62 | 69.31% | 57.59% | 11.72% | 12.28% |
| 05:01 | `1505278` | BTTS | YES | 1.61 | 69.31% | 57.29% | 12.02% | 11.59% |
| 05:06 | `1521619` | BTTS | NO | 2.34 | 57.38% | 40.15% | 17.22% | 34.26% |
| 05:15 | `1635453` | OU_25 | UNDER | 3.00 | 43.25% | 31.19% | 12.05% | 29.74% |
| 05:15 | `1635453` | OU_25 | UNDER | 2.92 | 43.25% | 30.97% | 12.28% | 26.28% |
| 05:15 | `1635453` | BTTS | NO | 2.90 | 43.31% | 31.76% | 11.54% | 25.60% |
| 05:15 | `1635453` | BTTS | NO | 2.75 | 43.31% | 33.73% | 9.57% | 19.10% |
| 05:22 | `1499659` | OU_25 | UNDER | 1.62 | 76.89% | 58.14% | 18.75% | 24.56% |
| 05:22 | `1499659` | OU_25 | UNDER | 1.59 | 76.89% | 57.71% | 19.17% | 22.25% |
| 05:22 | `1499659` | BTTS | NO | 1.63 | 71.41% | 56.53% | 14.87% | 16.39% |
| 05:22 | `1499659` | BTTS | NO | 1.62 | 71.41% | 57.59% | 13.82% | 15.68% |
| 05:24 | `1500131` | BTTS | YES | 2.62 | 42.98% | 35.47% | 7.52% | 12.62% |
| 05:28 | `1499654` | BTTS | YES | 2.62 | 51.73% | 35.47% | 16.27% | 35.54% |
| 05:28 | `1499654` | BTTS | YES | 2.30 | 51.73% | 40.10% | 11.63% | 18.99% |
| 05:28 | `1499654` | OU_25 | OVER | 2.75 | 48.57% | 33.73% | 14.84% | 33.57% |
| 05:28 | `1499654` | OU_25 | OVER | 2.59 | 48.57% | 35.41% | 13.16% | 25.80% |
| 05:29 | `1600705` | OU_25 | UNDER | 1.65 | 70.29% | 57.14% | 13.15% | 15.98% |
| 05:40 | `1517355` | OU_25 | UNDER | 2.08 | 71.21% | 45.41% | 25.80% | 48.11% |
| 05:40 | `1517355` | OU_25 | UNDER | 2.02 | 71.21% | 45.41% | 25.80% | 43.84% |
| 05:40 | `1517355` | BTTS | NO | 2.10 | 65.17% | 44.30% | 20.87% | 36.85% |
| 05:40 | `1517355` | BTTS | NO | 2.08 | 65.17% | 44.09% | 21.08% | 35.55% |
| 05:44 | `1634028` | OU_25 | UNDER | 2.10 | 67.70% | 44.00% | 23.70% | 42.17% |
| 05:44 | `1634028` | BTTS | NO | 2.00 | 65.43% | 47.51% | 17.92% | 30.85% |
| 05:51 | `1510864` | OU_25 | UNDER | 2.63 | 45.65% | 35.38% | 10.27% | 20.06% |
| 05:51 | `1510864` | BTTS | NO | 2.77 | 42.82% | 33.57% | 9.25% | 18.62% |
| 05:52 | `1511228` | OU_25 | UNDER | 2.75 | 48.70% | 33.73% | 14.96% | 33.91% |
| 05:52 | `1511228` | BTTS | NO | 2.63 | 47.61% | 35.38% | 12.23% | 25.22% |
| 05:55 | `1536711` | OU_25 | OVER | 1.80 | 60.18% | 51.35% | 8.83% | 8.33% |
| 06:08 | `1536474` | OU_25 | UNDER | 1.85 | 66.48% | 50.00% | 16.48% | 23.00% |
| 06:08 | `1536474` | BTTS | NO | 2.05 | 59.96% | 46.34% | 13.62% | 22.92% |
| 06:17 | `1499660` | OU_25 | UNDER | 1.62 | 85.40% | 58.14% | 27.26% | 38.35% |
| 06:17 | `1499660` | OU_25 | UNDER | 1.57 | 85.40% | 58.36% | 27.05% | 34.08% |
| 06:17 | `1499660` | BTTS | NO | 1.50 | 82.15% | 62.50% | 19.65% | 23.23% |
| 06:17 | `1499660` | BTTS | NO | 1.49 | 82.15% | 61.89% | 20.26% | 22.41% |
| 06:32 | `1577950` | OU_25 | UNDER | 2.15 | 71.28% | 43.72% | 27.56% | 53.25% |
| 06:32 | `1577950` | OU_25 | UNDER | 2.13 | 71.28% | 43.05% | 28.23% | 51.83% |
| 06:32 | `1577950` | BTTS | NO | 2.24 | 63.17% | 40.90% | 22.28% | 41.51% |
| 06:33 | `1569111` | OU_25 | OVER | 1.48 | 80.34% | 61.15% | 19.19% | 18.91% |
| 06:33 | `1569111` | OU_25 | OVER | 1.44 | 80.34% | 64.53% | 15.81% | 15.70% |
| 06:33 | `1569111` | BTTS | YES | 1.43 | 79.03% | 64.16% | 14.87% | 13.01% |
| 06:33 | `1569112` | BTTS | NO | 2.50 | 59.30% | 36.71% | 22.59% | 48.24% |
| 06:33 | `1569112` | OU_25 | UNDER | 2.62 | 54.72% | 35.47% | 19.25% | 43.37% |
| 06:33 | `1569112` | OU_25 | UNDER | 2.62 | 54.72% | 34.50% | 20.22% | 43.37% |
| 06:34 | `1504312` | OU_25 | UNDER | 2.88 | 44.09% | 31.43% | 12.66% | 26.98% |
| 06:34 | `1504312` | OU_25 | UNDER | 2.75 | 44.09% | 33.73% | 10.36% | 21.25% |
| 06:34 | `1504312` | BTTS | NO | 2.25 | 52.42% | 40.94% | 11.48% | 17.95% |
| 06:34 | `1504312` | BTTS | NO | 2.20 | 52.42% | 42.41% | 10.01% | 15.33% |
| 06:35 | `1640090` | OU_25 | UNDER | 2.38 | 51.73% | 39.13% | 12.60% | 23.12% |
| 06:35 | `1640090` | OU_25 | UNDER | 2.30 | 51.73% | 39.31% | 12.42% | 18.98% |
| 06:39 | `1568188` | OU_25 | UNDER | 2.05 | 74.05% | 46.05% | 28.00% | 51.81% |
| 06:39 | `1568188` | OU_25 | UNDER | 1.95 | 74.05% | 47.01% | 27.04% | 44.40% |
| 06:39 | `1568188` | BTTS | NO | 2.12 | 65.94% | 43.32% | 22.62% | 39.79% |
| 06:40 | `1492983` | OU_25 | OVER | 1.44 | 75.68% | 64.53% | 11.15% | 8.99% |
| 06:41 | `1640770` | OU_25 | OVER | 2.15 | 55.19% | 43.72% | 11.47% | 18.65% |
| 06:41 | `1640770` | OU_25 | OVER | 2.11 | 55.19% | 43.43% | 11.76% | 16.45% |
| 06:42 | `1640771` | OU_25 | OVER | 2.00 | 70.31% | 47.37% | 22.94% | 40.63% |
| 06:42 | `1640771` | OU_25 | OVER | 1.90 | 70.31% | 48.23% | 22.08% | 33.60% |
| 06:42 | `1640771` | BTTS | YES | 1.92 | 63.37% | 47.83% | 15.55% | 21.68% |
| 06:45 | `1493706` | OU_25 | UNDER | 2.10 | 57.23% | 44.74% | 12.49% | 20.18% |
| 06:45 | `1493706` | OU_25 | UNDER | 2.06 | 57.23% | 44.47% | 12.75% | 17.89% |
| 06:45 | `1493706` | BTTS | NO | 2.27 | 52.70% | 40.58% | 12.13% | 19.64% |
| 06:45 | `1493706` | BTTS | NO | 2.20 | 52.70% | 42.41% | 10.30% | 15.95% |
| 06:45 | `1493715` | OU_25 | OVER | 1.50 | 73.28% | 62.50% | 10.78% | 9.92% |
| 06:45 | `1493715` | BTTS | YES | 1.50 | 72.49% | 62.50% | 9.99% | 8.74% |
| 06:50 | `1568807` | OU_25 | UNDER | 2.74 | 43.72% | 33.17% | 10.55% | 19.79% |
| 06:59 | `1536710` | OU_25 | UNDER | 1.74 | 81.21% | 53.10% | 28.11% | 41.30% |
| 06:59 | `1536710` | BTTS | NO | 1.86 | 73.70% | 50.53% | 23.17% | 37.08% |
| 07:50 | `1536709` | BTTS | NO | 1.71 | 66.28% | 54.88% | 11.40% | 13.34% |
| 07:56 | `1635454` | OU_25 | UNDER | 2.88 | 43.59% | 31.43% | 12.16% | 25.54% |
| 07:56 | `1635454` | OU_25 | UNDER | 2.75 | 43.59% | 33.73% | 9.86% | 19.87% |
| 07:56 | `1635454` | BTTS | NO | 3.00 | 41.40% | 30.72% | 10.69% | 24.20% |
| 07:56 | `1635454` | BTTS | NO | 2.75 | 41.40% | 33.73% | 7.67% | 13.85% |
| 07:59 | `1499658` | BTTS | YES | 2.20 | 50.64% | 42.41% | 8.23% | 11.40% |
| 08:05 | `1498829` | BTTS | NO | 1.50 | 71.84% | 62.50% | 9.34% | 7.76% |
| 08:05 | `1498829` | BTTS | NO | 1.49 | 71.84% | 61.89% | 9.95% | 7.04% |
| 08:06 | `1549649` | BTTS | NO | 1.71 | 63.95% | 53.91% | 10.04% | 9.36% |
| 08:07 | `1520896` | OU_25 | UNDER | 2.00 | 56.10% | 47.37% | 8.74% | 12.21% |
| 08:07 | `1520896` | OU_25 | UNDER | 1.98 | 56.10% | 47.06% | 9.04% | 11.08% |
| 08:07 | `1520896` | BTTS | NO | 2.21 | 50.30% | 41.84% | 8.46% | 11.16% |
| 08:07 | `1520896` | BTTS | NO | 2.20 | 50.30% | 42.41% | 7.89% | 10.66% |
| 08:08 | `1520898` | OU_25 | OVER | 2.25 | 53.05% | 41.86% | 11.19% | 19.36% |
| 08:08 | `1520898` | OU_25 | OVER | 2.20 | 53.05% | 42.41% | 10.64% | 16.71% |
| 08:08 | `1641144` | OU_25 | UNDER | 1.65 | 65.68% | 57.14% | 8.54% | 8.37% |
| 08:08 | `1641144` | OU_25 | UNDER | 1.63 | 65.68% | 56.30% | 9.38% | 7.06% |
| 08:12 | `1637844` | OU_25 | OVER | 2.05 | 59.35% | 46.05% | 13.29% | 21.66% |
| 08:12 | `1637844` | OU_25 | OVER | 1.92 | 59.35% | 47.83% | 11.52% | 13.94% |
| 08:12 | `1637845` | BTTS | NO | 1.46 | 74.81% | 62.76% | 12.06% | 9.23% |
| 08:12 | `1637845` | BTTS | NO | 1.44 | 74.81% | 64.53% | 10.28% | 7.73% |
| 08:18 | `1508560` | OU_25 | UNDER | 2.05 | 63.00% | 44.74% | 18.25% | 29.14% |
| 08:19 | `1637846` | OU_25 | OVER | 2.15 | 60.41% | 43.72% | 16.69% | 29.87% |
| 08:19 | `1637846` | OU_25 | OVER | 2.08 | 60.41% | 44.09% | 16.32% | 25.65% |
| 08:19 | `1637846` | BTTS | YES | 2.00 | 57.51% | 46.38% | 11.13% | 15.02% |
| 08:21 | `1493708` | OU_25 | UNDER | 1.80 | 64.37% | 52.63% | 11.74% | 15.87% |
| 08:21 | `1493708` | OU_25 | UNDER | 1.73 | 64.37% | 52.99% | 11.38% | 11.36% |
| 08:21 | `1493708` | BTTS | NO | 1.94 | 58.51% | 47.57% | 10.94% | 13.50% |
| 08:21 | `1493708` | BTTS | NO | 1.83 | 58.51% | 50.00% | 8.51% | 7.07% |
| 09:17 | `1517353` | BTTS | NO | 2.15 | 61.10% | 42.67% | 18.43% | 31.36% |
| 09:17 | `1517353` | BTTS | NO | 2.10 | 61.10% | 44.30% | 16.80% | 28.31% |
| 09:20 | `1583933` | OU_25 | UNDER | 2.43 | 65.07% | 37.21% | 27.86% | 58.11% |
| 09:20 | `1583933` | BTTS | NO | 2.66 | 57.33% | 34.48% | 22.85% | 52.50% |
| 09:26 | `1501486` | OU_25 | UNDER | 1.86 | 59.84% | 49.32% | 10.52% | 11.30% |
| 09:34 | `1577491` | BTTS | NO | 1.78 | 78.70% | 52.02% | 26.67% | 40.08% |
| 09:34 | `1577491` | OU_25 | UNDER | 1.62 | 85.38% | 58.99% | 26.39% | 38.31% |
| 09:47 | `1583932` | OU_25 | UNDER | 2.88 | 47.55% | 31.43% | 16.12% | 36.94% |
| 09:47 | `1583932` | BTTS | NO | 2.95 | 41.32% | 31.07% | 10.24% | 21.89% |
| 10:07 | `1577493` | BTTS | NO | 1.87 | 58.04% | 49.46% | 8.59% | 8.54% |
| 10:16 | `1501485` | OU_25 | UNDER | 2.05 | 66.52% | 44.74% | 21.77% | 36.36% |
| 10:18 | `1554169` | OU_25 | OVER | 2.20 | 52.70% | 42.11% | 10.60% | 15.94% |
| 10:18 | `1554169` | BTTS | YES | 1.91 | 58.38% | 48.66% | 9.73% | 11.51% |
| 10:42 | `1493709` | OU_25 | UNDER | 2.62 | 45.78% | 35.47% | 10.31% | 19.95% |
| 10:42 | `1493709` | OU_25 | UNDER | 2.49 | 45.78% | 36.32% | 9.47% | 14.00% |
| 10:42 | `1493709` | BTTS | NO | 2.50 | 46.27% | 37.50% | 8.77% | 15.68% |
| 10:42 | `1493709` | BTTS | NO | 2.50 | 46.27% | 36.87% | 9.40% | 15.68% |
| 10:51 | `1549799` | OU_25 | OVER | 1.85 | 62.37% | 51.32% | 11.05% | 15.38% |
| 10:51 | `1549799` | OU_25 | OVER | 1.83 | 62.37% | 50.94% | 11.43% | 14.13% |
| 11:18 | `1490496` | BTTS | YES | 1.40 | 76.46% | 66.27% | 10.19% | 7.04% |
| 11:21 | `1577490` | OU_25 | OVER | 2.13 | 53.24% | 44.82% | 8.42% | 13.39% |
| 11:40 | `1577943` | BTTS | NO | 2.27 | 86.42% | 41.34% | 45.08% | 96.17% |
| 11:41 | `1577948` | OU_25 | OVER | 1.44 | 80.42% | 64.53% | 15.89% | 15.80% |
| 11:41 | `1577950` | OU_25 | UNDER | 2.15 | 71.28% | 43.72% | 27.56% | 53.25% |
| 11:41 | `1577950` | OU_25 | UNDER | 2.13 | 71.28% | 43.05% | 28.23% | 51.83% |
| 11:41 | `1577950` | BTTS | NO | 2.24 | 63.17% | 40.90% | 22.28% | 41.51% |
| 11:42 | `1569111` | OU_25 | OVER | 1.44 | 80.34% | 64.53% | 15.81% | 15.70% |
| 11:42 | `1569112` | BTTS | NO | 2.34 | 59.30% | 39.22% | 20.08% | 38.75% |
| 11:42 | `1569112` | OU_25 | UNDER | 2.38 | 54.72% | 39.13% | 15.59% | 30.24% |
| 11:42 | `1569112` | OU_25 | UNDER | 2.24 | 54.72% | 40.43% | 14.30% | 22.58% |
| 11:43 | `1504312` | OU_25 | UNDER | 2.83 | 44.09% | 31.97% | 12.12% | 24.78% |
| 11:43 | `1504312` | OU_25 | UNDER | 2.75 | 44.09% | 33.73% | 10.36% | 21.25% |
| 11:43 | `1504312` | BTTS | NO | 2.25 | 52.42% | 40.94% | 11.48% | 17.95% |
| 11:43 | `1504312` | BTTS | NO | 2.20 | 52.42% | 42.41% | 10.01% | 15.33% |
| 11:44 | `1640090` | OU_25 | UNDER | 2.66 | 51.73% | 34.00% | 17.74% | 37.61% |
| 11:44 | `1640090` | OU_25 | UNDER | 2.62 | 51.73% | 35.47% | 16.26% | 35.54% |
| 11:47 | `1505278` | BTTS | YES | 1.62 | 69.31% | 57.59% | 11.72% | 12.28% |
| 11:47 | `1505278` | BTTS | YES | 1.61 | 69.31% | 57.29% | 12.02% | 11.59% |
| 11:47 | `1511023` | OU_25 | UNDER | 2.38 | 51.43% | 39.13% | 12.30% | 22.40% |
| 11:47 | `1511023` | OU_25 | UNDER | 2.38 | 51.43% | 38.02% | 13.41% | 22.40% |
| 11:47 | `1511023` | BTTS | NO | 2.52 | 46.97% | 36.36% | 10.60% | 18.35% |
| 11:48 | `1511410` | BTTS | NO | 2.25 | 51.16% | 41.10% | 10.06% | 15.12% |
| 11:48 | `1511410` | BTTS | NO | 2.22 | 51.16% | 41.27% | 9.89% | 13.58% |
| 11:48 | `1511410` | OU_25 | UNDER | 2.50 | 45.28% | 37.50% | 7.78% | 13.19% |
| 11:48 | `1511410` | OU_25 | UNDER | 2.49 | 45.28% | 36.32% | 8.96% | 12.74% |
| 11:48 | `1511408` | OU_25 | UNDER | 2.62 | 48.80% | 34.50% | 14.30% | 27.86% |
| 11:48 | `1511408` | OU_25 | UNDER | 2.50 | 48.80% | 37.50% | 11.30% | 22.00% |
| 11:48 | `1511408` | BTTS | NO | 2.52 | 48.00% | 36.36% | 11.64% | 20.96% |
| 11:48 | `1511408` | BTTS | NO | 2.50 | 48.00% | 37.50% | 10.50% | 20.00% |
| 11:53 | `1520899` | OU_25 | OVER | 2.10 | 56.14% | 44.74% | 11.40% | 17.89% |
| 11:53 | `1520899` | OU_25 | OVER | 2.08 | 56.14% | 44.83% | 11.31% | 16.77% |
| 11:53 | `1520899` | BTTS | YES | 2.10 | 55.69% | 44.30% | 11.39% | 16.94% |
| 11:53 | `1520899` | BTTS | YES | 2.05 | 55.69% | 45.19% | 10.50% | 14.16% |
| 11:54 | `1508557` | OU_25 | UNDER | 2.75 | 58.73% | 33.73% | 25.00% | 61.51% |
| 11:54 | `1508557` | OU_25 | UNDER | 2.74 | 58.73% | 33.01% | 25.73% | 60.93% |
| 11:54 | `1508557` | BTTS | NO | 1.50 | 79.68% | 62.50% | 17.18% | 19.52% |
| 11:55 | `1493705` | OU_25 | UNDER | 2.08 | 56.71% | 45.41% | 11.30% | 17.95% |
| 11:55 | `1493705` | OU_25 | UNDER | 1.98 | 56.71% | 46.34% | 10.36% | 12.28% |
| 11:55 | `1493705` | BTTS | NO | 2.10 | 51.54% | 44.30% | 7.24% | 8.23% |
| 11:55 | `1493705` | BTTS | NO | 2.10 | 51.54% | 43.85% | 7.69% | 8.23% |
| 11:58 | `1577487` | OU_25 | OVER | 2.19 | 58.24% | 43.56% | 14.69% | 27.55% |
| 11:59 | `1490497` | OU_25 | UNDER | 2.10 | 62.50% | 44.74% | 17.77% | 31.26% |
| 11:59 | `1490497` | BTTS | NO | 2.20 | 55.64% | 42.41% | 13.23% | 22.41% |

## What we can measure reliably today

For **registered picks**, durable PostgreSQL state already gives us:

- immutable model probability;
- raw and de-vig market probability;
- edge and expected value;
- entry odds;
- bookmaker/source;
- quote freshness / stale warning provenance;
- model version and policy/config fingerprint;
- operator PLAYED/SKIPPED state;
- closing price where captured;
- realized CLV where available;
- settlement outcome and realized P/L.

That is enough to measure betting-system performance by market, league, odds range, probability range, EV band, quote freshness, and model/policy version.

## Critical research gap: blocked signals do not yet have counterfactual CLV/outcome tracking

The rows in this document are **preliminary candidates that never reached registered-pick monitoring**.

Because exposure was already full:

- they did not progress to mandatory final quote refresh;
- they were not registered as picks;
- they do not automatically enter the current pick closing-line workflow;
- result acquisition is currently centered on registered-pick fixtures.

Therefore a blocked signal can have a logged preliminary EV but, under the current production design, we cannot reliably compute its later **counterfactual CLV** and outcome from the normal pick pipeline.

This matters because exposure policy cannot be optimized from registered picks alone. We need to know what happened to the opportunities that the cap rejected.

## Required research dataset

Before changing exposure or staking based on short-term P/L, every qualifying signal should eventually support a row with:

- signal_id;
- fixture_id / provider_fixture_id;
- home / away / competition / kickoff;
- model_version_id;
- model probability;
- bookmaker/source;
- market and selection;
- selected odds and companion odds;
- de-vig market probability;
- edge;
- EV;
- quote observed/captured timestamp and quote age;
- eligibility result;
- risk result;
- explicit blocked reason(s), including exposure;
- whether it was registered, PLAYED, or SKIPPED;
- final same-book / approved closing odds when available;
- CLV;
- final match result;
- whether the signal won/lost/voided counterfactually;
- flat-stake counterfactual P/L;
- policy/config fingerprint.

The research record should be independent from the bankroll ledger: observing a blocked signal must **not** reserve stake or exposure.

## Analysis plan

Do not pick a probability "sweet spot" by intuition. Measure it.

Primary grouping dimensions:

- model probability buckets: 40–45%, 45–50%, 50–55%, 55–60%, **60–65%**, 65–70%, 70–75%, 75%+;
- EV bands: 7–10%, 10–15%, 15–20%, 20–30%, 30%+;
- odds bands: 1.40–1.60, 1.61–1.80, 1.81–2.00, 2.01–2.50, 2.51–3.00, 3.01–3.50;
- market: OU 2.5 vs BTTS;
- selection;
- competition/league;
- bookmaker;
- FRESH vs USABLE_STALE and quote age;
- model version.

For each bucket measure:

- sample size;
- empirical hit rate;
- model mean probability;
- calibration error (empirical hit rate - model probability);
- Brier score;
- log loss;
- average/median EV;
- average/median CLV;
- positive-CLV rate;
- flat-stake ROI/yield;
- expected return vs realized return;
- maximum drawdown;
- confidence intervals where sample size permits.

A 60–65% model-probability bucket is only a "sweet spot" if it remains well calibrated and profitable out-of-sample; a high hit rate alone is insufficient if prices are too short.

## Kelly staking — future, not current production policy

Kelly should not be based on EV rank alone. For decimal odds `O`, calibrated win probability `p`, `b = O - 1`, and `q = 1 - p`:

`Kelly fraction = (b*p - q) / b`

Full Kelly is very sensitive to probability-estimation error. If the research dataset later supports variable staking, the safer candidate is **capped fractional Kelly** (for example quarter-Kelly or half-Kelly) with independent per-pick and total-open-exposure caps.

No Kelly change is justified from today's sample alone.

## Current interpretation

The current exposure cap is demonstrably capacity-constraining: many signals cleared the 7% edge / 7% EV thresholds but could not progress because 10 PLAYED stakes already occupied 3,000 RSD.

That does **not** yet prove the cap should be raised. The correct decision depends on what the blocked signals do after detection:

1. Do they beat closing prices?
2. Are model probabilities calibrated?
3. Do high-EV signals retain positive realized return?
4. What is the incremental drawdown from admitting more concurrent bets?
5. Are signals correlated by league, team, market, kickoff window, or shared model error?

Until those are measured, preserve the current model and exposure policy and build the evidence base.

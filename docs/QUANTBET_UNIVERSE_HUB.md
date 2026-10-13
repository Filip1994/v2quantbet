# QuantBet Universe Hub

`https://quantbet-dashboard-production.up.railway.app/hub` is a static launcher on
the existing `quantbet-dashboard` service. Its eight cards navigate in the same
tab to existing dashboard routes. CornerLab, GoalLab, H2HLab and CardLab all use
`quantbet-quantlab` with a different `lab` query parameter.

## Install

- Android: open `/hub` in Chrome, then use **Install app** or **Add to Home screen**.
- iPhone: open `/hub` in Safari, then **Share → Add to Home Screen**. Keep **Open as Web App** enabled where offered.

The manifest starts at `/hub` in standalone mode. PNG icons are served by the
same dashboard process. There is no service worker or offline data. The Hub
uses the dashboard's existing read authentication; each linked service keeps
its own authentication. No business data is fetched while rendering the Hub.

## Cross-domain navigation

The other Railway domains are outside the Hub manifest's scope. On iOS, Apple
documents that such links open in Safari View Controller. Android Chrome can
also show browser controls for an out-of-scope destination. Use **Done**, the
browser's **Back** control, or the QuantBet Home Screen icon to return. The
existing dashboard HTML pages also provide a fixed **Hub** button that points
directly to `/hub` in the same tab. JSON and health endpoints are unchanged.
The button does not proxy traffic or relax frame restrictions.

Actual Home Screen behavior depends on the device and browser version and
must be checked on an iPhone and Android phone after deployment. Desktop
responsive checks do not emulate those platform transitions.

# Team Maple 🍁 — FleetIQ v3

High-fidelity SIH Problem Statement 2 MVP: fleet visibility, shipment orchestration, capacity-aware allocation, route/ETA decision support, delay-risk alerts and operational analytics.

## Run
```bash
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000`.

## Demo story
1. Overview: show command center and live fleet map.
2. Live Ops: show vehicle capacity, dispatch recommendations and safeguards.
3. Shipments: create a Critical shipment and assign a smart-matched vehicle.
4. Route AI: test Heavy Traffic + Heavy Rain and show ETA/risk change.
5. Advance shipment through Assigned → In-Transit → Delivered; show capacity release.
6. Analytics: show utilization and delivery-health indicators.

## Demo tip: Route AI → Shipments loop
Every assignment now auto-computes a realistic ETA and delay-risk (randomized traffic/weather, not always best-case), so the Shipments board is live from the moment you assign a vehicle — no manual step needed. You can still override it: on the Route AI tab, run a scenario, then use "Apply this decision to a shipment" to push a specific what-if result onto a real shipment.

## New in this pass (v3.2) — liveliness + completeness
- **Auto route decisions on assignment** — ETA and delay-risk populate immediately on assign, using weighted-random traffic/weather so not everything shows "Low risk" by default.
- **Report Delay button** — the state machine already supported Assigned/In-Transit → Delayed, but the UI never exposed it. Now there's a dedicated button so judges can see delay-risk management work end-to-end.
- **Live countdown ETAs** — shipment rows show "42m left" ticking down in real time (client-side, refreshes every 5s) instead of a static duration, and flip to "overdue" in red if a shipment runs past its ETA.
- **Rejected candidates shown with reasons** — the vehicle-assignment modal now lists ineligible vehicles too ("Insufficient capacity", "In maintenance") alongside eligible ones, matching the load-allocation transparency the problem statement asks for.
- **Smooth marker movement** — the fleet map now animates vehicle markers moving toward their destination (CSS transition) instead of jumping between positions each refresh.
- **Fixed in v3.1:** Live Ops dispatch panel (was silently 404ing), Route AI never reaching the shipment record, and a shipment-status pill color mismatch.

## Important honesty
GPS is simulated: vehicles advance step-by-step toward their assigned shipment's destination each tick (not randomly), but there is no real GPS hardware. Route optimization tries OSRM road routing when internet is available and falls back to a straight-line geodesic estimate when it isn't (say so if asked — don't claim road-accuracy for the fallback). Delay risk is an explainable heuristic (traffic + weather + route scale + cargo + driver experience), not a trained ML model. Say this plainly if a judge asks "where is AI" — it's decision support, not predictive ML, and that's a defensible, honest answer.

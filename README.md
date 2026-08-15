# 🍁 Team Maple — FleetIQ Final SIH PS2 MVP

A local-first Smart Fleet Coordination and Logistics Management Platform for SIH Problem Statement 2.

## Core capabilities
- Fleet monitoring with clearly labelled simulated GPS
- Capacity-aware vehicle allocation and reassignment
- Shipment lifecycle and tracking
- Road-aware route optimization with OSRM fallback
- Transparent delay-risk heuristic
- Dispatch recommendations / operations center
- Before-vs-after route metrics
- Estimated operational cost
- Fleet utilization analytics
- SQLite persistence

## Run
```bash
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000`.

Windows: double-click `run.bat`.

## Demo flow
1. Control Tower → show fleet and simulated positions.
2. Shipments → create a Critical shipment.
3. Allocate → compare eligible/rejected vehicles.
4. Assign → observe load and ETA/risk update.
5. Route AI → calculate route under Heavy traffic/Heavy Rain.
6. Show before/after distance, ETA, risk and estimated cost.
7. Move shipment through Assigned → In-Transit → Delivered.
8. Return to Fleet/Analytics and show released capacity + updated KPIs.

## Accuracy / honesty
GPS is simulated. Traffic/weather are user-selected or simulated for demo decisions. Delay prediction is a transparent heuristic, not a trained ML model. Cost figures are estimates. Routing uses a free public road-routing service when available and a geographic fallback when offline.

## Known MVP limitations
- No physical GPS hardware integration.
- No production authentication/role management.
- SQLite is intended for local/internal MVP use.
- Public routing service is not guaranteed to be available.

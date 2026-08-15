# Architecture

Browser UI (HTML/CSS/JS + Leaflet) → Flask REST API → SQLite.

The browser polls the API for current state and sends explicit actions for shipment creation, allocation, status changes, route decisions and GPS simulation.

Routing: OSRM when reachable; geographic distance fallback offline.

Optimization: nearest-neighbour stop ordering plus capacity/proximity/cargo-aware dispatch scoring.

Risk: transparent rule-based heuristic using traffic, weather, distance, peak period, refrigeration and driver experience.

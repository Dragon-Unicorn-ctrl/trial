# Team Maple 🍁 — Smart Fleet Coordination & Logistics MVP

SIH PS2 internal-hackathon demonstrable MVP.

## Run
1. Install Python 3.10+.
2. In this folder run: `pip install -r requirements.txt`
3. Run: `python app.py`
4. Open: http://127.0.0.1:5000

The MVP uses simulated GPS data and a browser Leaflet map. Internet is needed for map tiles/CDN.

## Demo flow
Dashboard → Fleet → Shipments → Assign eligible vehicle → Optimize Route → Map → update shipment status.

## Honest MVP limitations
- GPS movement is simulated.
- Route optimizer is a nearest-neighbour heuristic over demo Indian cities, not a full production traffic-aware optimizer.
- Delay risk is a deterministic heuristic using distance/weather/traffic/cargo/driver experience/peak-hour inputs, not a trained ML model.
- Data is local SQLite.

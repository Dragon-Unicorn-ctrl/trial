from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import sqlite3
import json
import math
import random
import time
import hashlib
import hmac
import base64
import secrets
import os
from pathlib import Path
from datetime import datetime


BASE = Path(__file__).parent
DB = BASE / "fleet.db"
STATIC = BASE / "static"
SECRET = os.getenv("FLEET_SECRET", "fleet-demo-secret-change-me")
PORT = int(os.getenv("PORT", "5000"))


# -----------------------------
# City coordinates
# -----------------------------

CITY = {
    "Mumbai": (19.076, 72.8777),
    "Delhi": (28.7041, 77.1025),
    "Bengaluru": (12.9716, 77.5946),
    "Chennai": (13.0827, 80.2707),
    "Hyderabad": (17.385, 78.4867),
    "Pune": (18.5204, 73.8567),
    "Kolkata": (22.5726, 88.3639),
    "Ahmedabad": (23.0225, 72.5714),
}


# -----------------------------
# Database
# -----------------------------

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def ensure_columns(c):
    def table_columns(table_name):
        return {
            row[1]
            for row in c.execute(f"PRAGMA table_info({table_name})").fetchall()
        }

    vehicle_cols = table_columns("vehicles")

    if "total_dist" not in vehicle_cols:
        c.execute("ALTER TABLE vehicles ADD COLUMN total_dist REAL DEFAULT 0")

    if "driver_exp" not in vehicle_cols:
        c.execute("ALTER TABLE vehicles ADD COLUMN driver_exp REAL DEFAULT 5")

    if "weather" not in vehicle_cols:
        c.execute("ALTER TABLE vehicles ADD COLUMN weather TEXT DEFAULT 'Clear'")

    if "traffic" not in vehicle_cols:
        c.execute("ALTER TABLE vehicles ADD COLUMN traffic TEXT DEFAULT 'Normal'")

    shipment_cols = table_columns("shipments")

    if "distance_km" not in shipment_cols:
        c.execute("ALTER TABLE shipments ADD COLUMN distance_km REAL DEFAULT 0")

    if "predicted_delay_min" not in shipment_cols:
        c.execute("ALTER TABLE shipments ADD COLUMN predicted_delay_min REAL DEFAULT 0")

    if "risk" not in shipment_cols:
        c.execute("ALTER TABLE shipments ADD COLUMN risk TEXT DEFAULT 'Low'")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        200_000,
    )
    return f"{salt}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            200_000,
        )
        return secrets.compare_digest(derived.hex(), expected)
    except Exception:
        return False


def create_token(email: str, role: str) -> str:
    payload = {
        "sub": email,
        "role": role,
        "exp": time.time() + 86_400,
    }

    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = hmac.new(
        SECRET.encode("utf-8"),
        encoded.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return f"{encoded}.{signature}"


def verify_token(token: str):
    try:
        encoded, signature = token.split(".", 1)

        expected = hmac.new(
            SECRET.encode("utf-8"),
            encoded.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            return None

        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())

        if payload.get("exp", 0) < time.time():
            return None

        return payload
    except Exception:
        return None


def init_db():
    c = conn()
    cur = c.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            name TEXT,
            role TEXT DEFAULT 'manager',
            hashed_password TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_no TEXT UNIQUE,
            type TEXT,
            capacity_kg REAL,
            current_load_kg REAL DEFAULT 0,
            status TEXT DEFAULT 'Idle',
            driver TEXT,
            lat REAL,
            lon REAL,
            last_update TEXT DEFAULT CURRENT_TIMESTAMP,
            fuel_pct REAL DEFAULT 100,
            cargo_desc TEXT DEFAULT '',
            priority TEXT DEFAULT 'Standard',
            route TEXT DEFAULT '[]',
            origin TEXT DEFAULT '',
            destination TEXT DEFAULT '',
            speed_kph REAL DEFAULT 40,
            kmpl REAL DEFAULT 10,
            hour INTEGER DEFAULT 0,
            remaining_km REAL DEFAULT 0,
            remaining_min REAL DEFAULT 0,
            progress_pct REAL DEFAULT 0,
            total_dist REAL DEFAULT 0,
            driver_exp REAL DEFAULT 5,
            weather TEXT DEFAULT 'Clear',
            traffic TEXT DEFAULT 'Normal'
        );

        CREATE TABLE IF NOT EXISTS shipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_no TEXT UNIQUE,
            origin TEXT,
            destination TEXT,
            load_kg REAL,
            priority TEXT,
            status TEXT DEFAULT 'Pending',
            vehicle_id INTEGER,
            eta TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            distance_km REAL DEFAULT 0,
            predicted_delay_min REAL DEFAULT 0,
            risk TEXT DEFAULT 'Low'
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS telematics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER,
            plate TEXT,
            hour INTEGER,
            location TEXT,
            progress_pct REAL,
            remaining_min REAL,
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    ensure_columns(c)

    # Seed admin user
    if c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"] == 0:
        c.execute(
            """
            INSERT INTO users(email, name, role, hashed_password)
            VALUES(?, ?, ?, ?)
            """,
            (
                "admin@example.com",
                "Fleet Admin",
                "admin",
                hash_password("Admin123!"),
            ),
        )

    # Seed vehicles
    if c.execute("SELECT COUNT(*) n FROM vehicles").fetchone()["n"] == 0:
        seed_vehicles = [
            (
                "TM-101",
                "Truck",
                12000,
                "In Transit",
                "Ravi",
                17.385,
                78.4867,
                85,
                "Electronics",
                "High",
                '["Hyderabad","Bengaluru"]',
                "Hyderabad",
                "Bengaluru",
                50,
                8,
                0,
                0,
                0,
                0,
            ),
            (
                "TM-202",
                "Pickup",
                3500,
                "Idle",
                "Arjun",
                19.076,
                72.8777,
                90,
                "",
                "Standard",
                "[]",
                "",
                "",
                35,
                12,
                0,
                0,
                0,
                0,
            ),
            (
                "TM-303",
                "Van",
                1800,
                "In Transit",
                "Kiran",
                12.9716,
                77.5946,
                70,
                "Medical supplies",
                "Normal",
                '["Bengaluru","Chennai","Hyderabad"]',
                "Bengaluru",
                "Hyderabad",
                30,
                15,
                0,
                0,
                0,
                0,
            ),
            (
                "TM-404",
                "Truck",
                10000,
                "In Transit",
                "Meena",
                13.0827,
                80.2707,
                60,
                "Machinery",
                "Express",
                '["Chennai","Kolkata"]',
                "Chennai",
                "Kolkata",
                45,
                9,
                0,
                0,
                0,
                0,
            ),
            (
                "TM-505",
                "Motorbike",
                80,
                "Idle",
                "Sahil",
                18.5204,
                73.8567,
                95,
                "",
                "Standard",
                "[]",
                "",
                "",
                25,
                25,
                0,
                0,
                0,
                0,
            ),
            (
                "TM-606",
                "Pickup",
                4000,
                "Maintenance",
                "Priya",
                28.7041,
                77.1025,
                0,
                "",
                "Standard",
                "[]",
                "",
                "",
                0,
                0,
                0,
                0,
                0,
                0,
            ),
        ]

        for v in seed_vehicles:
            c.execute(
                """
                INSERT INTO vehicles(
                    vehicle_no, type, capacity_kg, status, driver, lat, lon,
                    fuel_pct, cargo_desc, priority, route, origin, destination,
                    speed_kph, kmpl, hour, remaining_km, remaining_min, progress_pct
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                v,
            )

    # Seed shipments
    if c.execute("SELECT COUNT(*) n FROM shipments").fetchone()["n"] == 0:
        c.executemany(
            """
            INSERT INTO shipments(
                shipment_no, origin, destination, load_kg, priority, status, vehicle_id, eta
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            [
                ("SHP-1001", "Hyderabad", "Bengaluru", 1800, "High", "In-Transit", 1, "~4h"),
                ("SHP-1002", "Mumbai", "Pune", 1200, "Normal", "Pending", None, None),
                ("SHP-1003", "Chennai", "Hyderabad", 900, "Normal", "Assigned", 3, "~7h"),
            ],
        )

    c.commit()
    update_all_shipment_metrics(c)
    c.commit()
    c.close()


# -----------------------------
# Utility helpers
# -----------------------------

def haversine(a, b):
    R = 6371.0

    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    x = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    )

    return R * 2.0 * math.atan2(math.sqrt(x), math.sqrt(1.0 - x))


def city_distance_km(origin, destination):
    if origin in CITY and destination in CITY:
        return haversine(CITY[origin], CITY[destination])
    return 0.0


def route_distance(route):
    total = 0.0

    for i in range(len(route) - 1):
        if route[i] in CITY and route[i + 1] in CITY:
            total += haversine(CITY[route[i]], CITY[route[i + 1]])

    return round(total, 2)


def optimize_route(origin, destination, stops=None):
    stops = stops or []

    if origin not in CITY or destination not in CITY:
        return {
            "route": [],
            "distance_km": 0.0,
            "base_eta_min": 0,
            "coordinates": [],
        }

    cities = [
        stop
        for stop in stops
        if stop in CITY and stop != origin and stop != destination
    ]

    ordered = [origin]
    remaining = cities.copy()
    current = origin
    total_dist = 0.0

    while remaining:
        nxt = min(
            remaining,
            key=lambda city: haversine(CITY[current], CITY[city]),
        )

        total_dist += haversine(CITY[current], CITY[nxt])
        ordered.append(nxt)
        remaining.remove(nxt)
        current = nxt

    total_dist += haversine(CITY[current], CITY[destination])
    ordered.append(destination)

    return {
        "route": ordered,
        "distance_km": round(total_dist, 1),
        "base_eta_min": round(total_dist * 60.0 / 40.0),
        "coordinates": [CITY[c] for c in ordered],
    }


def is_peak_hour():
    now = datetime.now()
    weekday = now.weekday()
    hour = now.hour

    return weekday < 5 and ((8 <= hour < 11) or (17 <= hour < 20))


def risk_score(
    dist,
    weather="Clear",
    traffic="Normal",
    refrigerated=False,
    driver_exp=5,
    peak=False,
):
    score = 0.0

    if dist > 500:
        score += 25
    elif dist > 200:
        score += 10

    score += {
        "Clear": 0,
        "Light Rain": 10,
        "Heavy Rain": 25,
        "Storm": 45,
    }.get(weather, 0)

    score += {
        "Low": 0,
        "Normal": 10,
        "Heavy": 25,
    }.get(traffic, 10)

    if refrigerated:
        score += 15

    if peak:
        score += 18

    score -= float(driver_exp or 5) * 0.8
    score = max(0.0, score)

    delay_min = int(round(score * 1.1))

    if delay_min > 45:
        risk = "High"
    elif delay_min > 15:
        risk = "Moderate"
    else:
        risk = "Low"

    return {
        "delay_min": delay_min,
        "risk": risk,
    }


def update_shipment_metrics(c, shipment_id):
    s = c.execute(
        "SELECT * FROM shipments WHERE id=?",
        (shipment_id,),
    ).fetchone()

    if not s:
        return

    distance = city_distance_km(s["origin"], s["destination"])

    risk = risk_score(
        distance,
        weather="Clear",
        traffic="Normal",
        refrigerated=False,
        driver_exp=5,
        peak=is_peak_hour(),
    )

    c.execute(
        """
        UPDATE shipments
        SET distance_km=?, predicted_delay_min=?, risk=?
        WHERE id=?
        """,
        (
            round(distance, 2),
            risk["delay_min"],
            risk["risk"],
            shipment_id,
        ),
    )


def update_all_shipment_metrics(c):
    rows = c.execute("SELECT id FROM shipments").fetchall()

    for row in rows:
        update_shipment_metrics(c, row["id"])


def log_event(message):
    c = conn()
    c.execute("INSERT INTO events(message) VALUES(?)", (message,))
    c.commit()
    c.close()


def log_event_conn(c, message):
    c.execute("INSERT INTO events(message) VALUES(?)", (message,))


def execute_sql(sql, args=(), fetchall=True):
    c = conn()
    cur = c.execute(sql, args)

    if fetchall:
        res = [dict(row) for row in cur.fetchall()]
    else:
        row = cur.fetchone()
        res = dict(row) if row else None

    c.close()
    return res


def content_type_for(file_path):
    suffix = Path(file_path).suffix.lower()

    return {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
    }.get(suffix, "application/octet-stream")


# -----------------------------
# Advanced dashboard helpers
# -----------------------------

def build_dashboard():
    c = conn()

    update_all_shipment_metrics(c)
    c.commit()

    total_vehicles = c.execute("SELECT COUNT(*) n FROM vehicles").fetchone()["n"]
    active_vehicles = c.execute(
        "SELECT COUNT(*) n FROM vehicles WHERE status='In Transit'"
    ).fetchone()["n"]
    idle_vehicles = c.execute(
        "SELECT COUNT(*) n FROM vehicles WHERE status='Idle'"
    ).fetchone()["n"]
    maintenance_vehicles = c.execute(
        "SELECT COUNT(*) n FROM vehicles WHERE status='Maintenance'"
    ).fetchone()["n"]

    active_shipments = c.execute(
        "SELECT COUNT(*) n FROM shipments WHERE status != 'Delivered'"
    ).fetchone()["n"]

    delayed_shipments = c.execute(
        "SELECT COUNT(*) n FROM shipments WHERE status='Delayed'"
    ).fetchone()["n"]

    pending_unassigned = c.execute(
        """
        SELECT COUNT(*) n
        FROM shipments
        WHERE status='Pending' AND COALESCE(vehicle_id, 0)=0
        """
    ).fetchone()["n"]

    total_capacity = c.execute(
        """
        SELECT COALESCE(SUM(capacity_kg), 0) total
        FROM vehicles
        WHERE status != 'Maintenance'
        """
    ).fetchone()["total"]

    active_load = c.execute(
        """
        SELECT COALESCE(SUM(current_load_kg), 0) load
        FROM vehicles
        WHERE status != 'Maintenance'
        """
    ).fetchone()["load"]

    fleet_utilization_pct = (
        round(active_load / total_capacity * 100.0, 1)
        if total_capacity
        else 0.0
    )

    shipment_status_rows = c.execute(
        """
        SELECT status, COUNT(*) n
        FROM shipments
        GROUP BY status
        """
    ).fetchall()

    vehicle_status_rows = c.execute(
        """
        SELECT status, COUNT(*) n
        FROM vehicles
        GROUP BY status
        """
    ).fetchall()

    high_delay_rows = c.execute(
        """
        SELECT shipment_no, origin, destination, COALESCE(predicted_delay_min, 0) delay_min
        FROM shipments
        WHERE status != 'Delivered'
          AND COALESCE(predicted_delay_min, 0) > 30
        ORDER BY COALESCE(predicted_delay_min, 0) DESC
        LIMIT 5
        """
    ).fetchall()

    delayed_list = [dict(row) for row in high_delay_rows]

    on_time_total = c.execute(
        """
        SELECT COUNT(*) n
        FROM shipments
        WHERE status != 'Delivered'
        """
    ).fetchone()["n"]

    on_time = c.execute(
        """
        SELECT COUNT(*) n
        FROM shipments
        WHERE status != 'Delivered'
          AND COALESCE(predicted_delay_min, 0) <= 15
        """
    ).fetchone()["n"]

    on_time_rate_pct = (
        round(on_time / on_time_total * 100.0, 1)
        if on_time_total
        else 100.0
    )

    alerts = []

    if pending_unassigned:
        alerts.append(
            {
                "severity": "warning",
                "message": f"{pending_unassigned} shipment(s) are pending assignment.",
            }
        )

    if delayed_shipments:
        alerts.append(
            {
                "severity": "critical",
                "message": f"{delayed_shipments} shipment(s) are marked delayed.",
            }
        )

    if maintenance_vehicles:
        alerts.append(
            {
                "severity": "info",
                "message": f"{maintenance_vehicles} vehicle(s) are under maintenance.",
            }
        )

    if delayed_list:
        alerts.append(
            {
                "severity": "critical",
                "message": f"{len(delayed_list)} active shipment(s) have high predicted delay.",
            }
        )

    result = {
        "total_vehicles": total_vehicles,
        "active_vehicles": active_vehicles,
        "idle_vehicles": idle_vehicles,
        "maintenance_vehicles": maintenance_vehicles,
        "active_shipments": active_shipments,
        "delayed_shipments": delayed_shipments,
        "pending_unassigned": pending_unassigned,
        "fleet_utilization_pct": fleet_utilization_pct,
        "on_time_rate_pct": on_time_rate_pct,
        "shipments_by_status": {
            row["status"]: row["n"]
            for row in shipment_status_rows
        },
        "vehicles_by_status": {
            row["status"]: row["n"]
            for row in vehicle_status_rows
        },
        "alerts": alerts,
        "delayed_shipments_list": delayed_list,
    }

    c.close()
    return result


def build_pool():
    c = conn()

    rows = c.execute(
        """
        SELECT
            id,
            vehicle_no AS plate,
            type AS vtype,
            capacity_kg,
            current_load_kg AS cargo_kg,
            status,
            driver,
            lat,
            lon,
            fuel_pct,
            cargo_desc,
            priority,
            route,
            origin,
            destination,
            speed_kph,
            kmpl,
            hour,
            remaining_km,
            remaining_min,
            progress_pct,
            total_dist,
            driver_exp,
            weather,
            traffic
        FROM vehicles
        ORDER BY id
        """
    ).fetchall()

    result = []

    for row in rows:
        v = dict(row)

        try:
            route_list = json.loads(v.get("route") or "[]")
        except Exception:
            route_list = []

        if not route_list and v.get("origin") and v.get("destination"):
            if v["origin"] in CITY and v["destination"] in CITY:
                route_list = [v["origin"], v["destination"]]

        v["route"] = route_list

        coords = []
        for city in route_list:
            if city in CITY:
                coords.append(CITY[city])

        if not coords:
            coords = [(v.get("lat") or 0.0, v.get("lon") or 0.0)]

        v["coords"] = coords

        numeric_fields = [
            "capacity_kg",
            "cargo_kg",
            "fuel_pct",
            "speed_kph",
            "kmpl",
            "hour",
            "remaining_km",
            "remaining_min",
            "progress_pct",
            "lat",
            "lon",
            "total_dist",
            "driver_exp",
        ]

        for key in numeric_fields:
            try:
                v[key] = float(v.get(key) or 0.0)
            except Exception:
                v[key] = 0.0

        v["free_capacity_kg"] = max(0.0, v["capacity_kg"] - v["cargo_kg"])

        distance = route_distance(route_list) if len(route_list) >= 2 else 0.0
        v["route_distance_km"] = distance

        speed = max(v["speed_kph"], 1.0)
        base_eta = round(distance / speed * 60.0, 1)

        risk = risk_score(
            distance,
            weather=v.get("weather") or "Clear",
            traffic=v.get("traffic") or "Normal",
            refrigerated=False,
            driver_exp=v.get("driver_exp") or 5,
            peak=is_peak_hour(),
        )

        v["base_eta_min"] = base_eta
        v["delay_min"] = risk["delay_min"]
        v["risk"] = risk["risk"]
        v["final_eta_min"] = round(base_eta + risk["delay_min"], 1)

        result.append(v)

    c.close()
    return result


def build_vehicle_optimization(vehicle_id):
    c = conn()

    v = c.execute(
        "SELECT * FROM vehicles WHERE id=?",
        (vehicle_id,),
    ).fetchone()

    if not v:
        c.close()
        return None

    try:
        route_list = json.loads(v["route"] or "[]")
    except Exception:
        route_list = []

    if not route_list and v["origin"] and v["destination"]:
        route_list = [v["origin"], v["destination"]]

    if len(route_list) < 2:
        result = {
            "vehicle_id": v["id"],
            "plate": v["vehicle_no"],
            "route": route_list,
            "coordinates": [(v["lat"], v["lon"])] if v["lat"] is not None else [],
            "distance_km": 0.0,
            "base_eta_min": 0,
            "delay_min": 0,
            "risk": "Low",
            "final_eta_min": 0,
        }

        c.close()
        return result

    origin = route_list[0]
    destination = route_list[-1]
    stops = route_list[1:-1]

    optimized = optimize_route(origin, destination, stops)

    risk = risk_score(
        optimized["distance_km"],
        weather=v["weather"] or "Clear",
        traffic=v["traffic"] or "Normal",
        refrigerated=False,
        driver_exp=v["driver_exp"] or 5,
        peak=is_peak_hour(),
    )

    result = {
        "vehicle_id": v["id"],
        "plate": v["vehicle_no"],
        "route": optimized["route"],
        "coordinates": optimized["coordinates"],
        "distance_km": optimized["distance_km"],
        "base_eta_min": optimized["base_eta_min"],
        "delay_min": risk["delay_min"],
        "risk": risk["risk"],
        "final_eta_min": optimized["base_eta_min"] + risk["delay_min"],
    }

    c.close()
    return result


# -----------------------------
# HTTP Handler
# -----------------------------

class FleetHandler(BaseHTTPRequestHandler):

    def send(self, code, data, ctype="application/json"):
        if isinstance(data, dict) or isinstance(data, list):
            body = json.dumps(data).encode()
        elif isinstance(data, bytes):
            body = data
        else:
            body = str(data).encode()

        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}

            raw = self.rfile.read(length)
            if not raw:
                return {}

            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def get_bearer_payload(self):
        auth = self.headers.get("Authorization", "")

        if not auth.startswith("Bearer "):
            return None

        return verify_token(auth[7:])

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        # Serve index.html
        if path == "/":
            candidates = [
                STATIC / "index.html",
                BASE / "index.html",
            ]

            for candidate in candidates:
                if candidate.exists():
                    self.send(
                        200,
                        candidate.read_bytes(),
                        content_type_for(candidate),
                    )
                    return

            self.send(404, {"error": "index.html not found"})
            return

        # Serve static files
        if path.startswith("/static/"):
            requested = (BASE / path.lstrip("/")).resolve()

            if (
                requested.exists()
                and requested.is_file()
                and str(requested).startswith(str(BASE.resolve()))
            ):
                self.send(
                    200,
                    requested.read_bytes(),
                    content_type_for(requested),
                )
            else:
                self.send(404, {"error": "Static file not found"})

            return

        # API
        if path == "/api/health":
            self.send(200, {"status": "ok"})
            return

        if path == "/api/cities":
            self.send(200, list(CITY.keys()))
            return

        if path == "/api/auth/me":
            payload = self.get_bearer_payload()

            if not payload:
                self.send(401, {"error": "Unauthorized"})
                return

            self.send(
                200,
                {
                    "email": payload.get("sub"),
                    "role": payload.get("role"),
                },
            )
            return

        if path == "/api/dashboard":
            self.send(200, build_dashboard())
            return

        if path == "/api/pool":
            self.send(200, build_pool())
            return

        if path == "/api/telematics":
            rows = execute_sql(
                """
                SELECT *
                FROM telematics
                ORDER BY id DESC
                LIMIT 30
                """
            )
            self.send(200, rows)
            return

        if path == "/api/vehicles":
            self.send(200, execute_sql("SELECT * FROM vehicles"))
            return

        if path == "/api/shipments":
            c = conn()
            update_all_shipment_metrics(c)
            c.commit()

            rows = c.execute(
                """
                SELECT s.*, v.vehicle_no
                FROM shipments s
                LEFT JOIN vehicles v ON s.vehicle_id = v.id
                ORDER BY s.id DESC
                """
            ).fetchall()

            result = [dict(row) for row in rows]

            c.close()
            self.send(200, result)
            return

        if path == "/api/events":
            self.send(
                200,
                execute_sql(
                    """
                    SELECT *
                    FROM events
                    ORDER BY id DESC
                    LIMIT 8
                    """
                ),
            )
            return

        parts = path.strip("/").split("/")

        # /api/eligible/<shipment_id>
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "eligible":
            try:
                sid = int(parts[2])
            except Exception:
                self.send(400, {"error": "Invalid shipment id"})
                return

            s = execute_sql(
                "SELECT * FROM shipments WHERE id=?",
                (sid,),
                fetchall=False,
            )

            if not s:
                self.send(404, {"error": "Shipment not found"})
                return

            vehicles = execute_sql(
                """
                SELECT *
                FROM vehicles
                WHERE status != 'Maintenance'
                  AND capacity_kg - current_load_kg >= ?
                ORDER BY capacity_kg - current_load_kg
                """,
                (s["load_kg"],),
            )

            self.send(200, vehicles)
            return

        # /api/tracking/<shipment_no>
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "tracking":
            shipment_no = parts[2]

            c = conn()
            update_all_shipment_metrics(c)
            c.commit()

            row = c.execute(
                """
                SELECT s.*, v.vehicle_no
                FROM shipments s
                LEFT JOIN vehicles v ON s.vehicle_id = v.id
                WHERE s.shipment_no=?
                """,
                (shipment_no,),
            ).fetchone()

            c.close()

            if not row:
                self.send(404, {"error": "Shipment not found"})
                return

            self.send(200, dict(row))
            return

        # /api/optimization/vehicle/<vehicle_id>
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "optimization" and parts[2] == "vehicle":
            try:
                vehicle_id = int(parts[3])
            except Exception:
                self.send(400, {"error": "Invalid vehicle id"})
                return

            result = build_vehicle_optimization(vehicle_id)

            if not result:
                self.send(404, {"error": "Vehicle not found"})
                return

            self.send(200, result)
            return

        self.send(404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        body = self.read_body()

        try:
            # Auth login
            if path == "/api/auth/login":
                email = (body.get("email") or "").lower().strip()
                password = body.get("password") or ""

                c = conn()
                user = c.execute(
                    "SELECT * FROM users WHERE email=?",
                    (email,),
                ).fetchone()
                c.close()

                if not user or not verify_password(password, user["hashed_password"]):
                    self.send(401, {"error": "Invalid email or password"})
                    return

                token = create_token(user["email"], user["role"])

                self.send(
                    200,
                    {
                        "token": token,
                        "user": {
                            "email": user["email"],
                            "name": user["name"],
                            "role": user["role"],
                        },
                    },
                )
                return

            # Auth register
            if path == "/api/auth/register":
                email = (body.get("email") or "").lower().strip()
                password = body.get("password") or ""
                name = body.get("name") or email.split("@")[0]

                if not email or len(password) < 8:
                    self.send(
                        400,
                        {
                            "error": "Email and password of at least 8 characters are required"
                        },
                    )
                    return

                c = conn()
                existing = c.execute(
                    "SELECT id FROM users WHERE email=?",
                    (email,),
                ).fetchone()

                if existing:
                    c.close()
                    self.send(400, {"error": "Email already registered"})
                    return

                c.execute(
                    """
                    INSERT INTO users(email, name, role, hashed_password)
                    VALUES(?, ?, ?, ?)
                    """,
                    (
                        email,
                        name,
                        "manager",
                        hash_password(password),
                    ),
                )

                c.commit()
                c.close()

                self.send(
                    201,
                    {
                        "ok": True,
                        "user": {
                            "email": email,
                            "name": name,
                            "role": "manager",
                        },
                    },
                )
                return

            # GPS simulation
            if path == "/api/simulate":
                c = conn()

                step_seconds = float(body.get("step_seconds", 300))

                vehicles = c.execute(
                    "SELECT * FROM vehicles WHERE status='In Transit'"
                ).fetchall()

                simulated = 0

                for v in vehicles:
                    try:
                        route = json.loads(v["route"] or "[]")
                    except Exception:
                        route = []

                    route = [city for city in route if city in CITY]

                    if len(route) >= 2:
                        total_dist = v["total_dist"] or route_distance(route)

                        if not total_dist:
                            total_dist = route_distance(route)

                        if not v["total_dist"] or float(v["total_dist"]) == 0.0:
                            c.execute(
                                "UPDATE vehicles SET total_dist=? WHERE id=?",
                                (total_dist, v["id"]),
                            )

                        speed = float(v["speed_kph"] or 40.0)
                        progress = float(v["progress_pct"] or 0.0)

                        remaining = max(
                            0.0,
                            total_dist * (1.0 - progress / 100.0),
                        )

                        step_km = max(
                            0.05,
                            speed * (step_seconds / 3600.0),
                        )

                        new_remaining = max(0.0, remaining - step_km)

                        if total_dist <= 0:
                            new_progress = 100.0
                        else:
                            new_progress = (1.0 - new_remaining / total_dist) * 100.0

                        dist_traveled = total_dist * (new_progress / 100.0)

                        lat = CITY[route[-1]][0]
                        lon = CITY[route[-1]][1]

                        cumulative = 0.0

                        for i in range(len(route) - 1):
                            segment = haversine(CITY[route[i]], CITY[route[i + 1]])

                            if cumulative + segment >= dist_traveled:
                                frac = (
                                    (dist_traveled - cumulative) / segment
                                    if segment
                                    else 0.0
                                )

                                lat = CITY[route[i]][0] + frac * (
                                    CITY[route[i + 1]][0] - CITY[route[i]][0]
                                )

                                lon = CITY[route[i]][1] + frac * (
                                    CITY[route[i + 1]][1] - CITY[route[i]][1]
                                )

                                break

                            cumulative += segment

                        new_hour = datetime.now().hour
                        remaining_min = (
                            new_remaining / speed * 60.0
                            if speed
                            else 0.0
                        )

                        c.execute(
                            """
                            UPDATE vehicles
                            SET lat=?, lon=?, progress_pct=?, remaining_km=?,
                                remaining_min=?, hour=?, total_dist=?
                            WHERE id=?
                            """,
                            (
                                lat,
                                lon,
                                new_progress,
                                new_remaining,
                                remaining_min,
                                new_hour,
                                total_dist,
                                v["id"],
                            ),
                        )

                        if new_hour != (v["hour"] or 0):
                            location = route[0] if route else "Unknown"
                            note = f"En route from {route[0]} to {route[-1]}"

                            c.execute(
                                """
                                INSERT INTO telematics(
                                    vehicle_id, plate, hour, location,
                                    progress_pct, remaining_min, note
                                )
                                VALUES(?,?,?,?,?,?,?)
                                """,
                                (
                                    v["id"],
                                    v["vehicle_no"],
                                    new_hour,
                                    location,
                                    new_progress,
                                    remaining_min,
                                    note,
                                ),
                            )

                        if new_progress >= 100.0:
                            c.execute(
                                """
                                UPDATE vehicles
                                SET status='Idle',
                                    progress_pct=100,
                                    remaining_km=0,
                                    remaining_min=0
                                WHERE id=?
                                """,
                                (v["id"],),
                            )

                            shipments = c.execute(
                                """
                                SELECT *
                                FROM shipments
                                WHERE vehicle_id=?
                                  AND status IN ('Assigned', 'In-Transit', 'Delayed')
                                """,
                                (v["id"],),
                            ).fetchall()

                            for s in shipments:
                                c.execute(
                                    """
                                    UPDATE shipments
                                    SET status='Delivered'
                                    WHERE id=?
                                    """,
                                    (s["id"],),
                                )

                            if shipments:
                                c.execute(
                                    """
                                    UPDATE vehicles
                                    SET current_load_kg=0
                                    WHERE id=?
                                    """,
                                    (v["id"],),
                                )

                                log_event_conn(
                                    c,
                                    f"Vehicle {v['vehicle_no']} completed route and delivered assigned shipments",
                                )

                        simulated += 1

                    else:
                        lat = float(v["lat"] or 0.0) + random.uniform(-0.01, 0.01)
                        lon = float(v["lon"] or 0.0) + random.uniform(-0.01, 0.01)

                        c.execute(
                            """
                            UPDATE vehicles
                            SET lat=?, lon=?, last_update=CURRENT_TIMESTAMP
                            WHERE id=?
                            """,
                            (lat, lon, v["id"]),
                        )

                        simulated += 1

                c.commit()
                c.close()

                self.send(
                    200,
                    {
                        "ok": True,
                        "simulated": simulated,
                    },
                )
                return

            # Quick add vehicle
            if path == "/api/pool":
                plate = (body.get("plate") or "").strip()
                vtype = body.get("type") or "Truck"
                capacity = float(body.get("capacity_kg", 1000))
                fuel = float(body.get("fuel_pct", 100))

                if not plate:
                    self.send(400, {"error": "Plate required"})
                    return

                existing = execute_sql(
                    "SELECT id FROM vehicles WHERE vehicle_no=?",
                    (plate,),
                    fetchall=False,
                )

                if existing:
                    self.send(400, {"error": "Vehicle plate already exists"})
                    return

                c = conn()

                c.execute(
                    """
                    INSERT INTO vehicles(
                        vehicle_no, type, capacity_kg, fuel_pct,
                        status, lat, lon
                    )
                    VALUES(?,?,?,?, 'Idle', ?, ?)
                    """,
                    (
                        plate,
                        vtype,
                        capacity,
                        fuel,
                        random.uniform(18, 28),
                        random.uniform(72, 80),
                    ),
                )

                c.commit()
                c.close()

                log_event(f"Added vehicle {plate}")

                self.send(201, {"ok": True})
                return

            # Add customized route vehicle
            if path == "/api/pool/custom":
                plate = (body.get("plate") or "").strip()
                vtype = body.get("type") or "Truck"
                capacity = float(body.get("capacity_kg", 1000))
                fuel = float(body.get("fuel_pct", 100))
                cargo_desc = body.get("cargo_desc") or ""
                cargo_kg = float(body.get("cargo_kg", 0))
                priority = body.get("priority") or "Standard"
                origin = body.get("origin") or ""
                destination = body.get("destination") or ""
                weather = body.get("weather") or "Clear"
                traffic = body.get("traffic") or "Normal"
                driver_exp = float(body.get("driver_exp", 5))

                stops_input = body.get("stops", "")

                if isinstance(stops_input, list):
                    stops = [
                        str(stop).strip()
                        for stop in stops_input
                        if str(stop).strip() in CITY
                    ]
                else:
                    stops = [
                        stop.strip()
                        for stop in str(stops_input).split(",")
                        if stop.strip() in CITY
                    ]

                if not plate or origin not in CITY or destination not in CITY:
                    self.send(
                        400,
                        {
                            "error": "Plate, valid origin and valid destination are required"
                        },
                    )
                    return

                if capacity < cargo_kg:
                    self.send(400, {"error": "Cargo exceeds capacity"})
                    return

                route_info = optimize_route(origin, destination, stops)
                route_json = json.dumps(route_info["route"])
                total_dist = route_info["distance_km"]

                speed = 40.0
                remaining_min = total_dist / speed * 60.0

                c = conn()

                cur = c.execute(
                    """
                    INSERT INTO vehicles(
                        vehicle_no, type, capacity_kg, current_load_kg, fuel_pct,
                        cargo_desc, priority, route, origin, destination,
                        speed_kph, remaining_km, remaining_min, progress_pct,
                        status, lat, lon
                    )
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        plate,
                        vtype,
                        capacity,
                        cargo_kg,
                        fuel,
                        cargo_desc,
                        priority,
                        route_json,
                        origin,
                        destination,
                        speed,
                        total_dist,
                        remaining_min,
                        0,
                        "In Transit",
                        CITY[origin][0],
                        CITY[origin][1],
                    ),
                )

                vehicle_id = cur.lastrowid

                c.execute(
                    """
                    UPDATE vehicles
                    SET weather=?, traffic=?, driver_exp=?, total_dist=?
                    WHERE id=?
                    """,
                    (
                        weather,
                        traffic,
                        driver_exp,
                        total_dist,
                        vehicle_id,
                    ),
                )

                c.commit()
                c.close()

                log_event(f"Added custom vehicle {plate} with optimized route")

                self.send(201, {"ok": True})
                return

            # AI matcher
            if path == "/api/ai-match":
                cargo_weight = float(body.get("cargo_weight", 1000))
                distance = float(body.get("distance_km", 200))
                weather = body.get("weather") or "Clear"
                traffic = body.get("traffic") or "Normal"

                rows = execute_sql(
                    """
                    SELECT
                        id,
                        vehicle_no AS plate,
                        type AS vtype,
                        capacity_kg,
                        current_load_kg AS cargo_kg,
                        fuel_pct,
                        speed_kph,
                        kmpl,
                        status,
                        route,
                        origin,
                        destination
                    FROM vehicles
                    WHERE status != 'Maintenance'
                      AND capacity_kg - current_load_kg >= ?
                    """,
                    (cargo_weight,),
                )

                candidates = []

                for v in rows:
                    headroom = float(v["capacity_kg"]) - float(v["cargo_kg"])
                    capacity_ratio = headroom / max(float(v["capacity_kg"]), 1.0)

                    kmpl = float(v["kmpl"] or 10.0)
                    fuel_pct = float(v["fuel_pct"] or 0.0)

                    fuel_needed_pct = min(
                        100.0,
                        (distance / max(kmpl, 0.1)) / 5.0,
                    )

                    fuel_sufficiency = max(
                        0.0,
                        100.0 - max(0.0, fuel_needed_pct - fuel_pct),
                    )

                    speed = float(v["speed_kph"] or 40.0)
                    eta_min = distance / max(speed, 1.0) * 60.0

                    risk = risk_score(
                        distance,
                        weather,
                        traffic,
                        driver_exp=5,
                        peak=is_peak_hour(),
                    )

                    adjusted_eta = eta_min + risk["delay_min"]

                    score = (
                        capacity_ratio * 30.0
                        + fuel_sufficiency * 0.5
                        + max(0.0, 100.0 - risk["delay_min"] / 10.0) * 0.5
                    )

                    score = min(100.0, score)

                    reasons = [
                        f"{headroom:.0f} kg free capacity",
                        f"Fuel: {fuel_pct:.0f}% (estimated need {fuel_needed_pct:.1f}%)",
                        f"ETA: {adjusted_eta:.0f} min",
                        f"Weather risk: {risk['risk']}",
                    ]

                    candidates.append(
                        {
                            "id": v["id"],
                            "plate": v["plate"],
                            "vtype": v["vtype"],
                            "score": round(score, 1),
                            "eta_min": round(adjusted_eta),
                            "fuel_needed_pct": round(fuel_needed_pct, 1),
                            "fuel_pct": fuel_pct,
                            "reasons": reasons,
                        }
                    )

                candidates.sort(key=lambda x: x["score"], reverse=True)

                self.send(200, {"candidates": candidates[:5]})
                return

            # Auto assign shipments
            if path in ("/api/auto-assign", "/api/shipments/auto-assign"):
                c = conn()

                pending = c.execute(
                    """
                    SELECT *
                    FROM shipments
                    WHERE status IN ('Pending', 'Delayed')
                      AND COALESCE(vehicle_id, 0)=0
                    """
                ).fetchall()

                assignments = []

                for s in pending:
                    candidates = c.execute(
                        """
                        SELECT *
                        FROM vehicles
                        WHERE status != 'Maintenance'
                          AND capacity_kg - current_load_kg >= ?
                        """,
                        (s["load_kg"],),
                    ).fetchall()

                    if not candidates:
                        continue

                    def score_vehicle(v):
                        origin_coord = CITY.get(s["origin"])

                        vehicle_coord = (
                            (v["lat"], v["lon"])
                            if v["lat"] is not None and v["lon"] is not None
                            else None
                        )

                        dist_to_origin = (
                            haversine(vehicle_coord, origin_coord)
                            if origin_coord and vehicle_coord
                            else 0.0
                        )

                        linehaul = city_distance_km(s["origin"], s["destination"])

                        load_ratio = (
                            float(v["current_load_kg"] or 0.0)
                            / max(float(v["capacity_kg"] or 1.0), 1.0)
                        ) * 10.0

                        return dist_to_origin + 0.5 * linehaul + load_ratio

                    best = min(candidates, key=score_vehicle)

                    distance = city_distance_km(s["origin"], s["destination"])
                    eta = f"~{int(round(distance / 40.0 * 60.0))}m"

                    c.execute(
                        """
                        UPDATE shipments
                        SET vehicle_id=?, status='Assigned', eta=?
                        WHERE id=?
                        """,
                        (
                            best["id"],
                            eta,
                            s["id"],
                        ),
                    )

                    c.execute(
                        """
                        UPDATE vehicles
                        SET current_load_kg=current_load_kg + ?,
                            status='In Transit'
                        WHERE id=?
                        """,
                        (
                            s["load_kg"],
                            best["id"],
                        ),
                    )

                    assignments.append(
                        {
                            "shipment_id": s["id"],
                            "shipment_no": s["shipment_no"],
                            "vehicle_id": best["id"],
                            "vehicle_no": best["vehicle_no"],
                        }
                    )

                    log_event_conn(
                        c,
                        f"Auto assigned {s['shipment_no']} to {best['vehicle_no']}",
                    )

                c.commit()
                c.close()

                self.send(
                    200,
                    {
                        "ok": True,
                        "assigned_count": len(assignments),
                        "assignments": assignments,
                    },
                )
                return

            # Create shipment
            if path == "/api/shipments":
                origin = body.get("origin")
                destination = body.get("destination")
                load = float(body.get("load_kg", 0))

                if origin not in CITY or destination not in CITY:
                    self.send(400, {"error": "Unsupported city"})
                    return

                shipment_no = "SHP-" + str(1000 + int(time.time()) % 9000)

                c = conn()

                cur = c.execute(
                    """
                    INSERT INTO shipments(
                        shipment_no, origin, destination, load_kg, priority
                    )
                    VALUES(?,?,?,?,?)
                    """,
                    (
                        shipment_no,
                        origin,
                        destination,
                        load,
                        body.get("priority", "Normal"),
                    ),
                )

                shipment_id = cur.lastrowid

                update_shipment_metrics(c, shipment_id)

                c.commit()
                c.close()

                log_event(f"Created shipment {shipment_no}")

                self.send(
                    201,
                    {
                        "shipment_no": shipment_no,
                    },
                )
                return

            parts = path.strip("/").split("/")

            # /api/shipments/<id>/assign
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "shipments" and parts[3] == "assign":
                sid = int(parts[2])
                vid = body.get("vehicle_id")

                c = conn()

                s = c.execute(
                    "SELECT * FROM shipments WHERE id=?",
                    (sid,),
                ).fetchone()

                v = c.execute(
                    "SELECT * FROM vehicles WHERE id=?",
                    (vid,),
                ).fetchone()

                if not s or not v:
                    c.close()
                    self.send(404, {"error": "Shipment or vehicle not found"})
                    return

                if s["status"] == "Delivered":
                    c.close()
                    self.send(400, {"error": "Delivered shipment cannot be assigned"})
                    return

                if (
                    v["status"] == "Maintenance"
                    or v["capacity_kg"] - v["current_load_kg"] < s["load_kg"]
                ):
                    c.close()
                    self.send(400, {"error": "Insufficient capacity"})
                    return

                distance = city_distance_km(s["origin"], s["destination"])
                eta = f"~{int(round(distance / 40.0 * 60.0))}m"

                c.execute(
                    """
                    UPDATE shipments
                    SET vehicle_id=?, status='Assigned', eta=?
                    WHERE id=?
                    """,
                    (
                        vid,
                        eta,
                        sid,
                    ),
                )

                c.execute(
                    """
                    UPDATE vehicles
                    SET current_load_kg=current_load_kg + ?,
                        status='In Transit'
                    WHERE id=?
                    """,
                    (
                        s["load_kg"],
                        vid,
                    ),
                )

                log_event_conn(
                    c,
                    f"Assigned {s['shipment_no']} to {v['vehicle_no']}",
                )

                c.commit()
                c.close()

                self.send(200, {"ok": True})
                return

            # /api/shipments/<id>/status
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "shipments" and parts[3] == "status":
                sid = int(parts[2])
                st = body.get("status")

                allowed = {
                    "Pending",
                    "Assigned",
                    "In-Transit",
                    "Delayed",
                    "Delivered",
                }

                if st not in allowed:
                    self.send(400, {"error": "Invalid status"})
                    return

                c = conn()

                s = c.execute(
                    "SELECT * FROM shipments WHERE id=?",
                    (sid,),
                ).fetchone()

                if not s:
                    c.close()
                    self.send(404, {"error": "Shipment not found"})
                    return

                c.execute(
                    "UPDATE shipments SET status=? WHERE id=?",
                    (
                        st,
                        sid,
                    ),
                )

                if (
                    st == "Delivered"
                    and s["vehicle_id"]
                    and s["status"] != "Delivered"
                ):
                    c.execute(
                        """
                        UPDATE vehicles
                        SET current_load_kg=MAX(0, current_load_kg - ?)
                        WHERE id=?
                        """,
                        (
                            s["load_kg"],
                            s["vehicle_id"],
                        ),
                    )

                log_event_conn(
                    c,
                    f"{s['shipment_no']} status changed to {st}",
                )

                c.commit()
                c.close()

                self.send(200, {"ok": True})
                return

            # Route optimization
            if path == "/api/optimize":
                origin = body.get("origin")
                destination = body.get("destination")

                if origin not in CITY or destination not in CITY:
                    self.send(400, {"error": "Unsupported origin/destination"})
                    return

                route_info = optimize_route(
                    origin,
                    destination,
                    body.get("stops", []),
                )

                peak = bool(body.get("peak", is_peak_hour()))

                risk_info = risk_score(
                    route_info["distance_km"],
                    body.get("weather", "Clear"),
                    body.get("traffic", "Normal"),
                    bool(body.get("refrigerated")),
                    float(body.get("driver_exp", 5)),
                    peak,
                )

                result = {
                    **route_info,
                    **risk_info,
                }

                result["final_eta_min"] = (
                    result["base_eta_min"] + result["delay_min"]
                )

                self.send(200, result)
                return

            # Delay prediction only
            if path == "/api/predict-delay":
                distance = float(
                    body.get(
                        "distance_km",
                        city_distance_km(
                            body.get("origin"),
                            body.get("destination"),
                        ),
                    )
                )

                result = risk_score(
                    distance,
                    body.get("weather", "Clear"),
                    body.get("traffic", "Normal"),
                    bool(body.get("refrigerated")),
                    float(body.get("driver_exp", 5)),
                    bool(body.get("peak", is_peak_hour())),
                )

                result["distance_km"] = round(distance, 2)

                self.send(200, result)
                return

            self.send(404, {"error": "Not found"})

        except Exception as e:
            self.send(500, {"error": str(e)})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        parts = path.strip("/").split("/")

        # /api/pool/<id>
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "pool":
            try:
                vid = int(parts[2])
            except Exception:
                self.send(400, {"error": "Invalid vehicle id"})
                return

            c = conn()

            vehicle = c.execute(
                "SELECT * FROM vehicles WHERE id=?",
                (vid,),
            ).fetchone()

            if not vehicle:
                c.close()
                self.send(404, {"error": "Vehicle not found"})
                return

            if float(vehicle["current_load_kg"] or 0.0) > 0.0:
                c.close()
                self.send(
                    400,
                    {
                        "error": "Cannot delete vehicle with active load. Deliver or unload first."
                    },
                )
                return

            c.execute(
                "DELETE FROM vehicles WHERE id=?",
                (vid,),
            )

            log_event_conn(c, f"Deleted vehicle id {vid}")

            c.commit()
            c.close()

            self.send(200, {"ok": True})
            return

        self.send(404, {"error": "Not found"})


# -----------------------------
# Main
# -----------------------------

if __name__ == "__main__":
    init_db()

    server = ThreadingHTTPServer(("0.0.0.0", PORT), FleetHandler)

    print(f"Server running on http://127.0.0.1:{PORT}")

    server.serve_forever()

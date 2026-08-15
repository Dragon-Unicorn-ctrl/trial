from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import sqlite3, json, math, random, time
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent
DB = BASE / 'fleet.db'
STATIC = BASE / 'static'

# City coordinates
CITY = {
    'Mumbai': (19.076, 72.8777),
    'Delhi': (28.7041, 77.1025),
    'Bengaluru': (12.9716, 77.5946),
    'Chennai': (13.0827, 80.2707),
    'Hyderabad': (17.385, 78.4867),
    'Pune': (18.5204, 73.8567),
    'Kolkata': (22.5726, 88.3639),
    'Ahmedabad': (23.0225, 72.5714)
}

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = conn()
    cur = c.cursor()
    # Vehicles table extended
    cur.executescript('''
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
            route TEXT DEFAULT '[]',          -- JSON array of city names
            origin TEXT DEFAULT '',
            destination TEXT DEFAULT '',
            speed_kph REAL DEFAULT 40,
            kmpl REAL DEFAULT 10,
            hour INTEGER DEFAULT 0,
            remaining_km REAL DEFAULT 0,
            remaining_min REAL DEFAULT 0,
            progress_pct REAL DEFAULT 0
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
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
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
    ''')

    # Seed initial vehicles with routes
    if cur.execute('SELECT COUNT(*) n FROM vehicles').fetchone()['n'] == 0:
        seed_vehicles = [
            ("TM-101", "Truck", 12000, "In Transit", "Ravi", 17.385, 78.4867, 85, "Electronics", "High", 
             '["Hyderabad","Bengaluru"]', "Hyderabad", "Bengaluru", 50, 8, 0, 0, 0, 0),
            ("TM-202", "Pickup", 3500, "Idle", "Arjun", 19.076, 72.8777, 90, "", "Standard", 
             '[]', "", "", 35, 12, 0, 0, 0, 0),
            ("TM-303", "Van", 1800, "In Transit", "Kiran", 12.9716, 77.5946, 70, "Medical supplies", "Normal",
             '["Bengaluru","Chennai","Hyderabad"]', "Bengaluru", "Hyderabad", 30, 15, 0, 0, 0, 0),
            ("TM-404", "Truck", 10000, "In Transit", "Meena", 13.0827, 80.2707, 60, "Machinery", "Express",
             '["Chennai","Kolkata"]', "Chennai", "Kolkata", 45, 9, 0, 0, 0, 0),
            ("TM-505", "Motorbike", 80, "Idle", "Sahil", 18.5204, 73.8567, 95, "", "Standard",
             '[]', "", "", 25, 25, 0, 0, 0, 0),
            ("TM-606", "Pickup", 4000, "Maintenance", "Priya", 28.7041, 77.1025, 0, "", "Standard",
             '[]', "", "", 0, 0, 0, 0, 0, 0)
        ]
        for v in seed_vehicles:
            cur.execute('''
                INSERT INTO vehicles(
                    vehicle_no, type, capacity_kg, status, driver, lat, lon,
                    fuel_pct, cargo_desc, priority, route, origin, destination,
                    speed_kph, kmpl, hour, remaining_km, remaining_min, progress_pct
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', v)

    # Seed a few shipments for compatibility
    if cur.execute('SELECT COUNT(*) n FROM shipments').fetchone()['n'] == 0:
        cur.executemany('''
            INSERT INTO shipments(shipment_no, origin, destination, load_kg, priority, status, vehicle_id, eta)
            VALUES (?,?,?,?,?,?,?,?)
        ''', [
            ("SHP-1001", "Hyderabad", "Bengaluru", 1800, "High", "In-Transit", 1, "~4h"),
            ("SHP-1002", "Mumbai", "Pune", 1200, "Normal", "Pending", None, None),
            ("SHP-1003", "Chennai", "Hyderabad", 900, "Normal", "Assigned", 3, "~7h")
        ])

    c.commit()
    c.close()

# Helper functions
def haversine(a, b):
    R = 6371
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    x = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(x), math.sqrt(1-x))

def optimize_route(origin, destination, stops=[]):
    """Return route and total distance."""
    cities = [c for c in stops if c in CITY and c != origin and c != destination]
    route = [origin] + cities + [destination]
    # simple greedy nearest neighbor
    ordered = [origin]
    remaining = cities.copy()
    cur = origin
    total_dist = 0
    while remaining:
        nxt = min(remaining, key=lambda c: haversine(CITY[cur], CITY[c]))
        total_dist += haversine(CITY[cur], CITY[nxt])
        ordered.append(nxt)
        remaining.remove(nxt)
        cur = nxt
    total_dist += haversine(CITY[cur], CITY[destination])
    ordered.append(destination)
    return {
        'route': ordered,
        'distance_km': round(total_dist, 1),
        'base_eta_min': round(total_dist * 60 / 40),  # assume 40 km/h average
        'coordinates': [CITY[c] for c in ordered]
    }

def risk_score(dist, weather='Clear', traffic='Normal', refrigerated=False, driver_exp=5, peak=False):
    score = 0
    if dist > 500: score += 25
    elif dist > 200: score += 10
    score += {'Clear':0, 'Light Rain':10, 'Heavy Rain':25, 'Storm':45}.get(weather, 0)
    score += {'Low':0, 'Normal':10, 'Heavy':25}.get(traffic, 10)
    if refrigerated: score += 15
    if peak: score += 18
    score -= driver_exp * 0.8
    score = max(0, score)
    delay_min = round(score * 1.1)
    risk = 'High' if delay_min > 45 else 'Moderate' if delay_min > 15 else 'Low'
    return {'delay_min': delay_min, 'risk': risk}

def log_event(msg):
    c = conn()
    c.execute('INSERT INTO events(message) VALUES(?)', (msg,))
    c.commit()
    c.close()

def execute_sql(sql, args=(), fetchall=True):
    c = conn()
    cur = c.execute(sql, args)
    if fetchall:
        res = [dict(row) for row in cur.fetchall()]
    else:
        res = cur.fetchone()
    c.close()
    return res

# ------------------- HTTP Handler -------------------
class FleetHandler(BaseHTTPRequestHandler):
    def send(self, code, data, ctype='application/json'):
        if isinstance(data, dict) or isinstance(data, list):
            body = json.dumps(data).encode()
        elif isinstance(data, bytes):
            body = data
        else:
            body = str(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get('Content-Length', '0'))
        return json.loads(self.rfile.read(length) if length else b'{}')

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Serve static index.html
        if path == '/':
            index_path = STATIC / 'index.html'
            if index_path.exists():
                self.send(200, index_path.read_bytes(), 'text/html; charset=utf-8')
            else:
                self.send(404, {'error': 'index.html not found'})
            return

        if path.startswith('/static/'):
            file_path = BASE / path.lstrip('/')
            if file_path.exists():
                self.send(200, file_path.read_bytes(), 'text/plain')
            else:
                self.send(404, {'error': 'not found'})
            return

        # ---- API endpoints ----
        if path == '/api/cities':
            self.send(200, list(CITY.keys()))
            return

        if path == '/api/pool':
            # Return all vehicles with computed fields for the frontend
            rows = execute_sql('''
                SELECT id, vehicle_no as plate, type as vtype, capacity_kg,
                       current_load_kg as cargo_kg, status, driver,
                       lat, lon, fuel_pct, cargo_desc, priority,
                       route, origin, destination,
                       speed_kph, kmpl, hour,
                       remaining_km, remaining_min, progress_pct
                FROM vehicles ORDER BY id
            ''')
            # Convert route string to list and compute coords
            for v in rows:
                route_str = v.get('route', '[]')
                try:
                    route_list = json.loads(route_str) if route_str else []
                except:
                    route_list = []
                v['route'] = route_list
                v['coords'] = [CITY.get(c, (0,0)) for c in route_list] if route_list else []
                # if no route, set coords to current position
                if not v['coords']:
                    v['coords'] = [(v['lat'], v['lon'])]
                # ensure lat/lon are floats
                v['lat'] = float(v['lat'])
                v['lon'] = float(v['lon'])
                # other numeric fields
                for key in ['capacity_kg', 'cargo_kg', 'fuel_pct', 'speed_kph', 'kmpl',
                            'hour', 'remaining_km', 'remaining_min', 'progress_pct']:
                    v[key] = float(v[key]) if v[key] is not None else 0
                # status chip mapping is done in frontend
            self.send(200, rows)
            return

        if path == '/api/telematics':
            rows = execute_sql('''
                SELECT * FROM telematics ORDER BY id DESC LIMIT 30
            ''')
            self.send(200, rows)
            return

        if path.startswith('/api/pool/') and len(path.split('/')) == 4:
            # DELETE /api/pool/<id>
            try:
                vid = int(path.split('/')[3])
                execute_sql('DELETE FROM vehicles WHERE id=?', (vid,), fetchall=False)
                log_event(f'Deleted vehicle id {vid}')
                self.send(200, {'ok': True})
            except Exception as e:
                self.send(400, {'error': str(e)})
            return

        # Other existing endpoints for compatibility
        if path == '/api/dashboard':
            c = conn()
            d = {
                'total_vehicles': c.execute('SELECT COUNT(*) n FROM vehicles').fetchone()['n'],
                'active_vehicles': c.execute("SELECT COUNT(*) n FROM vehicles WHERE status='In Transit'").fetchone()['n'],
                'idle_vehicles': c.execute("SELECT COUNT(*) n FROM vehicles WHERE status='Idle'").fetchone()['n'],
                'maintenance_vehicles': c.execute("SELECT COUNT(*) n FROM vehicles WHERE status='Maintenance'").fetchone()['n'],
                'active_shipments': c.execute("SELECT COUNT(*) n FROM shipments WHERE status!='Delivered'").fetchone()['n'],
                'delayed_shipments': c.execute("SELECT COUNT(*) n FROM shipments WHERE status='Delayed'").fetchone()['n'],
            }
            c.close()
            self.send(200, d)
            return

        if path == '/api/vehicles':
            self.send(200, execute_sql('SELECT * FROM vehicles'))
            return

        if path == '/api/shipments':
            self.send(200, execute_sql('SELECT s.*,v.vehicle_no FROM shipments s LEFT JOIN vehicles v ON s.vehicle_id=v.id ORDER BY s.id DESC'))
            return

        if path == '/api/events':
            self.send(200, execute_sql('SELECT * FROM events ORDER BY id DESC LIMIT 8'))
            return

        if path.startswith('/api/eligible/'):
            sid = int(path.rsplit('/', 1)[1])
            s = execute_sql('SELECT * FROM shipments WHERE id=?', (sid,), fetchall=False)
            if not s:
                self.send(404, {'error': 'Shipment not found'})
                return
            vehicles = execute_sql('''
                SELECT * FROM vehicles
                WHERE status != 'Maintenance' AND capacity_kg - current_load_kg >= ?
                ORDER BY capacity_kg - current_load_kg
            ''', (s['load_kg'],))
            self.send(200, vehicles)
            return

        self.send(404, {'error': 'Not found'})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self.read_body()

        try:
            if path == '/api/simulate':
                # Update positions and progress for in-transit vehicles
                c = conn()
                now = datetime.now()
                vehicles = c.execute("SELECT * FROM vehicles WHERE status='In Transit'").fetchall()
                for v in vehicles:
                    # Simulate movement along route
                    route_str = v['route'] or '[]'
                    try:
                        route = json.loads(route_str)
                    except:
                        route = []
                    if len(route) >= 2:
                        # current progress
                        progress = v['progress_pct'] or 0
                        total_dist = v.get('total_dist', 0)
                        if total_dist == 0:
                            # compute total distance
                            total_dist = sum(haversine(CITY[route[i]], CITY[route[i+1]]) for i in range(len(route)-1))
                            c.execute('UPDATE vehicles SET total_dist=? WHERE id=?', (total_dist, v['id']))
                        # move forward by speed over 5 sec (simulation step)
                        speed = v['speed_kph'] or 40
                        step_km = speed * (5 / 3600)  # 5 seconds
                        remaining = total_dist * (1 - progress/100)
                        new_remaining = max(0, remaining - step_km)
                        new_progress = (1 - new_remaining/total_dist) * 100 if total_dist > 0 else 100
                        # update position: interpolate along route
                        # find segment
                        dist_traveled = total_dist * (new_progress/100)
                        cum = 0
                        for i in range(len(route)-1):
                            seg = haversine(CITY[route[i]], CITY[route[i+1]])
                            if cum + seg >= dist_traveled:
                                frac = (dist_traveled - cum) / seg if seg > 0 else 0
                                lat = CITY[route[i]][0] + frac * (CITY[route[i+1]][0] - CITY[route[i]][0])
                                lon = CITY[route[i]][1] + frac * (CITY[route[i+1]][1] - CITY[route[i]][1])
                                break
                            cum += seg
                        else:
                            lat = CITY[route[-1]][0]
                            lon = CITY[route[-1]][1]
                        # update vehicle
                        c.execute('''
                            UPDATE vehicles SET lat=?, lon=?, progress_pct=?, remaining_km=?,
                                remaining_min=?, hour=?
                            WHERE id=?
                        ''', (lat, lon, new_progress, new_remaining,
                              new_remaining / speed * 60, int((now.hour) % 24), v['id']))
                        # log telematics every simulated hour (if hour changed)
                        new_hour = int((now.hour) % 24)
                        if new_hour != v['hour']:
                            loc = route[0] if len(route)>0 else 'Unknown'
                            note = f"En route from {route[0]} to {route[-1]}"
                            c.execute('''
                                INSERT INTO telematics (vehicle_id, plate, hour, location, progress_pct, remaining_min, note)
                                VALUES (?,?,?,?,?,?,?)
                            ''', (v['id'], v['vehicle_no'], new_hour, loc, new_progress,
                                  new_remaining / speed * 60, note))
                    else:
                        # No route, just random movement
                        lat = v['lat'] + random.uniform(-0.01, 0.01)
                        lon = v['lon'] + random.uniform(-0.01, 0.01)
                        c.execute('UPDATE vehicles SET lat=?, lon=?, last_update=CURRENT_TIMESTAMP WHERE id=?',
                                  (lat, lon, v['id']))
                c.commit()
                c.close()
                self.send(200, {'ok': True})
                return

            if path == '/api/pool':
                # Add a simple vehicle (quick add)
                plate = body.get('plate', '').strip()
                vtype = body.get('type', 'Truck')
                capacity = float(body.get('capacity_kg', 1000))
                fuel = float(body.get('fuel_pct', 100))
                if not plate:
                    self.send(400, {'error': 'Plate required'})
                    return
                # Check uniqueness
                existing = execute_sql('SELECT id FROM vehicles WHERE vehicle_no=?', (plate,), fetchall=False)
                if existing:
                    self.send(400, {'error': 'Vehicle plate already exists'})
                    return
                # Insert with defaults
                c = conn()
                c.execute('''
                    INSERT INTO vehicles (vehicle_no, type, capacity_kg, fuel_pct, status, lat, lon)
                    VALUES (?,?,?,?, 'Idle', ?, ?)
                ''', (plate, vtype, capacity, fuel, random.uniform(18, 28), random.uniform(72, 80)))
                c.commit()
                c.close()
                log_event(f'Added vehicle {plate}')
                self.send(201, {'ok': True})
                return

            if path == '/api/pool/custom':
                # Add vehicle with full route details
                plate = body.get('plate', '').strip()
                vtype = body.get('type', 'Truck')
                capacity = float(body.get('capacity_kg', 1000))
                fuel = float(body.get('fuel_pct', 100))
                cargo_desc = body.get('cargo_desc', '')
                cargo_kg = float(body.get('cargo_kg', 0))
                priority = body.get('priority', 'Standard')
                origin = body.get('origin', '')
                destination = body.get('destination', '')
                stops_str = body.get('stops', '')
                stops = [s.strip() for s in stops_str.split(',') if s.strip() in CITY]

                if not plate or origin not in CITY or destination not in CITY:
                    self.send(400, {'error': 'Plate, origin and destination required, all must be in city list'})
                    return
                if capacity < cargo_kg:
                    self.send(400, {'error': 'Cargo exceeds capacity'})
                    return

                # Compute route
                route_info = optimize_route(origin, destination, stops)
                route_json = json.dumps(route_info['route'])
                total_dist = route_info['distance_km']
                speed = 40  # default
                remaining_min = total_dist / speed * 60
                progress = 0

                c = conn()
                c.execute('''
                    INSERT INTO vehicles (
                        vehicle_no, type, capacity_kg, current_load_kg, fuel_pct,
                        cargo_desc, priority, route, origin, destination,
                        speed_kph, remaining_km, remaining_min, progress_pct, status, lat, lon
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ''', (plate, vtype, capacity, cargo_kg, fuel,
                      cargo_desc, priority, route_json, origin, destination,
                      speed, total_dist, remaining_min, 0, 'In Transit',
                      CITY[origin][0], CITY[origin][1]))
                c.commit()
                c.close()
                log_event(f'Added custom vehicle {plate} with route')
                self.send(201, {'ok': True})
                return

            if path == '/api/ai-match':
                # Evaluate vehicles for a cargo
                cargo_weight = float(body.get('cargo_weight', 1000))
                distance = float(body.get('distance_km', 200))
                weather = body.get('weather', 'Clear')
                traffic = body.get('traffic', 'Normal')

                # Get all vehicles not in maintenance and with enough capacity
                rows = execute_sql('''
                    SELECT id, vehicle_no as plate, type as vtype, capacity_kg, current_load_kg as cargo_kg,
                           fuel_pct, speed_kph, kmpl, status, route, origin, destination
                    FROM vehicles
                    WHERE status != 'Maintenance' AND capacity_kg - current_load_kg >= ?
                ''', (cargo_weight,))

                candidates = []
                for v in rows:
                    # Score based on capacity headroom, fuel, speed, etc.
                    headroom = v['capacity_kg'] - v['cargo_kg']
                    # fuel sufficiency: distance / (kmpl * fuel_pct/100) -> fuel needed
                    kmpl = v['kmpl'] or 10
                    fuel_needed = distance / (kmpl * (v['fuel_pct']/100))
                    fuel_sufficiency = max(0, 100 - (fuel_needed / (v['fuel_pct']+1)) * 100)  # approximate
                    # speed factor
                    speed = v['speed_kph'] or 40
                    eta_min = distance / speed * 60
                    # risk adjustment
                    risk = risk_score(distance, weather, traffic, driver_exp=5, peak=False)
                    delay = risk['delay_min']
                    adjusted_eta = eta_min + delay
                    # composite score: higher is better
                    score = (headroom / v['capacity_kg']) * 30 + (fuel_sufficiency * 0.5) + max(0, (100 - delay/10)) * 0.5
                    score = min(100, score)
                    reasons = [
                        f"{headroom:.0f} kg free capacity",
                        f"Fuel: {v['fuel_pct']:.0f}% (needs {fuel_needed:.1f}% of tank)",
                        f"ETA: {adjusted_eta:.0f} min",
                        f"Weather risk: {risk['risk']}"
                    ]
                    candidates.append({
                        'id': v['id'],
                        'plate': v['plate'],
                        'vtype': v['vtype'],
                        'score': round(score, 1),
                        'eta_min': round(adjusted_eta),
                        'fuel_needed_pct': round(fuel_needed, 1),
                        'fuel_pct': v['fuel_pct'],
                        'reasons': reasons
                    })

                candidates.sort(key=lambda x: x['score'], reverse=True)
                self.send(200, {'candidates': candidates[:5]})
                return

            # Shipment endpoints (existing)
            if path == '/api/shipments':
                origin = body.get('origin')
                dest = body.get('destination')
                load = float(body.get('load_kg', 0))
                if origin not in CITY or dest not in CITY:
                    self.send(400, {'error': 'Unsupported city'})
                    return
                no = 'SHP-' + str(1000 + int(time.time()) % 9000)
                c = conn()
                c.execute('INSERT INTO shipments(shipment_no, origin, destination, load_kg, priority) VALUES(?,?,?,?,?)',
                          (no, origin, dest, load, body.get('priority', 'Normal')))
                c.commit()
                c.close()
                log_event('Created shipment ' + no)
                self.send(201, {'shipment_no': no})
                return

            if path.startswith('/api/shipments/') and path.endswith('/assign'):
                sid = int(path.split('/')[3])
                vid = body.get('vehicle_id')
                c = conn()
                s = c.execute('SELECT * FROM shipments WHERE id=?', (sid,)).fetchone()
                v = c.execute('SELECT * FROM vehicles WHERE id=?', (vid,)).fetchone()
                if not s or not v:
                    c.close()
                    self.send(404, {'error': 'Shipment or vehicle not found'})
                    return
                if v['status'] == 'Maintenance' or v['capacity_kg'] - v['current_load_kg'] < s['load_kg']:
                    c.close()
                    self.send(400, {'error': 'Insufficient capacity'})
                    return
                c.execute('UPDATE shipments SET vehicle_id=?, status="Assigned" WHERE id=?', (vid, sid))
                c.execute('UPDATE vehicles SET current_load_kg=current_load_kg+?, status="In Transit" WHERE id=?',
                          (s['load_kg'], vid))
                c.commit()
                c.close()
                log_event(f'Assigned {s["shipment_no"]} to {v["vehicle_no"]}')
                self.send(200, {'ok': True})
                return

            if path.startswith('/api/shipments/') and path.endswith('/status'):
                sid = int(path.split('/')[3])
                st = body.get('status')
                if st not in ['Pending','Assigned','In-Transit','Delayed','Delivered']:
                    self.send(400, {'error': 'Invalid status'})
                    return
                c = conn()
                s = c.execute('SELECT * FROM shipments WHERE id=?', (sid,)).fetchone()
                if not s:
                    c.close()
                    self.send(404, {'error': 'not found'})
                    return
                c.execute('UPDATE shipments SET status=? WHERE id=?', (st, sid))
                if st == 'Delivered' and s['vehicle_id']:
                    c.execute('UPDATE vehicles SET current_load_kg=MAX(0,current_load_kg-?) WHERE id=?',
                              (s['load_kg'], s['vehicle_id']))
                c.commit()
                c.close()
                log_event(f'{s["shipment_no"]} status → {st}')
                self.send(200, {'ok': True})
                return

            if path == '/api/optimize':
                origin = body.get('origin')
                dest = body.get('destination')
                if origin not in CITY or dest not in CITY:
                    self.send(400, {'error': 'Unsupported origin/destination'})
                    return
                route_info = optimize_route(origin, dest, body.get('stops', []))
                risk_info = risk_score(
                    route_info['distance_km'],
                    body.get('weather', 'Clear'),
                    body.get('traffic', 'Normal'),
                    bool(body.get('refrigerated')),
                    float(body.get('driver_exp', 5)),
                    bool(body.get('peak'))
                )
                result = {**route_info, **risk_info}
                result['final_eta_min'] = result['base_eta_min'] + result['delay_min']
                self.send(200, result)
                return

            self.send(404, {'error': 'Not found'})
        except Exception as e:
            self.send(500, {'error': str(e)})

# ------------------- Main -------------------
if __name__ == '__main__':
    init_db()
    server = ThreadingHTTPServer(('0.0.0.0', 5000), FleetHandler)
    print('Server running on http://127.0.0.1:5000')
    server.serve_forever()

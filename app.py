from flask import Flask, jsonify, request, send_from_directory
import sqlite3, math, random, time, urllib.parse, urllib.request, json as jsonlib
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB = BASE / "fleet.db"

app = Flask(__name__, static_folder="static", static_url_path="")

CITIES = {
    "Mumbai": (19.0760,72.8777),
    "Pune": (18.5204,73.8567),
    "Nashik": (19.9975,73.7898),
    "Ahmedabad": (23.0225,72.5714),
    "Hyderabad": (17.3850,78.4867),
    "Bengaluru": (12.9716,77.5946),
    "Chennai": (13.0827,80.2707),
    "Delhi": (28.6139,77.2090),
    "Kolkata": (22.5726,88.3639),
    "Thane": (19.2183,72.9781),
}

SPEEDS = {"Truck":45, "Van":55, "Pickup":50, "Motorbike":50}

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS vehicles(
      id TEXT PRIMARY KEY, plate TEXT, driver TEXT, type TEXT,
      capacity REAL, load REAL DEFAULT 0, status TEXT DEFAULT 'Idle',
      lat REAL, lon REAL, fuel REAL DEFAULT 70, updated REAL
    );
    CREATE TABLE IF NOT EXISTS shipments(
      id TEXT PRIMARY KEY, title TEXT, origin TEXT, destination TEXT,
      weight REAL, priority TEXT, status TEXT DEFAULT 'Pending',
      vehicle_id TEXT, eta_min INTEGER, route_distance REAL,
      delay_risk TEXT DEFAULT 'Low', delay_min INTEGER DEFAULT 0,
      created REAL, updated REAL
    );
    CREATE TABLE IF NOT EXISTS events(
      id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, message TEXT,
      created REAL
    );
    """)
    cols=[r[1] for r in c.execute("PRAGMA table_info(shipments)").fetchall()]
    if "eta_set" not in cols:
        c.execute("ALTER TABLE shipments ADD COLUMN eta_set REAL")
    if c.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 0:
        now=time.time()
        seed=[
          ("MH01","MH-01-AB-1201","Aarav Sharma","Truck",14000,4200,"In Transit",19.15,72.88,78),
          ("MH02","MH-02-CD-4521","Riya Patel","Truck",12000,8500,"In Transit",18.68,73.80,61),
          ("KA01","KA-01-EF-7710","Vikram Rao","Van",3500,0,"Idle",12.98,77.60,88),
          ("TN01","TN-01-GH-3020","Meera Iyer","Truck",10000,0,"Idle",13.10,80.25,72),
          ("TS01","TS-01-JK-6190","Kabir Khan","Pickup",2500,600,"Idle",17.42,78.49,66),
          ("DL01","DL-01-LM-8850","Neha Singh","Van",4000,0,"Maintenance",28.62,77.21,35),
        ]
        c.executemany("INSERT INTO vehicles VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      [(a,b,c1,d,e,f,g,h,i,j,now) for a,b,c1,d,e,f,g,h,i,j in seed])
        shipments=[
          ("S001","Electronics components","Mumbai","Pune",4200,"High","In-Transit","MH01",None,None,"Low",0),
          ("S002","Automotive spare parts","Mumbai","Hyderabad",6500,"Critical","In-Transit","MH02",None,None,"Moderate",0),
          ("S003","Temperature-sensitive cargo","Thane","Nashik",1800,"Critical","Pending",None,None,None,"Low",0),
          ("S004","Consumer electronics","Pune","Bengaluru",1200,"Normal","Pending",None,None,None,"Low",0)
        ]
        c.executemany("""INSERT INTO shipments
          (id,title,origin,destination,weight,priority,status,vehicle_id,eta_min,route_distance,delay_risk,delay_min,created,updated)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          [(s[0],s[1],s[2],s[3],s[4],s[5],s[6],s[7],s[8],s[9],s[10],s[11],now,now) for s in shipments])
        c.execute("INSERT INTO events(kind,message,created) VALUES(?,?,?)",("SYSTEM","Team Maple FleetIQ initialized",now))
        c.commit()
    c.close()

def hav(a,b,c,d):
    R=6371
    p1,p2=math.radians(a),math.radians(c)
    dp=math.radians(c-a); dl=math.radians(d-b)
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R*2*math.atan2(math.sqrt(x),math.sqrt(1-x))

def log(kind,msg):
    c=db(); c.execute("INSERT INTO events(kind,message,created) VALUES(?,?,?)",(kind,msg,time.time())); c.commit(); c.close()

def road_route(points):
    # Try OSRM road routing first; fall back safely to geodesic segments.
    if len(points)<2: return points,0
    coords=";".join(f"{lon},{lat}" for lat,lon in points)
    url=f"https://router.project-osrm.org/route/v1/driving/{coords}?overview=full&geometries=geojson&steps=false"
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"TeamMaple-FleetIQ/2.0"})
        with urllib.request.urlopen(req,timeout=4) as r:
            data=jsonlib.loads(r.read().decode())
        if data.get("code")=="Ok":
            geom=data["routes"][0]["geometry"]["coordinates"]
            line=[(lat,lon) for lon,lat in geom]
            return line, data["routes"][0]["distance"]/1000
    except Exception:
        pass
    d=sum(hav(points[i][0],points[i][1],points[i+1][0],points[i+1][1]) for i in range(len(points)-1))
    return points,d

def optimize(origin,destination,stops=None,vehicle_type="Truck",weather="Clear",traffic="Normal",peak=False,refrigerated=False,driver_exp=5):
    stops=stops or []
    names=[origin]+[s for s in stops if s not in (origin,destination)]+[destination]
    # For a small demo set, order optional stops by nearest-neighbour, but route geometry is road-aware when online.
    ordered=[origin]; remaining=names[1:-1]; cur=origin
    while remaining:
        nxt=min(remaining,key=lambda x:hav(*CITIES[cur],*CITIES[x]))
        ordered.append(nxt); remaining.remove(nxt); cur=nxt
    ordered.append(destination)
    pts=[CITIES[x] for x in ordered]
    line,dist=road_route(pts)
    speed=SPEEDS.get(vehicle_type,45)
    traffic_factor={"Low":1.0,"Normal":1.12,"Heavy":1.35}.get(traffic,1.12)
    weather_factor={"Clear":1.0,"Light Rain":1.08,"Heavy Rain":1.18,"Storm":1.35}.get(weather,1.0)
    base=max(1,round((dist/speed)*60*traffic_factor*weather_factor))
    risk=max(0, min(100,
        (18 if dist>500 else 8 if dist>200 else 2)
        + {"Clear":0,"Light Rain":8,"Heavy Rain":20,"Storm":38}.get(weather,0)
        + {"Low":0,"Normal":8,"Heavy":22}.get(traffic,8)
        + (12 if refrigerated else 0) + (15 if peak else 0)
        - driver_exp*0.9))
    risk_level="High" if risk>=55 else "Moderate" if risk>=25 else "Low"
    delay=round(risk*0.65)
    return {"sequence":ordered,"geometry":line,"distance_km":round(dist,1),
            "base_eta_min":base,"delay_min":delay,"eta_min":base+delay,
            "risk":round(risk),"risk_level":risk_level}

def serialize_vehicle(r):
    return dict(r)

def serialize_ship(r):
    d=dict(r); d["weight"]=float(d["weight"]); return d

@app.get("/")
def home(): return send_from_directory(app.static_folder,"index.html")

@app.get("/api/summary")
def summary():
    c=db()
    vs=[dict(x) for x in c.execute("SELECT * FROM vehicles").fetchall()]
    ss=[dict(x) for x in c.execute("SELECT * FROM shipments ORDER BY created DESC").fetchall()]
    ev=[dict(x) for x in c.execute("SELECT * FROM events ORDER BY created DESC LIMIT 12").fetchall()]
    c.close()
    return jsonify({
      "vehicles":vs,"shipments":ss,"events":ev,
      "kpis":{"total":len(vs),"available":sum(v["status"]=="Idle" for v in vs),
               "in_transit":sum(v["status"]=="In Transit" for v in vs),
               "maintenance":sum(v["status"]=="Maintenance" for v in vs),
               "active_shipments":sum(s["status"] not in ("Delivered",) for s in ss),
               "delayed":sum(s["delay_risk"]=="High" or s["status"]=="Delayed" for s in ss)}
    })

@app.post("/api/simulate")
def simulate():
    c=db()
    rows=c.execute("SELECT * FROM vehicles WHERE status='In Transit'").fetchall()
    now=time.time()
    changed=[]
    for v in rows:
        # Move toward the destination of whatever shipment this vehicle is carrying,
        # instead of a pure random walk, so movement visibly follows the route.
        ship=c.execute("SELECT * FROM shipments WHERE vehicle_id=? AND status IN ('Assigned','In-Transit') ORDER BY updated DESC LIMIT 1",(v["id"],)).fetchone()
        lat,lon=float(v["lat"]),float(v["lon"])
        if ship and ship["destination"] in CITIES:
            dlat,dlon=CITIES[ship["destination"]]
            remaining=hav(lat,lon,dlat,dlon)
            if remaining>2:
                step=0.06  # advance ~6% of the remaining distance per tick
                lat=lat+(dlat-lat)*step+random.uniform(-0.01,0.01)
                lon=lon+(dlon-lon)*step+random.uniform(-0.01,0.01)
            else:
                lat,lon=dlat,dlon  # arrived; hold at destination
        else:
            lat=lat+random.uniform(-0.025,0.025)
            lon=lon+random.uniform(-0.025,0.025)
        c.execute("UPDATE vehicles SET lat=?,lon=?,updated=? WHERE id=?",(lat,lon,now,v["id"]))
        changed.append(v["id"])
    c.commit(); c.close()
    return jsonify({"updated":changed,"mode":"simulation"})

def auto_decision(s, v):
    """Compute a plausible route decision at assignment time so ETA/risk populate
    immediately, without requiring a manual Route AI run. Traffic/weather are
    picked with realistic weighted randomness rather than always-best-case."""
    traffic=random.choices(["Low","Normal","Heavy"],weights=[30,50,20])[0]
    weather=random.choices(["Clear","Light Rain","Heavy Rain","Storm"],weights=[60,22,14,4])[0]
    return optimize(s["origin"],s["destination"],[],v["type"],weather,traffic,
                     peak=random.random()<0.25,refrigerated=False,driver_exp=random.uniform(2,15))

@app.get("/api/eligible/<shipment_id>")
def eligible(shipment_id):
    c=db(); s=c.execute("SELECT * FROM shipments WHERE id=?",(shipment_id,)).fetchone()
    if not s: c.close(); return jsonify({"error":"Shipment not found"}),404
    rows=c.execute("SELECT * FROM vehicles").fetchall()
    ok=[]; rejected=[]
    for v in rows:
        free=v["capacity"]-v["load"]
        d=hav(v["lat"],v["lon"],*CITIES.get(s["origin"],CITIES["Mumbai"]))
        if v["status"]=="Maintenance":
            rejected.append({**dict(v),"reason":"In maintenance"}); continue
        if free<s["weight"]:
            rejected.append({**dict(v),"reason":f"Insufficient capacity ({round(free)} kg free, {round(s['weight'])} kg needed)"}); continue
        score=max(0,100-d*1.4)
        score += min(25,(free-s["weight"])/max(v["capacity"],1)*25)
        ok.append({**dict(v),"free_capacity":round(free),"distance_to_pickup":round(d,1),"match_score":round(min(100,score))})
    c.close()
    ok=sorted(ok,key=lambda x:x["match_score"],reverse=True)
    return jsonify({"eligible":ok,"rejected":rejected})

@app.post("/api/shipments")
def create_shipment():
    x=request.get_json(force=True)
    req=["title","origin","destination","weight","priority"]
    if any(k not in x for k in req): return jsonify({"error":"Missing required fields"}),400
    try: weight=float(x["weight"])
    except: return jsonify({"error":"Weight must be numeric"}),400
    if weight<=0 or x["origin"] not in CITIES or x["destination"] not in CITIES or x["origin"]==x["destination"]:
        return jsonify({"error":"Invalid shipment data"}),400
    sid="S"+str(int(time.time()*1000))[-6:]
    now=time.time(); c=db()
    c.execute("""INSERT INTO shipments(id,title,origin,destination,weight,priority,status,vehicle_id,eta_min,route_distance,delay_risk,delay_min,created,updated)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (sid,x["title"],x["origin"],x["destination"],weight,x["priority"],"Pending",None,None,None,"Low",0,now,now))
    c.commit(); c.close(); log("SHIPMENT",f"{sid} created: {x['title']}")
    return jsonify({"id":sid})

@app.post("/api/assign")
def assign():
    x=request.get_json(force=True); sid=x.get("shipment_id"); vid=x.get("vehicle_id")
    c=db(); s=c.execute("SELECT * FROM shipments WHERE id=?",(sid,)).fetchone(); v=c.execute("SELECT * FROM vehicles WHERE id=?",(vid,)).fetchone()
    if not s or not v: c.close(); return jsonify({"error":"Shipment or vehicle not found"}),404
    if v["status"]=="Maintenance": c.close(); return jsonify({"error":"Vehicle is in maintenance"}),400
    old=s["vehicle_id"]
    if old==vid: c.close(); return jsonify({"ok":True,"message":"Already assigned"})
    if v["capacity"]-v["load"] < s["weight"]: c.close(); return jsonify({"error":"Insufficient free capacity"}),400
    now=time.time()
    if old:
        c.execute("UPDATE vehicles SET load=MAX(0,load-?) WHERE id=?",(s["weight"],old))
        oldv=c.execute("SELECT load FROM vehicles WHERE id=?",(old,)).fetchone()
        if oldv and oldv["load"]<=0: c.execute("UPDATE vehicles SET status='Idle' WHERE id=?",(old,))
    c.execute("UPDATE vehicles SET load=load+?,status='In Transit' WHERE id=?",(s["weight"],vid))
    c.execute("UPDATE shipments SET vehicle_id=?,status='Assigned',updated=? WHERE id=?",(vid,now,sid))
    # Auto-compute a route decision immediately so ETA/risk are live from the moment
    # of assignment, instead of staying at defaults until someone runs Route AI manually.
    try:
        r=auto_decision(s,v)
        c.execute("UPDATE shipments SET eta_min=?,route_distance=?,delay_risk=?,delay_min=?,eta_set=? WHERE id=?",
                  (r["eta_min"],r["distance_km"],r["risk_level"],r["delay_min"],now,sid))
    except Exception:
        r=None
    c.commit(); c.close(); log("ASSIGN",f"{sid} assigned to {vid}")
    if r: log("OPTIMIZE",f"{sid}: auto route decision — {r['distance_km']} km / ETA {r['eta_min']} min / {r['risk_level']} risk")
    return jsonify({"ok":True})

@app.post("/api/status")
def status():
    x=request.get_json(force=True); sid=x.get("shipment_id"); new=x.get("status")
    allowed={"Pending":{"Assigned"},"Assigned":{"In-Transit","Delayed"},"In-Transit":{"Delayed","Delivered"},"Delayed":{"In-Transit","Delivered"},"Delivered":set()}
    c=db(); s=c.execute("SELECT * FROM shipments WHERE id=?",(sid,)).fetchone()
    if not s: c.close(); return jsonify({"error":"Shipment not found"}),404
    if new not in allowed.get(s["status"],set()):
        c.close(); return jsonify({"error":f"Invalid transition {s['status']} → {new}"}),400
    now=time.time(); c.execute("UPDATE shipments SET status=?,updated=? WHERE id=?",(new,now,sid))
    if new=="Delivered" and s["vehicle_id"]:
        c.execute("UPDATE vehicles SET load=MAX(0,load-?) WHERE id=?",(s["weight"],s["vehicle_id"]))
        v=c.execute("SELECT load FROM vehicles WHERE id=?",(s["vehicle_id"],)).fetchone()
        if v and v["load"]<=0: c.execute("UPDATE vehicles SET status='Idle' WHERE id=?",(s["vehicle_id"],))
    c.commit(); c.close(); log("STATUS",f"{sid}: {s['status']} → {new}")
    return jsonify({"ok":True})

@app.post("/api/optimize")
def opt():
    x=request.get_json(force=True)
    try:
        result=optimize(x["origin"],x["destination"],x.get("stops",[]),x.get("vehicle_type","Truck"),
                         x.get("weather","Clear"),x.get("traffic","Normal"),bool(x.get("peak")),
                         bool(x.get("refrigerated")),float(x.get("driver_exp",5)))
    except Exception as e:
        return jsonify({"error":str(e)}),400
    return jsonify(result)

@app.post("/api/apply-route")
def apply_route():
    x=request.get_json(force=True); sid=x.get("shipment_id"); r=x.get("result")
    c=db(); s=c.execute("SELECT * FROM shipments WHERE id=?",(sid,)).fetchone()
    if not s: c.close(); return jsonify({"error":"Shipment not found"}),404
    c.execute("""UPDATE shipments SET eta_min=?,route_distance=?,delay_risk=?,delay_min=?,eta_set=?,updated=? WHERE id=?""",
              (r["eta_min"],r["distance_km"],r["risk_level"],r["delay_min"],time.time(),time.time(),sid))
    c.commit(); c.close(); log("OPTIMIZE",f"{sid}: {r['distance_km']} km / ETA {r['eta_min']} min / {r['risk_level']} risk")
    return jsonify({"ok":True})

@app.get("/api/cities")
def cities(): return jsonify(sorted(CITIES.keys()))

@app.get("/api/analytics")
def analytics():
    c=db(); vs=[dict(x) for x in c.execute("SELECT * FROM vehicles").fetchall()]; ss=[dict(x) for x in c.execute("SELECT * FROM shipments").fetchall()]; c.close()
    total_weight=sum(s["weight"] for s in ss); delivered=sum(s["status"]=="Delivered" for s in ss)
    avg_load=(sum(v["load"]/max(v["capacity"],1) for v in vs)/len(vs)*100) if vs else 0
    on_time=max(0,100-sum(1 for s in ss if s["delay_risk"]=="High")*12)
    utilization=sum(v["load"] for v in vs)/max(sum(v["capacity"] for v in vs),1)*100
    return jsonify({"fleet_utilization":round(utilization,1),"avg_load":round(avg_load,1),"on_time_index":round(on_time,1),"delivered":delivered,"total_shipments":len(ss),"total_weight":round(total_weight),"active_vehicles":sum(v["status"]=="In Transit" for v in vs),"idle_vehicles":sum(v["status"]=="Idle" for v in vs)})

@app.get("/api/dispatch-plan")
def dispatch_plan():
    c=db(); rows=c.execute("SELECT * FROM shipments WHERE status IN ('Pending','Assigned') ORDER BY CASE priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 ELSE 3 END, created").fetchall(); c.close()
    plan=[]
    for s in rows:
        data=app.test_client().get(f"/api/eligible/{s['id']}").get_json() or {}
        elig=data.get("eligible",[])
        plan.append({"shipment":dict(s),"recommended_vehicle":elig[0] if elig else None,"alternatives":elig[1:3]})
    return jsonify(plan)

@app.get("/api/events")
def events():
    c=db(); rows=[dict(x) for x in c.execute("SELECT * FROM events ORDER BY created DESC LIMIT 30").fetchall()]; c.close()
    return jsonify(rows)

@app.post("/api/reset")
def reset():
    if DB.exists(): DB.unlink()
    init_db(); return jsonify({"ok":True})

if __name__=="__main__":
    init_db()
    app.run(host="0.0.0.0",port=5000,debug=False)

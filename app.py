from flask import Flask, jsonify, request, send_from_directory
import sqlite3, math, time, random, urllib.request, json
from pathlib import Path

BASE=Path(__file__).resolve().parent
DB=BASE/'fleet.db'
app=Flask(__name__, static_folder='static', static_url_path='')
CITIES={'Mumbai':(19.076,72.8777),'Pune':(18.5204,73.8567),'Nashik':(19.9975,73.7898),'Ahmedabad':(23.0225,72.5714),'Hyderabad':(17.385,78.4867),'Bengaluru':(12.9716,77.5946),'Chennai':(13.0827,80.2707),'Delhi':(28.6139,77.209),'Kolkata':(22.5726,88.3639),'Thane':(19.2183,72.9781)}
SPEEDS={'Truck':45,'Van':55,'Pickup':50,'Motorbike':50}
COST_KM={'Truck':24,'Van':16,'Pickup':12,'Motorbike':7}

def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def log(kind,msg):
 c=db(); c.execute('INSERT INTO events(kind,message,created) VALUES(?,?,?)',(kind,msg,time.time())); c.commit(); c.close()

def init_db():
 c=db(); c.executescript('''CREATE TABLE IF NOT EXISTS vehicles(id TEXT PRIMARY KEY,plate TEXT,driver TEXT,type TEXT,capacity REAL,load REAL DEFAULT 0,status TEXT DEFAULT 'Idle',lat REAL,lon REAL,fuel REAL DEFAULT 70,updated REAL,maintenance INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS shipments(id TEXT PRIMARY KEY,title TEXT,origin TEXT,destination TEXT,weight REAL,priority TEXT,cargo_type TEXT,status TEXT DEFAULT 'Pending',vehicle_id TEXT,eta_min INTEGER,route_distance REAL,delay_risk TEXT DEFAULT 'Low',delay_min INTEGER DEFAULT 0,created REAL,updated REAL);
 CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT,message TEXT,created REAL);''')
 if c.execute('SELECT COUNT(*) FROM vehicles').fetchone()[0]==0:
  now=time.time(); vs=[('MH01','MH-01-AB-1201','Aarav Sharma','Truck',14000,4200,'In Transit',19.15,72.88,78,0),('MH02','MH-02-CD-4521','Riya Patel','Truck',12000,8500,'In Transit',18.68,73.80,61,0),('KA01','KA-01-EF-7710','Vikram Rao','Van',3500,0,'Idle',12.98,77.60,88,0),('TN01','TN-01-GH-3020','Meera Iyer','Truck',10000,0,'Idle',13.10,80.25,72,0),('TS01','TS-01-JK-6190','Kabir Khan','Pickup',2500,600,'Idle',17.42,78.49,66,0),('DL01','DL-01-LM-8850','Neha Singh','Van',4000,0,'Maintenance',28.62,77.21,35,1)]
  c.executemany('INSERT INTO vehicles VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',[(a,b,d,e,f,g,h,i,j,k,now,l) for a,b,d,e,f,g,h,i,j,k,l in vs])
  ss=[('S001','Electronics components','Mumbai','Pune',4200,'High','General','In-Transit','MH01'),('S002','Automotive spare parts','Mumbai','Hyderabad',6500,'Critical','General','In-Transit','MH02'),('S003','Temperature-sensitive cargo','Thane','Nashik',1800,'Critical','Refrigerated','Pending',None),('S004','Consumer electronics','Pune','Bengaluru',1200,'Normal','General','Pending',None)]
  for s in ss: c.execute('INSERT INTO shipments(id,title,origin,destination,weight,priority,cargo_type,status,vehicle_id,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(*s,now,now))
  c.execute('INSERT INTO events(kind,message,created) VALUES(?,?,?)',('SYSTEM','FleetIQ initialized — simulation mode ready',now)); c.commit()
 c.close()

def hav(a,b,c,d):
 R=6371; p1=math.radians(a); p2=math.radians(c); dp=math.radians(c-a); dl=math.radians(d-b); x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2; return R*2*math.atan2(math.sqrt(x),math.sqrt(1-x))

def road_route(points):
 if len(points)<2:return points,0
 coords=';'.join(f'{lon},{lat}' for lat,lon in points); url=f'https://router.project-osrm.org/route/v1/driving/{coords}?overview=full&geometries=geojson&steps=false'
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'TeamMaple-FleetIQ/Final'}); data=json.loads(urllib.request.urlopen(req,timeout=4).read().decode())
  if data.get('code')=='Ok':
   geom=data['routes'][0]['geometry']['coordinates']; return [(lat,lon) for lon,lat in geom],data['routes'][0]['distance']/1000
 except Exception: pass
 return points,sum(hav(*points[i],*points[i+1]) for i in range(len(points)-1))

def optimize(origin,destination,stops=None,vehicle_type='Truck',weather='Clear',traffic='Normal',peak=False,refrigerated=False,driver_exp=5):
 stops=stops or []; ordered=[origin]; rem=[s for s in stops if s in CITIES and s not in (origin,destination)]; cur=origin
 while rem:
  nxt=min(rem,key=lambda x:hav(*CITIES[cur],*CITIES[x])); ordered.append(nxt); rem.remove(nxt); cur=nxt
 ordered.append(destination); pts=[CITIES[x] for x in ordered]; line,dist=road_route(pts)
 straight=sum(hav(*pts[i],*pts[i+1]) for i in range(len(pts)-1));
 tf={'Low':1,'Normal':1.12,'Heavy':1.35}.get(traffic,1.12); wf={'Clear':1,'Light Rain':1.08,'Heavy Rain':1.18,'Storm':1.35}.get(weather,1)
 base=max(1,round(dist/SPEEDS.get(vehicle_type,45)*60*tf*wf)); risk=max(0,min(100,(18 if dist>500 else 8 if dist>200 else 2)+{'Clear':0,'Light Rain':8,'Heavy Rain':20,'Storm':38}.get(weather,0)+{'Low':0,'Normal':8,'Heavy':22}.get(traffic,8)+(12 if refrigerated else 0)+(15 if peak else 0)-driver_exp*.9)); level='High' if risk>=55 else 'Moderate' if risk>=25 else 'Low'; delay=round(risk*.65); cost=round(dist*COST_KM.get(vehicle_type,20)*(1+({'Low':0,'Normal':.04,'Heavy':.12}.get(traffic,0))+({'Clear':0,'Light Rain':.03,'Heavy Rain':.07,'Storm':.15}.get(weather,0))))
 return {'sequence':ordered,'geometry':line,'distance_km':round(dist,1),'straight_km':round(straight,1),'base_eta_min':base,'delay_min':delay,'eta_min':base+delay,'risk':round(risk),'risk_level':level,'estimated_cost':cost}

def serialize(r): return dict(r)

def eligibility(s):
 c=db(); rows=c.execute('SELECT * FROM vehicles').fetchall(); c.close(); ok=[]; rej=[]
 for v in rows:
  free=v['capacity']-v['load']; d=hav(v['lat'],v['lon'],*CITIES[s['origin']]); reasons=[]
  if v['status']=='Maintenance': reasons.append('Maintenance')
  if free<s['weight']: reasons.append(f'Only {free:.0f} kg free')
  if s['cargo_type']=='Refrigerated' and v['type'] not in ('Truck','Van'): reasons.append('Vehicle not suitable for refrigerated cargo')
  if reasons: rej.append({**dict(v),'reason':' • '.join(reasons)}); continue
  score=100; score-=min(45,d*1.1); score+=min(25,max(0,(free-s['weight'])/v['capacity']*25)); score+=15 if v['status']=='Idle' else 4; score+=8 if s['priority']=='Critical' and v['status']=='Idle' else 0; score=max(0,min(100,score))
  ok.append({**dict(v),'free_capacity':round(free),'distance_to_pickup':round(d,1),'match_score':round(score)})
 return sorted(ok,key=lambda x:x['match_score'],reverse=True),rej

def update_route_for(s,v):
 traffic=random.choices(['Low','Normal','Heavy'],[30,50,20])[0]; weather=random.choices(['Clear','Light Rain','Heavy Rain','Storm'],[60,22,14,4])[0]; return optimize(s['origin'],s['destination'],[],v['type'],weather,traffic,random.random()<.25,s['cargo_type']=='Refrigerated',random.uniform(2,15))

@app.get('/')
def home(): return send_from_directory(app.static_folder,'index.html')
@app.get('/api/summary')
def summary():
 c=db(); vs=[dict(x) for x in c.execute('SELECT * FROM vehicles')]; ss=[dict(x) for x in c.execute('SELECT * FROM shipments ORDER BY created DESC')]; ev=[dict(x) for x in c.execute('SELECT * FROM events ORDER BY created DESC LIMIT 18')]; c.close(); totalcap=sum(v['capacity'] for v in vs); load=sum(v['load'] for v in vs); return jsonify({'vehicles':vs,'shipments':ss,'events':ev,'kpis':{'total':len(vs),'available':sum(v['status']=='Idle' for v in vs),'in_transit':sum(v['status']=='In Transit' for v in vs),'maintenance':sum(v['status']=='Maintenance' for v in vs),'active_shipments':sum(s['status']!='Delivered' for s in ss),'delayed':sum(s['delay_risk']=='High' or s['status']=='Delayed' for s in ss),'utilization':round(load/totalcap*100,1) if totalcap else 0}})
@app.get('/api/cities')
def cities(): return jsonify(sorted(CITIES))
@app.get('/api/eligible/<sid>')
def eligible(sid):
 c=db(); s=c.execute('SELECT * FROM shipments WHERE id=?',(sid,)).fetchone(); c.close();
 if not s:return jsonify({'error':'Shipment not found'}),404
 a,b=eligibility(s); return jsonify({'eligible':a,'rejected':b})
@app.post('/api/shipments')
def create():
 x=request.get_json(force=True); req=['title','origin','destination','weight','priority','cargo_type']
 if any(k not in x for k in req): return jsonify({'error':'All shipment fields are required'}),400
 try:w=float(x['weight'])
 except:return jsonify({'error':'Weight must be numeric'}),400
 if w<=0 or x['origin'] not in CITIES or x['destination'] not in CITIES or x['origin']==x['destination']:return jsonify({'error':'Invalid route or weight'}),400
 sid='S'+str(int(time.time()*1000))[-7:]; now=time.time(); c=db(); c.execute('INSERT INTO shipments(id,title,origin,destination,weight,priority,cargo_type,status,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)',(sid,x['title'].strip(),x['origin'],x['destination'],w,x['priority'],x['cargo_type'],'Pending',now,now)); c.commit(); c.close(); log('SHIPMENT',f'{sid} created — {x["title"]}'); return jsonify({'id':sid})
@app.post('/api/assign')
def assign():
 x=request.get_json(force=True); sid=x.get('shipment_id'); vid=x.get('vehicle_id'); c=db(); s=c.execute('SELECT * FROM shipments WHERE id=?',(sid,)).fetchone(); v=c.execute('SELECT * FROM vehicles WHERE id=?',(vid,)).fetchone();
 if not s or not v:c.close();return jsonify({'error':'Shipment or vehicle not found'}),404
 if s['status']=='Delivered':c.close();return jsonify({'error':'Delivered shipment cannot be reassigned'}),400
 if v['status']=='Maintenance' or v['capacity']-v['load']<s['weight']:c.close();return jsonify({'error':'Vehicle is not eligible'}),400
 old=s['vehicle_id']; now=time.time()
 if old and old!=vid:c.execute('UPDATE vehicles SET load=MAX(0,load-?) WHERE id=?',(s['weight'],old))
 if old!=vid:c.execute('UPDATE vehicles SET load=load+?,status="In Transit" WHERE id=?',(s['weight'],vid))
 c.execute('UPDATE shipments SET vehicle_id=?,status="Assigned",updated=? WHERE id=?',(vid,now,sid)); r=update_route_for(s,v); c.execute('UPDATE shipments SET eta_min=?,route_distance=?,delay_risk=?,delay_min=? WHERE id=?',(r['eta_min'],r['distance_km'],r['risk_level'],r['delay_min'],sid)); c.commit(); c.close(); log('DISPATCH',f'{sid} → {vid} | {r["risk_level"]} risk | ETA {r["eta_min"]} min'); return jsonify({'ok':True,'route':r})
@app.post('/api/status')
def status():
 x=request.get_json(force=True); sid=x.get('shipment_id'); new=x.get('status'); allowed={'Pending':{'Assigned'},'Assigned':{'In-Transit','Delayed'},'In-Transit':{'Delayed','Delivered'},'Delayed':{'In-Transit','Delivered'},'Delivered':set()}; c=db(); s=c.execute('SELECT * FROM shipments WHERE id=?',(sid,)).fetchone()
 if not s:c.close();return jsonify({'error':'Shipment not found'}),404
 if new not in allowed.get(s['status'],set()):c.close();return jsonify({'error':f'Invalid transition {s["status"]} → {new}'}),400
 now=time.time(); c.execute('UPDATE shipments SET status=?,updated=? WHERE id=?',(new,now,sid))
 if new=='Delivered' and s['vehicle_id']:
  c.execute('UPDATE vehicles SET load=MAX(0,load-?) WHERE id=?',(s['weight'],s['vehicle_id'])); c.execute('UPDATE vehicles SET status="Idle" WHERE id=? AND load<=0',(s['vehicle_id'],))
 c.commit(); c.close(); log('STATUS',f'{sid}: {s["status"]} → {new}'); return jsonify({'ok':True})
@app.post('/api/optimize')
def opt():
 x=request.get_json(force=True)
 try:return jsonify(optimize(x['origin'],x['destination'],x.get('stops',[]),x.get('vehicle_type','Truck'),x.get('weather','Clear'),x.get('traffic','Normal'),bool(x.get('peak')),bool(x.get('refrigerated')),float(x.get('driver_exp',5))))
 except Exception as e:return jsonify({'error':str(e)}),400
@app.post('/api/apply-route')
def apply_route():
 x=request.get_json(force=True); r=x.get('result'); sid=x.get('shipment_id'); c=db(); s=c.execute('SELECT * FROM shipments WHERE id=?',(sid,)).fetchone()
 if not s:c.close();return jsonify({'error':'Shipment not found'}),404
 c.execute('UPDATE shipments SET eta_min=?,route_distance=?,delay_risk=?,delay_min=?,updated=? WHERE id=?',(r['eta_min'],r['distance_km'],r['risk_level'],r['delay_min'],time.time(),sid)); c.commit(); c.close(); log('OPTIMIZE',f'{sid}: {r["distance_km"]} km • ETA {r["eta_min"]} min • {r["risk_level"]} risk • ₹{r["estimated_cost"]} est.'); return jsonify({'ok':True})
@app.post('/api/simulate')
def simulate():
 c=db(); rows=c.execute('SELECT * FROM vehicles WHERE status="In Transit"').fetchall(); now=time.time(); changed=[]
 for v in rows:
  s=c.execute('SELECT * FROM shipments WHERE vehicle_id=? AND status IN ("Assigned","In-Transit","Delayed") ORDER BY updated DESC LIMIT 1',(v['id'],)).fetchone(); lat,lon=v['lat'],v['lon']
  if s and s['destination'] in CITIES:
   dlat,dlon=CITIES[s['destination']]; lat+=(dlat-lat)*.06+random.uniform(-.004,.004); lon+=(dlon-lon)*.06+random.uniform(-.004,.004)
  else: lat+=random.uniform(-.01,.01); lon+=random.uniform(-.01,.01)
  c.execute('UPDATE vehicles SET lat=?,lon=?,updated=? WHERE id=?',(lat,lon,now,v['id'])); changed.append(v['id'])
 c.commit(); c.close(); return jsonify({'updated':changed,'mode':'SIMULATION'})
@app.get('/api/analytics')
def analytics():
 c=db(); vs=[dict(x) for x in c.execute('SELECT * FROM vehicles')]; ss=[dict(x) for x in c.execute('SELECT * FROM shipments')]; c.close(); cap=sum(v['capacity'] for v in vs); load=sum(v['load'] for v in vs); delivered=sum(s['status']=='Delivered' for s in ss); high=sum(s['delay_risk']=='High' for s in ss); return jsonify({'utilization':round(load/cap*100,1) if cap else 0,'delivered':delivered,'total':len(ss),'on_time':round(max(0,100-high*12),1),'active':sum(v['status']=='In Transit' for v in vs),'idle':sum(v['status']=='Idle' for v in vs),'capacity_kg':round(cap),'loaded_kg':round(load)})
@app.get('/api/dispatch-plan')
def dispatch_plan():
 c=db(); ss=c.execute('SELECT * FROM shipments WHERE status IN ("Pending","Assigned") ORDER BY CASE priority WHEN "Critical" THEN 1 WHEN "High" THEN 2 ELSE 3 END,created').fetchall(); c.close(); out=[]
 for s in ss:
  a,_=eligibility(s); out.append({'shipment':dict(s),'recommended_vehicle':a[0] if a else None,'alternatives':a[1:3]})
 return jsonify(out)
@app.post('/api/recommendation')
def recommendation():
 sid=request.json.get('shipment_id'); c=db(); s=c.execute('SELECT * FROM shipments WHERE id=?',(sid,)).fetchone(); c.close()
 if not s:return jsonify({'error':'Shipment not found'}),404
 a,_=eligibility(s)
 if not a:return jsonify({'error':'No eligible vehicle available'}),409
 v=a[0]; return jsonify({'shipment_id':sid,'vehicle_id':v['id'],'vehicle':v,'action':f'Assign {v["plate"]} to {sid}','reason':f'{v["free_capacity"]} kg free • {v["distance_to_pickup"]} km to pickup • {v["match_score"]}% match'})
@app.post('/api/reset')
def reset():
 if DB.exists():DB.unlink()
 init_db(); return jsonify({'ok':True})
if __name__=='__main__': init_db(); app.run(host='0.0.0.0',port=5000,debug=False)

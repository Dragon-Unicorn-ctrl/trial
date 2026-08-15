from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import sqlite3, json, math, random, time
from pathlib import Path
BASE=Path(__file__).parent; DB=BASE/'fleet.db'; STATIC=BASE/'static'
CITY={'Mumbai':(19.076,72.8777),'Delhi':(28.7041,77.1025),'Bengaluru':(12.9716,77.5946),'Chennai':(13.0827,80.2707),'Hyderabad':(17.385,78.4867),'Pune':(18.5204,73.8567),'Kolkata':(22.5726,88.3639),'Ahmedabad':(23.0225,72.5714)}
def conn():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init_db():
 c=conn(); q=c.cursor(); q.executescript('''CREATE TABLE IF NOT EXISTS vehicles(id INTEGER PRIMARY KEY AUTOINCREMENT,vehicle_no TEXT UNIQUE,type TEXT,capacity_kg REAL,current_load_kg REAL DEFAULT 0,status TEXT DEFAULT 'Idle',driver TEXT,lat REAL,lon REAL,last_update TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS shipments(id INTEGER PRIMARY KEY AUTOINCREMENT,shipment_no TEXT UNIQUE,origin TEXT,destination TEXT,load_kg REAL,priority TEXT,status TEXT DEFAULT 'Pending',vehicle_id INTEGER,eta TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,message TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);''')
 if q.execute('SELECT COUNT(*) n FROM vehicles').fetchone()['n']==0:
  q.executemany('INSERT INTO vehicles(vehicle_no,type,capacity_kg,current_load_kg,status,driver,lat,lon) VALUES(?,?,?,?,?,?,?,?)',[("TM-101","Truck",12000,2500,"In Transit","Ravi",17.385,78.4867),("TM-202","Pickup",3500,0,"Idle","Arjun",19.076,72.8777),("TM-303","Van",1800,600,"In Transit","Kiran",12.9716,77.5946),("TM-404","Truck",10000,0,"Idle","Meena",13.0827,80.2707),("TM-505","Motorbike",80,20,"In Transit","Sahil",18.5204,73.8567),("TM-606","Pickup",4000,0,"Maintenance","Priya",28.7041,77.1025)])
 if q.execute('SELECT COUNT(*) n FROM shipments').fetchone()['n']==0:
  q.executemany('INSERT INTO shipments(shipment_no,origin,destination,load_kg,priority,status,vehicle_id,eta) VALUES(?,?,?,?,?,?,?,?)',[("SHP-1001","Hyderabad","Bengaluru",1800,"High","In-Transit",1,"~4h"),("SHP-1002","Mumbai","Pune",1200,"Normal","Pending",None,None),("SHP-1003","Chennai","Hyderabad",900,"Normal","Assigned",3,"~7h")])
 c.commit();c.close()
def hav(a,b):
 R=6371;p1=math.radians(a[0]);p2=math.radians(b[0]);dp=math.radians(b[0]-a[0]);dl=math.radians(b[1]-a[1]);x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2;return R*2*math.atan2(math.sqrt(x),math.sqrt(1-x))
def optimize(o,d,stops=[]):
 u=[s for s in stops if s in CITY and s not in(o,d)];cur=o;route=[o];dist=0
 while u:
  n=min(u,key=lambda s:hav(CITY[cur],CITY[s]));dist+=hav(CITY[cur],CITY[n]);cur=n;route.append(cur);u.remove(n)
 dist+=hav(CITY[cur],CITY[d]);route.append(d);base=round(dist);return {'route':route,'distance_km':round(dist,1),'base_eta_min':round(dist),'coordinates':[CITY[x] for x in route]}
def risk(dist,w='Clear',t='Normal',ref=False,exp=5,peak=False):
 score=(25 if dist>500 else 10 if dist>200 else 0)+{'Clear':0,'Light Rain':10,'Heavy Rain':25,'Storm':45}.get(w,0)+{'Low':0,'Normal':10,'Heavy':25}.get(t,10)+(15 if ref else 0)+(18 if peak else 0)-exp*.8;score=max(0,score);mins=round(score*1.1);return {'delay_min':mins,'risk':'High' if mins>45 else 'Moderate' if mins>15 else 'Low'}
def log(msg):
 c=conn();c.execute('INSERT INTO events(message) VALUES(?)',(msg,));c.commit();c.close()
def rows(sql,args=()):
 c=conn();r=[dict(x) for x in c.execute(sql,args).fetchall()];c.close();return r
class H(BaseHTTPRequestHandler):
 def send(self,code,data,ctype='application/json'):
  b=data if isinstance(data,bytes) else (json.dumps(data).encode() if ctype=='application/json' else data.encode());self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(b)));self.send_header('Access-Control-Allow-Origin','*');self.end_headers();self.wfile.write(b)
 def body(self):
  n=int(self.headers.get('Content-Length','0'));return json.loads(self.rfile.read(n) or b'{}')
 def do_OPTIONS(self):self.send(204,b'', 'text/plain')
 def do_GET(self):
  p=urlparse(self.path).path
  if p=='/':return self.send(200,(STATIC/'index.html').read_bytes(),'text/html; charset=utf-8')
  if p.startswith('/static/'): 
   f=BASE/p.lstrip('/');return self.send(200,f.read_bytes(),'text/plain') if f.exists() else self.send(404,{'error':'not found'})
  if p=='/api/dashboard':
   c=conn();d={};d['total_vehicles']=c.execute('SELECT COUNT(*) n FROM vehicles').fetchone()['n'];d['active_vehicles']=c.execute("SELECT COUNT(*) n FROM vehicles WHERE status='In Transit'").fetchone()['n'];d['idle_vehicles']=c.execute("SELECT COUNT(*) n FROM vehicles WHERE status='Idle'").fetchone()['n'];d['maintenance_vehicles']=c.execute("SELECT COUNT(*) n FROM vehicles WHERE status='Maintenance'").fetchone()['n'];d['active_shipments']=c.execute("SELECT COUNT(*) n FROM shipments WHERE status!='Delivered'").fetchone()['n'];d['delayed_shipments']=c.execute("SELECT COUNT(*) n FROM shipments WHERE status='Delayed'").fetchone()['n'];c.close();return self.send(200,d)
  if p=='/api/vehicles':return self.send(200,rows('SELECT * FROM vehicles ORDER BY id'))
  if p=='/api/shipments':return self.send(200,rows('SELECT s.*,v.vehicle_no FROM shipments s LEFT JOIN vehicles v ON s.vehicle_id=v.id ORDER BY s.id DESC'))
  if p=='/api/events':return self.send(200,rows('SELECT * FROM events ORDER BY id DESC LIMIT 8'))
  if p.startswith('/api/eligible/'):
   sid=int(p.rsplit('/',1)[1]);c=conn();s=c.execute('SELECT * FROM shipments WHERE id=?',(sid,)).fetchone();r=[] if not s else [dict(x) for x in c.execute("SELECT * FROM vehicles WHERE status!='Maintenance' AND capacity_kg-current_load_kg>=? ORDER BY capacity_kg-current_load_kg",(s['load_kg'],)).fetchall()];c.close();return self.send(200,r)
  return self.send(404,{'error':'not found'})
 def do_POST(self):
  p=urlparse(self.path).path;d=self.body()
  try:
   if p=='/api/simulate':
    c=conn();vs=c.execute("SELECT * FROM vehicles WHERE status='In Transit'").fetchall()
    for v in vs:c.execute('UPDATE vehicles SET lat=?,lon=?,last_update=CURRENT_TIMESTAMP WHERE id=?',(v['lat']+random.uniform(-.015,.015),v['lon']+random.uniform(-.015,.015),v['id']))
    c.commit();c.close();return self.send(200,{'ok':True})
   if p=='/api/shipments':
    o=d.get('origin');de=d.get('destination');kg=float(d.get('load_kg',0));
    if o not in CITY or de not in CITY:return self.send(400,{'error':'Use supported demo cities: '+', '.join(CITY)})
    no='SHP-'+str(1000+int(time.time())%9000);c=conn();c.execute('INSERT INTO shipments(shipment_no,origin,destination,load_kg,priority) VALUES(?,?,?,?,?)',(no,o,de,kg,d.get('priority','Normal')));c.commit();c.close();log('Created shipment '+no);return self.send(201,{'shipment_no':no})
   if p.startswith('/api/shipments/') and p.endswith('/assign'):
    sid=int(p.split('/')[3]);vid=d.get('vehicle_id');c=conn();s=c.execute('SELECT * FROM shipments WHERE id=?',(sid,)).fetchone();v=c.execute('SELECT * FROM vehicles WHERE id=?',(vid,)).fetchone();
    if not s or not v:c.close();return self.send(404,{'error':'Shipment or vehicle not found'})
    if v['status']=='Maintenance' or v['capacity_kg']-v['current_load_kg']<s['load_kg']:c.close();return self.send(400,{'error':'Vehicle does not have enough capacity'})
    c.execute('UPDATE shipments SET vehicle_id=?,status="Assigned" WHERE id=?',(vid,sid));c.execute('UPDATE vehicles SET current_load_kg=current_load_kg+?,status="In Transit" WHERE id=?',(s['load_kg'],vid));c.commit();c.close();log(f'Assigned {s["shipment_no"]} to {v["vehicle_no"]}');return self.send(200,{'ok':True})
   if p.startswith('/api/shipments/') and p.endswith('/status'):
    sid=int(p.split('/')[3]);st=d.get('status');
    if st not in ['Pending','Assigned','In-Transit','Delayed','Delivered']:return self.send(400,{'error':'Invalid status'})
    c=conn();s=c.execute('SELECT * FROM shipments WHERE id=?',(sid,)).fetchone();
    if not s:c.close();return self.send(404,{'error':'not found'})
    c.execute('UPDATE shipments SET status=? WHERE id=?',(st,sid));
    if st=='Delivered' and s['vehicle_id']:c.execute('UPDATE vehicles SET current_load_kg=MAX(0,current_load_kg-?) WHERE id=?',(s['load_kg'],s['vehicle_id']))
    c.commit();c.close();log(f'{s["shipment_no"]} status → {st}');return self.send(200,{'ok':True})
   if p=='/api/optimize':
    o=d.get('origin');de=d.get('destination');
    if o not in CITY or de not in CITY:return self.send(400,{'error':'Unsupported origin/destination'})
    r=optimize(o,de,d.get('stops',[]));r.update(risk(r['distance_km'],d.get('weather','Clear'),d.get('traffic','Normal'),bool(d.get('refrigerated')),float(d.get('driver_exp',5)),bool(d.get('peak'))));r['final_eta_min']=r['base_eta_min']+r['delay_min'];return self.send(200,r)
   return self.send(404,{'error':'not found'})
  except Exception as e:return self.send(500,{'error':str(e)})
init_db();ThreadingHTTPServer(('0.0.0.0',5000),H).serve_forever()

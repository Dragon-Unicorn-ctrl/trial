import "dotenv/config";
import express from "express";
import cors from "cors";
import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import fs from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";
import { randomUUID } from "crypto";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = process.env.PORT || 3000;
const JWT_SECRET = process.env.JWT_SECRET || "dev-secret-change-in-production";
const DATA_DIR = path.join(__dirname, "data");
const DB_PATH = path.join(DATA_DIR, "db.json");

app.use(cors());
app.use(express.json({ limit: "1mb" }));
app.use(express.static(path.join(__dirname, "public")));

const asyncHandler = (fn) => (req, res, next) =>
  Promise.resolve(fn(req, res, next)).catch(next);

const nowISO = () => new Date().toISOString();
const addMinutesISO = (minutes = 0) =>
  new Date(Date.now() + Number(minutes || 0) * 60000).toISOString();
const round1 = (value) => Math.round(Number(value || 0) * 10) / 10;
const toNumber = (value, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const VEHICLE_STATUSES = ["ready_to_load", "loaded", "empty", "delayed", "maintenance"];
const SHIPMENT_STATUSES = ["pending", "assigned", "in_transit", "arrived", "delayed", "delivered", "cancelled"];

const safeUser = (user) => ({
  id: user.id,
  role: user.role,
  username: user.username,
  name: user.name,
  phone: user.phone || ""
});

const isShipmentActive = (shipment) =>
  !["delivered", "cancelled"].includes(shipment.status);

async function ensureDb() {
  await fs.mkdir(DATA_DIR, { recursive: true });
  try {
    await fs.access(DB_PATH);
  } catch {
    await seedDb();
  }
}

async function seedDb() {
  const managerHash = bcrypt.hashSync("Manager@123", 10);
  const driverHash = bcrypt.hashSync("Driver@123", 10);
  const now = new Date();

  const minutesAgo = (minutes) => new Date(now.getTime() - minutes * 60000).toISOString();
  const minutesAhead = (minutes) => new Date(now.getTime() + minutes * 60000).toISOString();

  const db = {
    users: [
      {
        id: "u-manager",
        role: "manager",
        username: "manager@fleet.com",
        passwordHash: managerHash,
        name: "Fleet Operations Manager",
        phone: "+1-555-0100"
      },
      {
        id: "u-driver-1",
        role: "driver",
        username: "driver1@fleet.com",
        passwordHash: driverHash,
        name: "Ravi Kumar",
        phone: "+91 98100 00001"
      },
      {
        id: "u-driver-2",
        role: "driver",
        username: "driver2@fleet.com",
        passwordHash: driverHash,
        name: "Aisha Khan",
        phone: "+91 98100 00002"
      },
      {
        id: "u-driver-3",
        role: "driver",
        username: "driver3@fleet.com",
        passwordHash: driverHash,
        name: "Vikram Singh",
        phone: "+91 98100 00003"
      },
      {
        id: "u-driver-4",
        role: "driver",
        username: "driver4@fleet.com",
        passwordHash: driverHash,
        name: "Meena Joshi",
        phone: "+91 98100 00004"
      }
    ],
    vehicles: [
      {
        id: "v-1001",
        plate: "MH-12-AV-3456",
        type: "truck",
        capacityKg: 8000,
        status: "loaded",
        driverId: "u-driver-1",
        location: { lat: 19.076, lng: 72.8777 },
        createdAt: minutesAgo(2000),
        updatedAt: minutesAgo(15)
      },
      {
        id: "v-1002",
        plate: "DL-01-BC-9876",
        type: "truck",
        capacityKg: 6000,
        status: "ready_to_load",
        driverId: "u-driver-2",
        location: { lat: 18.5204, lng: 73.8567 },
        createdAt: minutesAgo(1800),
        updatedAt: minutesAgo(20)
      },
      {
        id: "v-1003",
        plate: "KA-05-MN-2211",
        type: "van",
        capacityKg: 2500,
        status: "delayed",
        driverId: "u-driver-3",
        location: { lat: 12.9716, lng: 77.5946 },
        createdAt: minutesAgo(1500),
        updatedAt: minutesAgo(25)
      },
      {
        id: "v-1004",
        plate: "TS-09-PQ-7788",
        type: "pickup",
        capacityKg: 1500,
        status: "empty",
        driverId: "u-driver-4",
        location: { lat: 17.385, lng: 78.4867 },
        createdAt: minutesAgo(1200),
        updatedAt: minutesAgo(10)
      },
      {
        id: "v-1005",
        plate: "TN-10-XZ-4455",
        type: "truck",
        capacityKg: 10000,
        status: "maintenance",
        driverId: null,
        location: { lat: 13.0827, lng: 80.2707 },
        createdAt: minutesAgo(3000),
        updatedAt: minutesAgo(300)
      }
    ],
    shipments: [
      {
        id: "s-2001",
        code: "SHP-1001",
        origin: { label: "Mumbai Warehouse", lat: 19.076, lng: 72.8777 },
        destination: { label: "Pune Distribution Center", lat: 18.5204, lng: 73.8567 },
        weightKg: 5400,
        status: "in_transit",
        vehicleId: "v-1001",
        createdAt: minutesAgo(180),
        eta: minutesAhead(45),
        deliveredAt: null,
        delayReason: "",
        history: [{ at: minutesAgo(180), event: "created" }]
      },
      {
        id: "s-2002",
        code: "SHP-1002",
        origin: { label: "Chennai Port", lat: 13.0827, lng: 80.2707 },
        destination: { label: "Bengaluru Tech Park", lat: 12.9716, lng: 77.5946 },
        weightKg: 900,
        status: "pending",
        vehicleId: null,
        createdAt: minutesAgo(60),
        eta: minutesAhead(120),
        deliveredAt: null,
        delayReason: "",
        history: [{ at: minutesAgo(60), event: "created" }]
      },
      {
        id: "s-2003",
        code: "SHP-1003",
        origin: { label: "Hyderabad Hub", lat: 17.385, lng: 78.4867 },
        destination: { label: "Chennai Retail Center", lat: 13.0827, lng: 80.2707 },
        weightKg: 1400,
        status: "delayed",
        vehicleId: "v-1003",
        createdAt: minutesAgo(240),
        eta: minutesAgo(35),
        deliveredAt: null,
        delayReason: "Traffic congestion near toll plaza",
        history: [{ at: minutesAgo(240), event: "created" }]
      },
      {
        id: "s-2004",
        code: "SHP-1004",
        origin: { label: "Mumbai Warehouse", lat: 19.076, lng: 72.8777 },
        destination: { label: "Nashik Depot", lat: 19.9975, lng: 73.7898 },
        weightKg: 1200,
        status: "delivered",
        vehicleId: "v-1004",
        createdAt: minutesAgo(2000),
        eta: minutesAgo(1800),
        deliveredAt: minutesAgo(1800),
        delayReason: "",
        history: [{ at: minutesAgo(2000), event: "created" }]
      }
    ],
    audit: []
  };

  await fs.writeFile(DB_PATH, JSON.stringify(db, null, 2), "utf8");
}

async function readDb() {
  try {
    const raw = await fs.readFile(DB_PATH, "utf8");
    return JSON.parse(raw);
  } catch {
    await seedDb();
    const raw = await fs.readFile(DB_PATH, "utf8");
    return JSON.parse(raw);
  }
}

async function writeDb(db) {
  await fs.writeFile(DB_PATH, JSON.stringify(db, null, 2), "utf8");
}

function haversineKm(a, b) {
  const toRad = (x) => (x * Math.PI) / 180;
  const earthRadiusKm = 6371;
  const dLat = toRad((b.lng === undefined ? 0 : b.lat || 0) - (a.lat || 0));
  const dLng = toRad((b.lng || 0) - (a.lng || 0));
  const lat1 = toRad(a.lat || 0);
  const lat2 = toRad(b.lat || 0);

  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;

  return 2 * earthRadiusKm * Math.asin(Math.sqrt(h));
}

function vehicleHasOtherActive(db, vehicleId, excludeShipmentId = null) {
  return db.shipments.some(
    (s) => s.vehicleId === vehicleId && s.id !== excludeShipmentId && isShipmentActive(s)
  );
}

function setVehicleStatus(db, vehicleId, status) {
  const vehicle = db.vehicles.find((v) => v.id === vehicleId);
  if (!vehicle) return;
  vehicle.status = status;
  vehicle.updatedAt = nowISO();
}

function validateCapacity(db, weightKg, vehicleId) {
  if (!vehicleId) return { ok: true };
  const vehicle = db.vehicles.find((v) => v.id === vehicleId);
  if (!vehicle) return { ok: true };

  const capacity = Number(vehicle.capacityKg || 0);
  const weight = Number(weightKg || 0);

  if (capacity > 0 && weight > capacity) {
    return {
      ok: false,
      error: `${vehicle.plate} capacity is ${capacity} kg, but shipment weight is ${weight} kg.`
    };
  }

  return { ok: true };
}

function vehicleView(db, vehicle) {
  const driver = vehicle.driverId
    ? db.users.find((u) => u.id === vehicle.driverId)
    : null;

  return {
    ...vehicle,
    driver: driver
      ? { id: driver.id, name: driver.name, phone: driver.phone }
      : null
  };
}

function shipmentView(db, shipment) {
  const vehicle = shipment.vehicleId
    ? db.vehicles.find((v) => v.id === shipment.vehicleId)
    : null;

  const driver = vehicle?.driverId
    ? db.users.find((u) => u.id === vehicle.driverId)
    : null;

  const delayed =
    shipment.status === "delayed" ||
    (isShipmentActive(shipment) &&
      shipment.eta &&
      new Date(shipment.eta).getTime() < Date.now());

  return {
    ...shipment,
    delayed,
    vehicle: vehicle
      ? { id: vehicle.id, plate: vehicle.plate, status: vehicle.status }
      : null,
    driver: driver
      ? { id: driver.id, name: driver.name, phone: driver.phone }
      : null
  };
}

function estimateMinutes(vehicle, shipment) {
  const from =
    vehicle?.location && Number.isFinite(vehicle.location.lat)
      ? vehicle.location
      : shipment.origin;

  const distanceKm = haversineKm(from, shipment.destination) * 1.25;
  return Math.max(20, Math.round((distanceKm / 55) * 60) + 10);
}

function authenticate(req, res, next) {
  const auth = req.headers.authorization;
  if (!auth || !auth.startsWith("Bearer ")) {
    return res.status(401).json({ error: "Authentication required" });
  }

  try {
    const payload = jwt.verify(auth.slice(7), JWT_SECRET);
    req.user = {
      id: payload.sub,
      role: payload.role,
      name: payload.name,
      username: payload.username
    };
    return next();
  } catch {
    return res.status(401).json({ error: "Invalid or expired token" });
  }
}

const authorize = (roles) => (req, res, next) => {
  if (roles.includes(req.user.role)) return next();
  return res.status(403).json({ error: "Forbidden" });
};

app.get("/api/config", (req, res) => {
  const googleMapsJsKey =
    process.env.GOOGLE_MAPS_JS_API_KEY || process.env.GOOGLE_MAPS_API_KEY || "";
  const enableGoogle =
    String(process.env.FORCE_GOOGLE_MAPS || "").toLowerCase() === "true" &&
    Boolean(googleMapsJsKey);

  res.json({
    mapProvider: enableGoogle ? "google" : "leaflet",
    googleMapsApiKey: enableGoogle ? googleMapsJsKey : ""
  });
});

app.post(
  "/api/auth/login",
  asyncHandler(async (req, res) => {
    const { username, password } = req.body || {};
    if (!username || !password) {
      return res.status(400).json({ error: "Username and password are required" });
    }

    const db = await readDb();
    const user = db.users.find(
      (u) => u.username.toLowerCase() === String(username).toLowerCase()
    );

    if (!user || !bcrypt.compareSync(password, user.passwordHash)) {
      return res.status(401).json({ error: "Invalid credentials" });
    }

    const token = jwt.sign(
      {
        sub: user.id,
        role: user.role,
        name: user.name,
        username: user.username
      },
      JWT_SECRET,
      { expiresIn: "12h" }
    );

    return res.json({ token, user: safeUser(user) });
  })
);

app.get(
  "/api/auth/me",
  authenticate,
  asyncHandler(async (req, res) => {
    const db = await readDb();
    const user = db.users.find((u) => u.id === req.user.id);
    if (!user) return res.status(404).json({ error: "User not found" });

    const manager = db.users.find((u) => u.role === "manager");
    const managerContact = manager
      ? { name: manager.name, phone: manager.phone, username: manager.username }
      : null;

    return res.json({ user: safeUser(user), managerContact });
  })
);

app.get(
  "/api/manager/dashboard",
  authenticate,
  authorize(["manager"]),
  asyncHandler(async (req, res) => {
    const db = await readDb();

    const shipmentsRaw = db.shipments.map((s) => shipmentView(db, s));
    const delayedShipments = shipmentsRaw.filter((s) => s.delayed);
    const delayedVehicleIds = new Set(
      delayedShipments.map((s) => s.vehicleId).filter(Boolean)
    );

    const vehicles = db.vehicles.map((v) => {
      const view = vehicleView(db, v);
      if (delayedVehicleIds.has(view.id) && view.status !== "delayed") {
        return { ...view, status: "delayed" };
      }
      return view;
    });

    const drivers = db.users
      .filter((u) => u.role === "driver")
      .map((d) => {
        const vehicle = db.vehicles.find((v) => v.driverId === d.id);
        return {
          ...safeUser(d),
          assignedVehicle: vehicle?.plate || null,
          vehicleId: vehicle?.id || null
        };
      });

    const shipments = shipmentsRaw.sort(
      (a, b) => new Date(b.createdAt || 0) - new Date(a.createdAt || 0)
    );

    const activeShipments = shipments.filter((s) => isShipmentActive(s));

    const counts = {
      totalVehicles: vehicles.length,
      ready_to_load: 0,
      loaded: 0,
      empty: 0,
      delayed: 0,
      maintenance: 0
    };

    vehicles.forEach((v) => {
      if (Object.prototype.hasOwnProperty.call(counts, v.status)) {
        counts[v.status] += 1;
      }
    });

    const utilized = vehicles.filter((v) =>
      ["loaded", "delayed"].includes(v.status)
    ).length;

    const utilization = counts.totalVehicles
      ? Math.round((utilized / counts.totalVehicles) * 100)
      : 0;

    const kpi = {
      totalVehicles: counts.totalVehicles,
      ready_to_load: counts.ready_to_load,
      loaded: counts.loaded,
      empty: counts.empty,
      delayedVehicles: counts.delayed,
      maintenance: counts.maintenance,
      activeShipments: activeShipments.length,
      delayedShipments: delayedShipments.length,
      onTimeShipments: activeShipments.filter((s) => !s.delayed).length,
      utilization
    };

    return res.json({ kpi, vehicles, drivers, shipments, delayedShipments });
  })
);

app.get(
  "/api/vehicles",
  authenticate,
  authorize(["manager"]),
  asyncHandler(async (req, res) => {
    const db = await readDb();
    const vehicles = db.vehicles.map((v) => vehicleView(db, v));
    return res.json({ vehicles });
  })
);

app.post(
  "/api/vehicles",
  authenticate,
  authorize(["manager"]),
  asyncHandler(async (req, res) => {
    const {
      plate,
      type = "truck",
      capacityKg = 1000,
      status = "ready_to_load",
      driverId = null,
      location = null
    } = req.body || {};

    if (!plate) return res.status(400).json({ error: "Plate is required" });

    const db = await readDb();

    if (db.vehicles.some((v) => v.plate.toLowerCase() === String(plate).toLowerCase())) {
      return res.status(409).json({ error: "Vehicle plate already exists" });
    }

    if (driverId) {
      const driver = db.users.find((u) => u.id === driverId && u.role === "driver");
      if (!driver) return res.status(400).json({ error: "Invalid driver assignment" });
    }

    const vehicleStatus = VEHICLE_STATUSES.includes(status) ? status : "ready_to_load";

    const vehicle = {
      id: randomUUID(),
      plate: String(plate).trim(),
      type: String(type || "truck").trim(),
      capacityKg: toNumber(capacityKg, 0),
      status: vehicleStatus,
      driverId: driverId || null,
      location:
        location && Number.isFinite(Number(location.lat)) && Number.isFinite(Number(location.lng))
          ? { lat: Number(location.lat), lng: Number(location.lng) }
          : { lat: 20.5937, lng: 78.9629 },
      createdAt: nowISO(),
      updatedAt: nowISO()
    };

    db.vehicles.push(vehicle);
    await writeDb(db);
    return res.status(201).json({ vehicle: vehicleView(db, vehicle) });
  })
);

app.patch(
  "/api/vehicles/:id",
  authenticate,
  authorize(["manager"]),
  asyncHandler(async (req, res) => {
    const db = await readDb();
    const vehicle = db.vehicles.find((v) => v.id === req.params.id);
    if (!vehicle) return res.status(404).json({ error: "Vehicle not found" });

    const { plate, type, capacityKg, status, driverId, location } = req.body || {};

    if (plate !== undefined) vehicle.plate = String(plate).trim();
    if (type !== undefined) vehicle.type = String(type).trim();
    if (capacityKg !== undefined) vehicle.capacityKg = toNumber(capacityKg, vehicle.capacityKg);

    if (status !== undefined) {
      if (!VEHICLE_STATUSES.includes(status)) {
        return res.status(400).json({ error: "Invalid vehicle status" });
      }
      vehicle.status = status;
    }

    if (driverId !== undefined) {
      if (driverId) {
        const driver = db.users.find((u) => u.id === driverId && u.role === "driver");
        if (!driver) return res.status(400).json({ error: "Invalid driver assignment" });
        vehicle.driverId = driverId;
      } else {
        vehicle.driverId = null;
      }
    }

    if (location !== undefined) {
      const lat = Number(location?.lat);
      const lng = Number(location?.lng);
      if (Number.isFinite(lat) && Number.isFinite(lng)) {
        vehicle.location = { lat, lng };
      }
    }

    vehicle.updatedAt = nowISO();
    await writeDb(db);
    return res.json({ vehicle: vehicleView(db, vehicle) });
  })
);

app.get(
  "/api/drivers",
  authenticate,
  authorize(["manager"]),
  asyncHandler(async (req, res) => {
    const db = await readDb();
    const drivers = db.users
      .filter((u) => u.role === "driver")
      .map((d) => {
        const vehicle = db.vehicles.find((v) => v.driverId === d.id);
        return {
          ...safeUser(d),
          assignedVehicle: vehicle?.plate || null,
          vehicleId: vehicle?.id || null
        };
      });

    return res.json({ drivers });
  })
);

app.post(
  "/api/drivers",
  authenticate,
  authorize(["manager"]),
  asyncHandler(async (req, res) => {
    const { name, username, password, phone = "" } = req.body || {};

    if (!name || !username || !password) {
      return res.status(400).json({ error: "Name, username, and password are required" });
    }

    if (String(password).length < 6) {
      return res.status(400).json({ error: "Password must be at least 6 characters" });
    }

    const db = await readDb();

    if (db.users.some((u) => u.username.toLowerCase() === String(username).toLowerCase())) {
      return res.status(409).json({ error: "Username already exists" });
    }

    const user = {
      id: randomUUID(),
      role: "driver",
      username: String(username).trim(),
      passwordHash: bcrypt.hashSync(password, 10),
      name: String(name).trim(),
      phone: String(phone || "").trim()
    };

    db.users.push(user);
    await writeDb(db);
    return res.status(201).json({ driver: safeUser(user) });
  })
);

app.get(
  "/api/shipments",
  authenticate,
  authorize(["manager"]),
  asyncHandler(async (req, res) => {
    const db = await readDb();
    const shipments = db.shipments.map((s) => shipmentView(db, s));
    return res.json({ shipments });
  })
);

app.post(
  "/api/shipments",
  authenticate,
  authorize(["manager"]),
  asyncHandler(async (req, res) => {
    const {
      originLabel = "Origin",
      originLat = 28.6139,
      originLng = 77.209,
      destinationLabel = "Destination",
      destinationLat = 19.076,
      destinationLng = 72.8777,
      weightKg = 500,
      vehicleId = null,
      etaMinutes = 60
    } = req.body || {};

    const db = await readDb();

    let status = "pending";
    if (vehicleId) {
      const vehicle = db.vehicles.find((v) => v.id === vehicleId);
      if (!vehicle) return res.status(400).json({ error: "Assigned vehicle not found" });
      if (vehicle.status === "maintenance") {
        return res.status(400).json({ error: "Cannot assign shipment to a maintenance vehicle" });
      }

      const capacityCheck = validateCapacity(db, weightKg, vehicleId);
      if (!capacityCheck.ok) {
        return res.status(400).json({ error: capacityCheck.error });
      }

      status = "assigned";
    }

    const shipment = {
      id: randomUUID(),
      code: `SHP-${Math.floor(1000 + Math.random() * 9000)}`,
      origin: {
        label: String(originLabel).trim(),
        lat: toNumber(originLat, 28.6139),
        lng: toNumber(originLng, 77.209)
      },
      destination: {
        label: String(destinationLabel).trim(),
        lat: toNumber(destinationLat, 19.076),
        lng: toNumber(destinationLng, 72.8777)
      },
      weightKg: toNumber(weightKg, 0),
      status,
      vehicleId: vehicleId || null,
      createdAt: nowISO(),
      eta: addMinutesISO(toNumber(etaMinutes, 60)),
      deliveredAt: null,
      delayReason: "",
      history: [{ at: nowISO(), event: "created" }]
    };

    db.shipments.push(shipment);

    if (vehicleId) {
      setVehicleStatus(db, vehicleId, "loaded");
    }

    await writeDb(db);
    return res.status(201).json({ shipment: shipmentView(db, shipment) });
  })
);

app.patch(
  "/api/shipments/:id",
  authenticate,
  authorize(["manager"]),
  asyncHandler(async (req, res) => {
    const db = await readDb();
    const shipment = db.shipments.find((s) => s.id === req.params.id);
    if (!shipment) return res.status(404).json({ error: "Shipment not found" });

    const { status, vehicleId, etaMinutes, delayReason } = req.body || {};

    if (status !== undefined) {
      if (!SHIPMENT_STATUSES.includes(status)) {
        return res.status(400).json({ error: "Invalid shipment status" });
      }

      shipment.status = status;
      shipment.history.push({ at: nowISO(), event: `manager_status_${status}` });

      if (status === "delivered") {
        shipment.deliveredAt = nowISO();
        if (shipment.vehicleId && !vehicleHasOtherActive(db, shipment.vehicleId, shipment.id)) {
          setVehicleStatus(db, shipment.vehicleId, "empty");
        }
      } else if (status === "cancelled") {
        if (shipment.vehicleId && !vehicleHasOtherActive(db, shipment.vehicleId, shipment.id)) {
          setVehicleStatus(db, shipment.vehicleId, "ready_to_load");
        }
      } else if (status === "delayed") {
        shipment.delayReason = delayReason || shipment.delayReason || "Manager reported delay";
        if (shipment.vehicleId) {
          setVehicleStatus(db, shipment.vehicleId, "delayed");
        }
      } else if (["in_transit", "arrived"].includes(status)) {
        shipment.deliveredAt = null;
        shipment.delayReason = "";
        if (shipment.vehicleId) {
          setVehicleStatus(db, shipment.vehicleId, "loaded");
        }
      } else {
        shipment.deliveredAt = null;
      }
    }

    if (vehicleId !== undefined) {
      const oldVehicleId = shipment.vehicleId;
      shipment.vehicleId = vehicleId || null;

      if (shipment.vehicleId) {
        const vehicle = db.vehicles.find((v) => v.id === shipment.vehicleId);
        if (!vehicle) return res.status(400).json({ error: "Assigned vehicle not found" });

        const capacityCheck = validateCapacity(db, shipment.weightKg, shipment.vehicleId);
        if (!capacityCheck.ok) {
          return res.status(400).json({ error: capacityCheck.error });
        }

        if (isShipmentActive(shipment)) {
          setVehicleStatus(db, shipment.vehicleId, "loaded");
        }
      }

      if (oldVehicleId && oldVehicleId !== shipment.vehicleId) {
        if (!vehicleHasOtherActive(db, oldVehicleId, shipment.id)) {
          setVehicleStatus(db, oldVehicleId, "ready_to_load");
        }
      }
    }

    if (etaMinutes !== undefined) {
      shipment.eta = addMinutesISO(toNumber(etaMinutes, 60));
    }

    if (delayReason !== undefined) {
      shipment.delayReason = delayReason;
    }

    shipment.updatedAt = nowISO();
    await writeDb(db);
    return res.json({ shipment: shipmentView(db, shipment) });
  })
);

app.post(
  "/api/shipments/:id/reassign",
  authenticate,
  authorize(["manager"]),
  asyncHandler(async (req, res) => {
    const { newVehicleId, reason = "Manager reassignment" } = req.body || {};
    if (!newVehicleId) {
      return res.status(400).json({ error: "newVehicleId is required" });
    }

    const db = await readDb();
    const shipment = db.shipments.find((s) => s.id === req.params.id);
    if (!shipment) return res.status(404).json({ error: "Shipment not found" });

    const newVehicle = db.vehicles.find((v) => v.id === newVehicleId);
    if (!newVehicle) return res.status(404).json({ error: "Replacement vehicle not found" });

    if (!["ready_to_load", "empty"].includes(newVehicle.status)) {
      return res.status(400).json({ error: "Selected replacement vehicle is not available" });
    }

    const capacityCheck = validateCapacity(db, shipment.weightKg, newVehicleId);
    if (!capacityCheck.ok) {
      return res.status(400).json({ error: capacityCheck.error });
    }

    const oldVehicleId = shipment.vehicleId;

    if (oldVehicleId) {
      const oldVehicle = db.vehicles.find((v) => v.id === oldVehicleId);
      if (oldVehicle && !vehicleHasOtherActive(db, oldVehicleId, shipment.id)) {
        oldVehicle.status = "ready_to_load";
        oldVehicle.updatedAt = nowISO();
      }
    }

    shipment.vehicleId = newVehicleId;
    shipment.status = "in_transit";
    shipment.delayReason = "";
    shipment.eta = addMinutesISO(estimateMinutes(newVehicle, shipment));
    shipment.history.push({
      at: nowISO(),
      event: "reassigned",
      reason,
      vehicle: newVehicle.plate
    });

    newVehicle.status = "loaded";
    newVehicle.updatedAt = nowISO();

    db.audit.push({
      at: nowISO(),
      action: "reassign",
      shipmentId: shipment.id,
      oldVehicleId,
      newVehicleId,
      by: req.user.id
    });

    await writeDb(db);
    return res.json({ shipment: shipmentView(db, shipment) });
  })
);

app.get(
  "/api/driver/me",
  authenticate,
  authorize(["driver"]),
  asyncHandler(async (req, res) => {
    const db = await readDb();
    const user = db.users.find((u) => u.id === req.user.id);
    if (!user) return res.status(404).json({ error: "User not found" });

    const manager = db.users.find((u) => u.role === "manager");
    const managerContact = manager
      ? { name: manager.name, phone: manager.phone, username: manager.username }
      : null;

    const vehicle = db.vehicles.find((v) => v.driverId === user.id) || null;
    let vehicleData = vehicle ? vehicleView(db, vehicle) : null;

    const shipments = vehicle
      ? db.shipments
          .filter((s) => s.vehicleId === vehicle.id)
          .map((s) => shipmentView(db, s))
      : [];

    const activeShipments = shipments
      .filter((s) => isShipmentActive(s))
      .sort((a, b) => new Date(a.eta || 0) - new Date(b.eta || 0));

    if (vehicleData && activeShipments.some((s) => s.delayed)) {
      vehicleData = { ...vehicleData, status: "delayed" };
    }

    return res.json({
      user: safeUser(user),
      managerContact,
      vehicle: vehicleData,
      shipments,
      activeShipments
    });
  })
);

app.post(
  "/api/driver/gps",
  authenticate,
  authorize(["driver"]),
  asyncHandler(async (req, res) => {
    const lat = Number(req.body?.lat);
    const lng = Number(req.body?.lng);

    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      return res.status(400).json({ error: "Valid lat and lng are required" });
    }

    const db = await readDb();
    const vehicle = db.vehicles.find((v) => v.driverId === req.user.id);
    if (!vehicle) return res.status(404).json({ error: "No vehicle assigned to this driver" });

    vehicle.location = { lat, lng };
    vehicle.updatedAt = nowISO();

    await writeDb(db);
    return res.json({ ok: true, location: vehicle.location });
  })
);

app.post(
  "/api/driver/shipments/:id/status",
  authenticate,
  authorize(["driver"]),
  asyncHandler(async (req, res) => {
    const { status, note = "" } = req.body || {};
    const allowed = ["in_transit", "arrived", "delivered", "delayed"];

    if (!allowed.includes(status)) {
      return res.status(400).json({ error: "Invalid driver status update" });
    }

    const db = await readDb();
    const shipment = db.shipments.find((s) => s.id === req.params.id);
    if (!shipment) return res.status(404).json({ error: "Shipment not found" });

    const vehicle = shipment.vehicleId
      ? db.vehicles.find((v) => v.id === shipment.vehicleId)
      : null;

    if (!vehicle || vehicle.driverId !== req.user.id) {
      return res.status(403).json({ error: "You are not assigned to this shipment vehicle" });
    }

    shipment.status = status;
    shipment.history.push({ at: nowISO(), event: status, note });

    if (status === "delivered") {
      shipment.deliveredAt = nowISO();
      if (!vehicleHasOtherActive(db, vehicle.id, shipment.id)) {
        vehicle.status = "empty";
        vehicle.updatedAt = nowISO();
      }
    } else if (status === "delayed") {
      shipment.delayReason = note || "Driver reported delay";
      vehicle.status = "delayed";
      vehicle.updatedAt = nowISO();
    } else if (status === "in_transit") {
      shipment.delayReason = "";
      vehicle.status = "loaded";
      vehicle.updatedAt = nowISO();
    } else if (status === "arrived") {
      vehicle.status = "loaded";
      vehicle.updatedAt = nowISO();
    }

    shipment.updatedAt = nowISO();
    await writeDb(db);
    return res.json({ shipment: shipmentView(db, shipment) });
  })
);

async function getWeather(coords) {
  try {
    const url = `https://api.open-meteo.com/v1/forecast?latitude=${coords.lat}&longitude=${coords.lng}&current_weather=true`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);

    const response = await fetch(url, { signal: controller.signal });
    clearTimeout(timeout);

    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

function describeWeatherCode(code) {
  const map = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail"
  };

  return map[code] || "Mixed weather conditions";
}

function assessWeather(currentWeather) {
  if (!currentWeather) {
    return {
      level: "unknown",
      risk: 25,
      summary: "Weather data unavailable; using conservative safety margin",
      temperature: null,
      windSpeed: null
    };
  }

  const code = Number(currentWeather.weathercode ?? 0);
  const wind = Number(currentWeather.windspeed ?? 0);
  const temperature = Number(currentWeather.temperature ?? 0);

  let risk = 12;
  let level = "good";

  const severeCodes = [45, 48, 56, 57, 65, 66, 67, 75, 77, 82, 85, 86, 95, 96, 99];
  const moderateCodes = [51, 53, 61, 63, 71, 80, 81];

  if (severeCodes.includes(code) || wind > 45) {
    risk = 82;
    level = "severe";
  } else if (moderateCodes.includes(code) || wind > 28) {
    risk = 48;
    level = "caution";
  }

  if (temperature <= 0) risk += 8;
  if (temperature >= 43) risk += 6;

  risk = Math.min(100, risk);

  if (risk >= 65) level = "severe";
  else if (risk >= 35) level = "caution";
  else level = "good";

  return {
    level,
    risk,
    summary: describeWeatherCode(code),
    temperature,
    windSpeed: wind
  };
}

async function getGoogleRoute(origin, destination) {
  const key = process.env.GOOGLE_MAPS_API_KEY;
  if (!key) return null;

  try {
    const params = new URLSearchParams({
      origins: `${origin.lat},${origin.lng}`,
      destinations: `${destination.lat},${destination.lng}`,
      key,
      mode: "driving",
      departure_time: "now",
      traffic_model: "best_guess"
    });

    const url = `https://maps.googleapis.com/maps/api/distancematrix/json?${params.toString()}`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);

    const response = await fetch(url, { signal: controller.signal });
    clearTimeout(timeout);

    const data = await response.json();
    if (data.status !== "OK") return null;

    const element = data.rows?.[0]?.elements?.[0];
    if (element?.status !== "OK") return null;

    return {
      distanceKm: element.distance.value / 1000,
      durationMin: Math.round(
        (element.duration_in_traffic?.value || element.duration.value) / 60
      ),
      source: "google_distance_matrix"
    };
  } catch {
    return null;
  }
}

function buildRoutePath(origin, destination, offset = 0) {
  const steps = 24;
  const points = [];

  if (origin.lat === destination.lat && origin.lng === destination.lng) {
    return [origin, destination];
  }

  const midLat = (origin.lat + destination.lat) / 2;
  const midLng = (origin.lng + destination.lng) / 2;
  const dx = destination.lat - origin.lat;
  const dy = destination.lng - origin.lng;
  const norm = Math.sqrt(dx * dx + dy * dy) || 1;

  const controlLat = midLat + (-dy / norm) * offset;
  const controlLng = midLng + (dx / norm) * offset;

  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps;
    const lat =
      (1 - t) * (1 - t) * origin.lat +
      2 * (1 - t) * t * controlLat +
      t * t * destination.lat;
    const lng =
      (1 - t) * (1 - t) * origin.lng +
      2 * (1 - t) * t * controlLng +
      t * t * destination.lng;

    points.push({ lat: Number(lat.toFixed(6)), lng: Number(lng.toFixed(6)) });
  }

  return points;
}

function riskLevel(score) {
  if (score >= 65) return "severe";
  if (score >= 35) return "caution";
  return "good";
}

app.get(
  "/api/route/recommend",
  authenticate,
  asyncHandler(async (req, res) => {
    const originLat = Number(req.query.originLat);
    const originLng = Number(req.query.originLng);
    const destinationLat = Number(req.query.destinationLat);
    const destinationLng = Number(req.query.destinationLng);

    if (![originLat, originLng, destinationLat, destinationLng].every(Number.isFinite)) {
      return res.status(400).json({
        error: "originLat, originLng, destinationLat, destinationLng are required"
      });
    }

    const origin = { lat: originLat, lng: originLng };
    const destination = { lat: destinationLat, lng: destinationLng };

    const weather = await getWeather(destination);
    const weatherAssessment = assessWeather(weather?.current_weather);
    const googleRoute = await getGoogleRoute(origin, destination);

    const fallbackDistanceKm = haversineKm(origin, destination) * 1.22;
    const primaryDistanceKm = googleRoute ? googleRoute.distanceKm : fallbackDistanceKm;

    const baseEta = googleRoute
      ? googleRoute.durationMin
      : Math.round((primaryDistanceKm / 56) * 60);

    const weatherPenalty = Math.round((weatherAssessment.risk / 100) * 50);
    const primaryEtaMinutes = Math.max(5, baseEta + weatherPenalty);
    const primaryRisk = Math.min(100, weatherAssessment.risk + 14);

    const alternateDistanceKm = primaryDistanceKm * 1.16;
    const alternateBaseEta = Math.round((alternateDistanceKm / 63) * 60);
    const alternateWeatherPenalty =
      weatherAssessment.risk > 50
        ? Math.round(weatherPenalty * 0.3)
        : Math.round(weatherPenalty * 0.75);

    const alternateEtaMinutes = Math.max(5, alternateBaseEta + alternateWeatherPenalty);
    const alternateRisk = Math.max(
      7,
      Math.round(weatherAssessment.risk * 0.42 + 10)
    );

    const offset = Math.min(0.35, Math.max(0.025, primaryDistanceKm / 2800));

    const primary = {
      id: "primary",
      name: "Direct route",
      distanceKm: round1(primaryDistanceKm),
      etaMinutes: primaryEtaMinutes,
      riskScore: primaryRisk,
      riskLevel: riskLevel(primaryRisk),
      path: buildRoutePath(origin, destination, 0),
      source: googleRoute ? "google_distance_matrix" : "heuristic_fallback"
    };

    const alternate = {
      id: "alternate",
      name:
        weatherAssessment.level === "good"
          ? "Alternate corridor"
          : "Weather-avoidance corridor",
      distanceKm: round1(alternateDistanceKm),
      etaMinutes: alternateEtaMinutes,
      riskScore: alternateRisk,
      riskLevel: riskLevel(alternateRisk),
      path: buildRoutePath(origin, destination, offset),
      source: "ai_heuristic"
    };

    let recommendedId = "primary";
    let recommendationReason =
      "Direct route has acceptable weather and estimated time.";

    if (
      weatherAssessment.level === "severe" ||
      (primaryRisk > alternateRisk + 18 && alternateEtaMinutes <= primaryEtaMinutes * 1.35)
    ) {
      recommendedId = "alternate";
      recommendationReason = `AI recommends the alternate corridor due to ${weatherAssessment.summary.toLowerCase()} and lower operational risk.`;
    } else if (
      weatherAssessment.level === "caution" &&
      alternateEtaMinutes <= primaryEtaMinutes * 1.08
    ) {
      recommendedId = "alternate";
      recommendationReason =
        "Alternate route has similar ETA and lower operational risk.";
    }

    return res.json({
      origin,
      destination,
      weather: {
        ...weatherAssessment,
        raw: weather?.current_weather || null
      },
      options: [primary, alternate],
      recommendedId,
      recommendationReason,
      googleUsed: Boolean(googleRoute)
    });
  })
);

app.get(
  "/api/route/optimize",
  authenticate,
  asyncHandler(async (req, res) => {
    const db = await readDb();
    const vehicle = db.vehicles.find((v) => v.id === req.query.vehicleId);
    if (!vehicle) return res.status(404).json({ error: "Vehicle not found" });

    if (req.user.role !== "manager") {
      const driverVehicle = db.vehicles.find((v) => v.driverId === req.user.id);
      if (!driverVehicle || driverVehicle.id !== vehicle.id) {
        return res.status(403).json({ error: "Forbidden" });
      }
    }

    const stops = db.shipments
      .filter((s) => s.vehicleId === vehicle.id && isShipmentActive(s))
      .map((s) => ({
        id: s.id,
        code: s.code,
        label: s.destination.label,
        lat: s.destination.lat,
        lng: s.destination.lng
      }));

    let current =
      vehicle.location && Number.isFinite(vehicle.location.lat)
        ? vehicle.location
        : { lat: 20.5937, lng: 78.9629 };

    const remaining = [...stops];
    const orderedStops = [];

    while (remaining.length > 0) {
      let bestIndex = 0;
      let bestDistance = Infinity;

      remaining.forEach((stop, index) => {
        const distance = haversineKm(current, stop);
        if (distance < bestDistance) {
          bestDistance = distance;
          bestIndex = index;
        }
      });

      const next = remaining.splice(bestIndex, 1)[0];
      orderedStops.push({
        ...next,
        distanceFromPrevKm: round1(bestDistance)
      });

      current = next;
    }

    return res.json({
      vehicleId: vehicle.id,
      origin: vehicle.location,
      orderedStops,
      totalKm: round1(orderedStops.reduce((sum, stop) => sum + stop.distanceFromPrevKm, 0))
    });
  })
);

app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).json({ error: err.message || "Internal server error" });
});

ensureDb()
  .then(() => {
    app.listen(PORT, () => {
      console.log(`Smart Fleet Platform running on http://localhost:${PORT}`);
    });
  })
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });

"""The drone fleet simulator.

Owns all drones in memory and runs their autonomous mission state machine:

    IDLE ──assign──▶ LOADING ──▶ EN_ROUTE ──▶ DELIVERING ──▶ RETURNING ──▶ IDLE/CHARGING
                     (package)   (fly to     (hover + drop)  (fly home)      (recharge)
                                  customer)

Smart behaviour:
  • Orders created without a free drone stay PENDING and are auto-assigned
    whenever a suitable drone becomes available.
  • Battery drains while flying; below LOW_BATTERY the drone autonomously
    returns home, charges, then resumes its order (order goes ON_HOLD).
  • Every movement decision is computed by the compiled C/C++ flight
    controller when available (see firmware_bridge.FirmwareBridge).
"""
import asyncio
import logging
import random
import time
from typing import Any, Dict, List, Optional

from backend import database as db
from backend.config import settings
from backend.firmware_bridge import FirmwareBridge
from backend.geoutils import (
    bearing_deg,
    clamp,
    haversine_m,
    move_position,
)
from backend.ws_manager import manager

log = logging.getLogger("fleet")

# ── Simulation tuning ────────────────────────────────────────────
CRUISE_ALT_M = 60.0          # cruise altitude
DELIVERY_HOVER_M = 12.0      # hover height above the customer drop point
LOAD_SECONDS = 6.0           # package loading time at the shop
DELIVER_SECONDS = 6.0        # hover-and-drop time at the customer
CHARGE_RATE_PCT_S = 1.5      # battery % gained per simulated second
DRAIN_PCT_S_FLYING = 0.06    # battery % lost per simulated second flying
DRAIN_PCT_PER_KM = 0.85      # battery % lost per km flown
LOW_BATTERY_PCT = 22.0       # auto-return threshold
RESERVE_PCT = 15.0           # kept for the return leg when assigning


def now_iso():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


class Drone:
    def __init__(self, drone_id: int, name: str, model: str):
        self.id = drone_id
        self.name = name
        self.model = model
        self.lat = settings.SHOP_LAT + random.uniform(-0.0004, 0.0004)
        self.lng = settings.SHOP_LNG + random.uniform(-0.0004, 0.0004)
        self.alt = 0.0
        self.battery = random.uniform(88.0, 100.0)
        self.status = "IDLE"
        self.speed = 0.0
        self.heading = 0.0
        self.order_id: Optional[int] = None
        self.phase_timer = 0.0
        self._eta_counter = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "model": self.model,
            "status": self.status,
            "lat": round(self.lat, 6),
            "lng": round(self.lng, 6),
            "alt": round(self.alt, 1),
            "speed": round(self.speed * 3.6, 1),   # km/h for the UI
            "heading": round(self.heading, 1),
            "battery": round(self.battery, 1),
            "order_id": self.order_id,
        }


class Fleet:
    def __init__(self):
        self.drones: Dict[int, Drone] = {}
        self.bridges: Dict[int, FirmwareBridge] = {}
        self._task: Optional[asyncio.Task] = None
        self._tick = 0

    # ── lifecycle ────────────────────────────────────────────────
    def start(self):
        for i in range(1, settings.DRONE_COUNT + 1):
            self.add_drone(f"DRONE-{i}", "SkyCart X1-Pro")
        # Orders left mid-flight by a previous run go back to the queue.
        db.execute(
            "UPDATE orders SET drone_id=NULL, status='PENDING', updated_at=datetime('now') "
            "WHERE status IN ('ASSIGNED','LOADING','IN_TRANSIT','DELIVERING')"
        )
        self._task = asyncio.get_running_loop().create_task(self._run())
        log.info("Fleet started with %d drone(s)", len(self.drones))

    def stop(self):
        if self._task:
            self._task.cancel()
        for bridge in self.bridges.values():
            bridge.kill()
        log.info("Fleet stopped")

    def add_drone(self, name: str, model: str) -> Drone:
        drone_id = (max(self.drones) + 1) if self.drones else 1
        drone = Drone(drone_id, name, model)
        self.drones[drone_id] = drone
        self.bridges[drone_id] = FirmwareBridge()
        return drone

    # ── async loop ───────────────────────────────────────────────
    async def _run(self):
        last = time.monotonic()
        while True:
            await asyncio.sleep(settings.SIM_TICK_SECONDS)
            now = time.monotonic()
            dt = (now - last) * settings.SIM_SPEED
            last = now
            events: List[dict] = []
            try:
                self.tick(dt, events)
            except Exception:
                log.exception("Fleet tick failed")
            try:
                await manager.broadcast(
                    {"type": "drones", "drones": [d.to_dict() for d in self.drones.values()]}
                )
                for ev in events:
                    await manager.broadcast(ev)
            except Exception:
                log.exception("Broadcast failed")

    # ── main tick: advance every drone one step ──────────────────
    def tick(self, dt: float, events: List[dict]):
        self._tick += 1
        if self._tick % 4 == 0:
            self._auto_assign_pending(events)
        for drone in list(self.drones.values()):
            self._tick_drone(drone, dt, events)

    def _tick_drone(self, d: Drone, dt: float, events: List[dict]):
        if d.status == "IDLE":
            return

        if d.status == "CHARGING":
            d.battery = min(100.0, d.battery + CHARGE_RATE_PCT_S * dt)
            if d.battery >= 90.0:
                order = db.order_row(d.order_id) if d.order_id else None
                if order and order["status"] == "ON_HOLD":
                    d.status = "EN_ROUTE"
                    db.set_order_status(d.order_id, "IN_TRANSIT", "resumed after recharge")
                    events.append(self._order_event(d.order_id, "resumed"))
                else:
                    d.status = "IDLE"
            return

        if d.status == "LOADING":
            d.phase_timer -= dt
            if d.phase_timer <= 0:
                d.status = "EN_ROUTE"
                db.set_order_status(d.order_id, "IN_TRANSIT")
                events.append(self._order_event(d.order_id, "in_transit"))
            return

        if d.status == "EN_ROUTE":
            order = db.order_row(d.order_id) if d.order_id else None
            if not order or order["status"] not in ("IN_TRANSIT", "ASSIGNED"):
                d.status = "RETURNING"
                d.order_id = None
                return
            self._fly(d, order["lat"], order["lng"], DELIVERY_HOVER_M, dt)
            dist = haversine_m(d.lat, d.lng, order["lat"], order["lng"])
            if dist < 8.0 and d.alt < DELIVERY_HOVER_M + 2.0:
                d.status = "DELIVERING"
                d.speed = 0.0
                d.phase_timer = DELIVER_SECONDS
                db.set_order_status(d.order_id, "DELIVERING")
                events.append(self._order_event(d.order_id, "delivering"))
            elif d.battery <= LOW_BATTERY_PCT:
                db.set_order_status(d.order_id, "ON_HOLD", "drone returned: low battery")
                events.append(self._order_event(d.order_id, "on_hold"))
                d.status = "RETURNING"
            return

        if d.status == "DELIVERING":
            d.alt = max(2.0, d.alt - 6.0 * dt)   # gentle final descent
            d.phase_timer -= dt
            if d.phase_timer <= 0:
                order_id = d.order_id
                db.complete_order(order_id)
                events.append(self._order_event(order_id, "delivered"))
                d.order_id = None
                d.status = "RETURNING"
            return

        if d.status == "RETURNING":
            self._fly(d, settings.SHOP_LAT, settings.SHOP_LNG, 0.0, dt)
            dist = haversine_m(d.lat, d.lng, settings.SHOP_LAT, settings.SHOP_LNG)
            if dist < 8.0 and d.alt < 3.0:
                d.alt = 0.0
                d.speed = 0.0
                d.order_id = None
                d.status = "CHARGING" if d.battery < 90.0 else "IDLE"
            return

    # ── movement (via C/C++ firmware when compiled) ──────────────
    def _fly(self, d: Drone, tgt_lat: float, tgt_lng: float, tgt_alt: float, dt: float):
        cmd = self._step_controller(d, tgt_lat, tgt_lng, tgt_alt, dt)
        d.heading = cmd["heading"]
        d.speed = cmd["speed"]
        dist_m = d.speed * dt
        if dist_m > 0:
            d.lat, d.lng = move_position(d.lat, d.lng, d.heading, dist_m)
        d.alt = max(0.0, d.alt + cmd["vspeed"] * dt)
        d.battery = max(
            0.0, d.battery - DRAIN_PCT_S_FLYING * dt - (dist_m / 1000.0) * DRAIN_PCT_PER_KM
        )
        self._update_eta(d, tgt_lat, tgt_lng)

    def _step_controller(self, d: Drone, tgt_lat: float, tgt_lng: float,
                         tgt_alt: float, dt: float) -> Dict[str, float]:
        bridge = self.bridges.get(d.id)
        if bridge and bridge.available:
            try:
                return bridge.step(
                    d.lat, d.lng, d.alt, tgt_lat, tgt_lng, tgt_alt,
                    d.battery, settings.DRONE_SPEED_MPS, dt,
                )
            except Exception:
                log.warning("Drone %s: firmware failed, switching to Python controller", d.id)
        return self._python_controller(d, tgt_lat, tgt_lng, tgt_alt, dt)

    @staticmethod
    def _python_controller(d: Drone, tgt_lat: float, tgt_lng: float,
                           tgt_alt: float, dt: float) -> Dict[str, float]:
        """Pure-Python twin of the C++ flight controller (used when the
        firmware binary is not compiled)."""
        dist = haversine_m(d.lat, d.lng, tgt_lat, tgt_lng)
        heading = bearing_deg(d.lat, d.lng, tgt_lat, tgt_lng) if dist > 0.01 else d.heading
        if dist <= 1.5:
            speed = 0.0
        elif dist < 25.0:
            speed = clamp(dist * 0.5, 1.0, settings.DRONE_SPEED_MPS)
        else:
            speed = clamp(2.0 + 0.45 * dist, 2.5, settings.DRONE_SPEED_MPS)
        accel = clamp(speed - d.speed, -8.0 * dt, 8.0 * dt)
        speed = clamp(d.speed + accel, 0.0, settings.DRONE_SPEED_MPS)
        alt_set = CRUISE_ALT_M if dist > 40.0 else tgt_alt
        vspeed = clamp(alt_set - d.alt, -3.0, 3.0)
        return {"heading": heading, "speed": speed, "vspeed": vspeed, "alt_cmd": alt_set,
                "telemetry": ""}

    def _update_eta(self, d: Drone, tgt_lat: float, tgt_lng: float):
        d._eta_counter += 1
        if d._eta_counter % 4:   # every ~2 real seconds is plenty
            return
        if d.status != "EN_ROUTE" or not d.order_id:
            return
        dist_km = haversine_m(d.lat, d.lng, tgt_lat, tgt_lng) / 1000.0
        eta = dist_km / max(1.0, settings.speed_kmh / 60.0)
        db.execute(
            "UPDATE orders SET eta_min = ?, updated_at = datetime('now') WHERE id = ?",
            (round(eta, 1), d.order_id),
        )

    # ── assignment / commands ────────────────────────────────────
    def _auto_assign_pending(self, events: List[dict]):
        rows = db.query(
            "SELECT * FROM orders WHERE status IN ('PENDING','ON_HOLD') "
            "AND drone_id IS NULL ORDER BY id ASC"
        )
        for order in rows:
            drone = self._pick_drone(order["lat"], order["lng"])
            if drone:
                self._assign(drone, order["id"], events)

    def _pick_drone(self, dest_lat: float, dest_lng: float) -> Optional[Drone]:
        roundtrip_km = 2 * haversine_m(settings.SHOP_LAT, settings.SHOP_LNG, dest_lat, dest_lng) / 1000.0
        needed = roundtrip_km * DRAIN_PCT_PER_KM + RESERVE_PCT + 5.0
        candidates = [
            d for d in self.drones.values()
            if d.status == "IDLE" and d.order_id is None and d.battery >= max(30.0, needed)
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda d: haversine_m(d.lat, d.lng, settings.SHOP_LAT, settings.SHOP_LNG),
        )

    def _assign(self, drone: Drone, order_id: int, events: List[dict]):
        drone.order_id = order_id
        drone.status = "LOADING"
        drone.phase_timer = LOAD_SECONDS
        db.execute(
            "UPDATE orders SET status='ASSIGNED', drone_id=?, updated_at=datetime('now') WHERE id=?",
            (drone.id, order_id),
        )
        events.append(self._order_event(order_id, "assigned"))

    def try_assign_order(self, order_id: int) -> Optional[int]:
        """Called from the REST layer right after an order is created."""
        order = db.order_row(order_id)
        if not order:
            return None
        drone = self._pick_drone(order["lat"], order["lng"])
        if not drone:
            return None
        events: List[dict] = []
        self._assign(drone, order_id, events)
        for ev in events:
            manager.broadcast_threadsafe(ev)
        return drone.id

    def recall(self, drone_id: int) -> bool:
        d = self.drones.get(drone_id)
        if not d or d.status not in ("LOADING", "EN_ROUTE", "DELIVERING"):
            return False
        if d.order_id:
            cancelled = d.order_id
            db.set_order_status(cancelled, "ON_HOLD", "recalled by operator")
            d.order_id = None
            manager.broadcast_threadsafe(self._order_event(cancelled, "on_hold"))
        d.status = "RETURNING"
        return True

    def cancel_order(self, order_id: int) -> None:
        for d in self.drones.values():
            if d.order_id == order_id and d.status in ("LOADING", "EN_ROUTE", "DELIVERING"):
                d.order_id = None
                d.status = "RETURNING"
        db.set_order_status(order_id, "CANCELLED")

    # ── helpers ──────────────────────────────────────────────────
    def drone_name(self, drone_id) -> str:
        if drone_id is None:
            return ""
        d = self.drones.get(int(drone_id))
        return d.name if d else ""

    @staticmethod
    def _order_event(order_id: int, event: str, force_fetch=None) -> dict:
        order = db.order_row(order_id if order_id > 0 else force_fetch)
        if order is None and force_fetch:
            order = {"id": force_fetch}
        return {"type": "order", "event": event, "order": order}


fleet = Fleet()

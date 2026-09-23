"""Order business logic shared by the REST API and the AI assistant tools.

Kept synchronous (SQLite + in-memory fleet) so it can be called from the
LangChain agent tools running in worker threads; broadcasting to the UI is
done via the thread-safe bridge in ws_manager."""
import logging
from typing import Any, Dict, List, Optional

from backend import database as db
from backend.config import settings
from backend.fleet import fleet
from backend.geoutils import haversine_km
from backend.ws_manager import manager

log = logging.getLogger("orders")

CANCELLABLE = ("PENDING", "ASSIGNED", "LOADING", "IN_TRANSIT", "DELIVERING", "ON_HOLD")


def serialize_order(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    out["drone_name"] = fleet.drone_name(row.get("drone_id"))
    return out


def create_order(user: Dict[str, Any], item: str, customer_name: str,
                 customer_phone: str = "", address: str = "",
                 lat: float = 0.0, lng: float = 0.0) -> Dict[str, Any]:
    distance_km = round(haversine_km(settings.SHOP_LAT, settings.SHOP_LNG, lat, lng), 3)
    eta_min = round(distance_km / max(1.0, settings.speed_kmh / 60.0), 1)
    order_id = db.execute(
        "INSERT INTO orders (item, customer_name, customer_phone, address, lat, lng,"
        " status, created_by, distance_km, eta_min)"
        " VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?)",
        (item, customer_name, customer_phone, address, lat, lng, user["id"], distance_km, eta_min),
    )
    drone_id = fleet.try_assign_order(order_id)
    order = db.order_row(order_id)
    manager.broadcast_threadsafe(
        {"type": "order", "event": "created", "order": serialize_order(order)}
    )
    log.info("Order #%s created by %s -> drone=%s", order_id, user["email"], drone_id)
    return serialize_order(order)


def list_orders(user: Dict[str, Any], limit: int = 100) -> List[Dict[str, Any]]:
    if user["role"] == "admin":
        rows = db.query("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,))
    else:
        rows = db.query(
            "SELECT * FROM orders WHERE created_by = ? ORDER BY id DESC LIMIT ?",
            (user["id"], limit),
        )
    return [serialize_order(r) for r in rows]


def get_order(user: Dict[str, Any], order_id: int) -> Optional[Dict[str, Any]]:
    row = db.order_row(order_id)
    if not row:
        return None
    if user["role"] != "admin" and row["created_by"] != user["id"]:
        return None
    return serialize_order(row)


def cancel_order(user: Dict[str, Any], order_id: int) -> Optional[Dict[str, Any]]:
    row = db.order_row(order_id)
    if not row:
        return None
    if user["role"] != "admin" and row["created_by"] != user["id"]:
        return None
    if row["status"] not in CANCELLABLE:
        return None
    fleet.cancel_order(order_id)
    order = serialize_order(db.order_row(order_id))
    manager.broadcast_threadsafe({"type": "order", "event": "cancelled", "order": order})
    return order

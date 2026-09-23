"""First-run seeding: the main admin account, a demo shopkeeper account,
and one delivered demo order so the dashboard has some history."""
import logging

from backend import database as db
from backend.config import settings
from backend.security import hash_password

log = logging.getLogger("seed")


def _ensure_user(name: str, email: str, password: str, role: str,
                 shop_name: str = "") -> None:
    existing = db.query("SELECT id FROM users WHERE email = ?", (email.lower(),), one=True)
    if existing:
        return
    salt_hex, hash_hex = hash_password(password)
    db.execute(
        "INSERT INTO users (name, email, password_hash, salt, role, shop_name)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (name, email.lower(), hash_hex, salt_hex, role, shop_name),
    )
    log.info("Seeded %s account: %s", role, email)


def seed_if_empty() -> None:
    _ensure_user(settings.ADMIN_NAME or "Main Admin",
                 settings.ADMIN_EMAIL or "admin@skycart.com",
                 settings.ADMIN_PASSWORD or "admin123", "admin")
    _ensure_user(settings.SHOPKEEPER_NAME or "Demo Shopkeeper",
                 settings.SHOPKEEPER_EMAIL or "shop@skycart.com",
                 settings.SHOPKEEPER_PASSWORD or "shop123", "shopkeeper",
                 shop_name=settings.SHOP_NAME)

    # One delivered demo order (only if there is no order history at all).
    if not db.query("SELECT id FROM orders LIMIT 1", one=True):
        shop_user = db.query(
            "SELECT id FROM users WHERE email = ?",
            (settings.SHOPKEEPER_EMAIL.lower(),), one=True,
        )
        created_by = shop_user["id"] if shop_user else 1
        db.execute(
            "INSERT INTO orders (item, customer_name, customer_phone, address, lat, lng,"
            " status, drone_id, created_by, distance_km, eta_min, delivered_at)"
            " VALUES ('Medicines (demo)', 'Anita Rao', '9990001111', 'MG Road Metro Station',"
            " 12.9756, 77.6068, 'DELIVERED', NULL, ?, 1.9, 0, datetime('now'))",
            (created_by,),
        )
        log.info("Seeded one demo delivered order")

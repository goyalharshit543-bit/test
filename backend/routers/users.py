"""User management (admin only): create shopkeeper/admin accounts, toggle access."""
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend import database as db
from backend.deps import get_current_user, require_admin
from backend.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


class UserIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=6, max_length=128)
    role: str = "shopkeeper"
    shop_name: str = ""


class ActiveIn(BaseModel):
    active: bool


def _public(user: Dict) -> Dict:
    user = dict(user)
    user.pop("password_hash", None)
    user.pop("salt", None)
    return user


@router.get("")
def list_users(_: Dict = Depends(require_admin)) -> List[Dict]:
    rows = db.query("SELECT * FROM users ORDER BY id ASC")
    return [_public(r) for r in rows]


@router.post("", status_code=201)
def create_user(body: UserIn, admin: Dict = Depends(require_admin)):
    if body.role not in ("admin", "shopkeeper"):
        raise HTTPException(status_code=400, detail="role must be 'admin' or 'shopkeeper'")
    email = body.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Please enter a valid email address")
    if db.query("SELECT id FROM users WHERE email = ?", (email,), one=True):
        raise HTTPException(status_code=400, detail="A user with this email already exists")
    salt_hex, hash_hex = hash_password(body.password)
    user_id = db.execute(
        "INSERT INTO users (name, email, password_hash, salt, role, shop_name)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (body.name.strip(), email, hash_hex, salt_hex, body.role, body.shop_name.strip()),
    )
    return _public(db.user_row(user_id))


@router.patch("/{user_id}/active")
def set_active(user_id: int, body: ActiveIn, admin: Dict = Depends(require_admin)):
    target = db.user_row(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["id"] == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot disable your own account")
    if target["role"] == "admin" and not body.active:
        raise HTTPException(status_code=400, detail="Admin accounts cannot be disabled")
    db.execute("UPDATE users SET active = ? WHERE id = ?", (1 if body.active else 0, user_id))
    return _public(db.user_row(user_id))


@router.get("/me")
def whoami(user: Dict = Depends(get_current_user)):
    return _public(user)

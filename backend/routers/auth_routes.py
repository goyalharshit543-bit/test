"""Authentication router: login + current user."""
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend import database as db
from backend.deps import get_current_user
from backend.security import create_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


def _public_user(user: Dict) -> Dict:
    user = dict(user)
    user.pop("password_hash", None)
    user.pop("salt", None)
    return user


@router.post("/login")
def login(body: LoginIn):
    user = db.query(
        "SELECT * FROM users WHERE email = ?", (body.email.strip().lower(),), one=True
    )
    if not user or not verify_password(body.password, user["salt"], user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user["active"]:
        raise HTTPException(status_code=403, detail="Account disabled — contact the admin")
    return {"token": create_token(user), "user": _public_user(user)}


@router.get("/me")
def me(user: Dict = Depends(get_current_user)):
    return _public_user(user)

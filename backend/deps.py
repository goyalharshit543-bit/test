"""FastAPI dependencies for authentication and role checks."""
from typing import Any, Dict

from fastapi import Depends, HTTPException, Request, WebSocket, status

from backend import database as db
from backend.security import decode_token


def _user_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.user_row(user_id)
    if not user or not user["active"]:
        raise HTTPException(status_code=401, detail="Account not found or disabled")
    user.pop("password_hash", None)
    user.pop("salt", None)
    return user


def get_current_user(request: Request) -> Dict[str, Any]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth[7:].strip()
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(
            status_code=401, detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _user_from_payload(payload)


def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def ws_current_user(ws: WebSocket) -> Dict[str, Any]:
    """Validate a WebSocket connection's ?token= query param."""
    token = ws.query_params.get("token", "")
    if not token:
        raise PermissionError("Missing token")
    payload = decode_token(token)
    return _user_from_payload(payload)

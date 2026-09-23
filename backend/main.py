"""FastAPI application entry point.

Serves:
  • the REST API under /api
  • the live-tracking WebSocket at /ws?token=JWT
  • the website (frontend/) at / and /dashboard

Run with:  python -m backend.main
   or:     uvicorn backend.main:app --reload
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend import database as db
from backend.ai.assistant import assistant
from backend.config import settings
from backend.deps import get_current_user, ws_current_user
from backend.fleet import fleet
from backend.routers import ai_routes, auth_routes, drones, geocode, orders, users
from backend.seed import seed_if_empty
from backend.ws_manager import manager

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    seed_if_empty()
    manager.main_loop = asyncio.get_running_loop()
    fleet.start()
    yield
    fleet.stop()


app = FastAPI(title="Smart Drone Delivery", version="1.0.0", lifespan=lifespan)

# Allow the frontend to be developed from VS Code Live Server etc.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(drones.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(ai_routes.router, prefix="/api")
app.include_router(geocode.router, prefix="/api")


# ── misc API ────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"ok": True, "service": "smart-drone-delivery"}


@app.get("/api/config")
def frontend_config(user: dict = Depends(get_current_user)):
    """Public-ish settings the dashboard needs at startup."""
    return {
        "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
        "shop": {"name": settings.SHOP_NAME,
                 "lat": settings.SHOP_LAT, "lng": settings.SHOP_LNG},
        "ai_engine": assistant.engine_label(),
        "speed_kmh": round(settings.speed_kmh, 1),
        "sim_speed": settings.SIM_SPEED,
        "firmware_engine": "C/C++ flight controller"
        if any(b.available for b in fleet.bridges.values()) else "Python fallback",
    }


# ── WebSocket: live tracking ────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    try:
        ws_current_user(ws)
    except Exception:
        await ws.close(code=4401)
        return
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # client keep-alive pings
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)


# ── Website ─────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(FRONTEND_DIR / "dashboard.html")


if __name__ == "__main__":
    import socket
    import sys

    # Windows consoles default to cp1252 and crash on emoji in banners.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    import uvicorn

    # Fail fast with a friendly message when the port is taken — that always
    # means a previous SkyCart server is still running somewhere.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(0.5)
    if probe.connect_ex(("127.0.0.1", settings.PORT)) == 0:
        probe.close()
        print(f"\n❌  Port {settings.PORT} is already busy — a previous SkyCart server is still running.")
        print("    Fix 1: stop the old one → close its terminal, or Ctrl+C in it, or:")
        print(f"           taskkill /F /PID <pid> /T     (find it with:  netstat -ano | findstr :{settings.PORT})")
        print(f"    Fix 2: use another port →  put  PORT=8080  in .env, then open http://localhost:8080\n")
        sys.exit(1)
    probe.close()

    print(f"\n🛸  SkyCart server starting →  http://localhost:{settings.PORT}   (Ctrl+C to stop)\n")
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)

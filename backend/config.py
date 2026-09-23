"""Central configuration for the Smart Drone Delivery backend."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class Settings:
    """All tunables in one place. Everything can be overridden in .env."""

    # ── Server ────────────────────────────────────────────────
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    JWT_ALGORITHM: str = "HS256"
    TOKEN_EXPIRE_HOURS: int = int(os.getenv("TOKEN_EXPIRE_HOURS", "12"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # ── Database ──────────────────────────────────────────────
    DB_PATH: str = os.getenv("DB_PATH", str(BASE_DIR / "data" / "drone_delivery.db"))

    # First-run accounts (used by seed.py, override in .env)
    ADMIN_NAME: str = os.getenv("ADMIN_NAME", "Main Admin")
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@skycart.com")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")
    SHOPKEEPER_NAME: str = os.getenv("SHOPKEEPER_NAME", "Demo Shopkeeper")
    SHOPKEEPER_EMAIL: str = os.getenv("SHOPKEEPER_EMAIL", "shop@skycart.com")
    SHOPKEEPER_PASSWORD: str = os.getenv("SHOPKEEPER_PASSWORD", "shop123")

    # ── Shop / drone home base ────────────────────────────────
    SHOP_NAME: str = os.getenv("SHOP_NAME", "SkyCart Central Store")
    SHOP_LAT: float = _f("SHOP_LAT", 12.9716)
    SHOP_LNG: float = _f("SHOP_LNG", 77.5946)

    # ── Drone fleet & simulation ──────────────────────────────
    DRONE_COUNT: int = int(os.getenv("DRONE_COUNT", "3"))
    DRONE_SPEED_MPS: float = _f("DRONE_SPEED_MPS", 12.0)   # cruise m/s
    SIM_SPEED: float = _f("SIM_SPEED", 1.0)                # time multiplier
    SIM_TICK_SECONDS: float = 0.5                          # real seconds per tick

    # ── Google Maps (used by the frontend) ────────────────────
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")

    # ── AI assistant (LangChain) ──────────────────────────────
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "auto").lower()
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1")
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")

    # ── Compiled flight controller (C/C++) ────────────────────
    FIRMWARE_BIN: str = os.getenv(
        "FIRMWARE_BIN", str(BASE_DIR / "firmware" / "build" / "drone_controller")
    )

    @property
    def speed_kmh(self) -> float:
        """Effective simulated speed in km/h (used for ETA math)."""
        return self.DRONE_SPEED_MPS * 3.6 * self.SIM_SPEED


settings = Settings()
os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)

"""SkyBot — the personal AI assistant for the drone delivery platform.

Built on LangChain (langchain-core). The LLM is chosen from .env:

    AI_PROVIDER = auto | gemini | openai | ollama | none
      • gemini  — free-tier Google Gemini key (langchain-google-genai)
      • openai  — OpenAI API key (langchain-openai)
      • ollama  — fully local/free (langchain-ollama), needs `ollama serve`
      • auto    — first available of gemini → openai → ollama

If no LLM is configured (or LangChain isn't installed / the call fails),
SkyBot falls back to a built-in rule-based assistant that still answers
live questions from fleet data — the platform always has a working AI.

The agent is a small tool-calling loop over `model.bind_tools(...)`, which
is stable across LangChain versions: SkyBot can check drones, inspect and
create orders, estimate ETAs and recall drones on your behalf.
"""
import asyncio
import logging
import re
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from backend import database as db
from backend.config import settings
from backend.fleet import fleet
from backend.geocode import resolve_place, search_places
from backend.order_service import create_order, serialize_order

log = logging.getLogger("skybot")


# ── tools (built per-request so they honour the caller's role) ──────
def _build_tools(user: Dict[str, Any]):
    from langchain_core.tools import tool

    def orders_visible():
        if user["role"] == "admin":
            return db.query("SELECT * FROM orders ORDER BY id DESC LIMIT 50")
        return db.query(
            "SELECT * FROM orders WHERE created_by = ? ORDER BY id DESC LIMIT 50",
            (user["id"],),
        )

    @tool
    def list_drones() -> str:
        """List every drone in the fleet with its status, battery and current job."""
        lines = []
        for d in fleet.drones.values():
            dd = d.to_dict()
            lines.append(
                f"{dd['name']}: status={dd['status']}, battery={dd['battery']}%, "
                f"speed={dd['speed']} km/h, position=({dd['lat']}, {dd['lng']}), "
                f"order_id={dd['order_id']}"
            )
        return "\n".join(lines) or "No drones in fleet."

    @tool
    def get_order_status(order_id: int) -> str:
        """Get the full status of one order by its numeric id."""
        row = db.order_row(order_id)
        if not row or (user["role"] != "admin" and row["created_by"] != user["id"]):
            return f"Order {order_id} not found (or you don't have access)."
        o = serialize_order(row)
        addr = o["address"] or f"({o['lat']}, {o['lng']})"
        return (
            f"Order #{o['id']}: {o['item']} for {o['customer_name']} — status={o['status']}, "
            f"drone={o['drone_name'] or 'unassigned'}, distance={o['distance_km']} km, "
            f"ETA={o['eta_min']} min, address={addr}"
        )

    @tool
    def list_recent_orders(status: str = "") -> str:
        """List recent orders, optionally filtered by status (e.g. IN_TRANSIT, PENDING)."""
        rows = orders_visible()
        if status:
            rows = [r for r in rows if r["status"] == status.upper()]
        if not rows:
            return "No matching orders."
        return "\n".join(
            f"#{r['id']} {r['item']} → {r['customer_name']} [{r['status']}] "
            f"drone={fleet.drone_name(r.get('drone_id'))} ETA={r['eta_min']}min"
            for r in rows[:15]
        )

    @tool
    def find_place(place_name: str) -> str:
        """Look up a place by name and return its coordinates.
        Use this before create_order when the user gives a place name
        instead of coordinates."""
        hits = search_places(place_name)
        if not hits:
            return f"No place found for '{place_name}'. Ask the user for a more specific name."
        return "\n".join(f"{h['label']} → lat {h['lat']}, lng {h['lng']}" for h in hits[:3])

    @tool
    def create_order(item: str, customer_name: str,
                     place: str = "", lat: float = 0.0, lng: float = 0.0,
                     customer_phone: str = "", address: str = "") -> str:
        """Create a new delivery order. Pass either `place` (a place name,
        e.g. 'Indiranagar, Bengaluru' — coordinates are resolved automatically)
        or explicit lat/lng coordinates."""
        resolved = ""
        if not (place or lat or lng):
            return "I need a drop location — give me a place name or coordinates."
        if place and not (lat or lng):
            hit = resolve_place(place)
            if not hit:
                return (f"I couldn't find '{place}'. Try a more specific place name "
                        "or give me coordinates.")
            lat, lng = hit["lat"], hit["lng"]
            resolved = hit["label"]
        order = create_order(
            user, item=item, customer_name=customer_name,
            customer_phone=customer_phone, address=address or resolved,
            lat=lat, lng=lng,
        )
        drone = order.get("drone_name") or "no drone free — it will be auto-assigned"
        where = f" at {resolved}" if resolved else ""
        return (f"Order #{order['id']} created for {order['customer_name']}{where}. "
                f"Assigned drone: {drone}. Estimated delivery: {order['eta_min']} min.")

    @tool
    def estimate_delivery(order_id: int) -> str:
        """Estimate when an order will be delivered (distance + live ETA)."""
        row = db.order_row(order_id)
        if not row or (user["role"] != "admin" and row["created_by"] != user["id"]):
            return f"Order {order_id} not found."
        if row["status"] == "DELIVERED":
            return f"Order #{order_id} was already delivered at {row['delivered_at']}."
        return (f"Order #{order_id} is {row['status']} with live ETA ≈ {row['eta_min']} min "
                f"({row['distance_km']} km from the shop).")

    @tool
    def recall_drone(drone_id: int) -> str:
        """Command a flying drone to return to the shop immediately (its order goes on hold)."""
        ok = fleet.recall(drone_id)
        if not ok:
            return f"Drone {drone_id} can't be recalled right now (not flying)."
        return f"Drone {drone_id} is returning to base."

    return [list_drones, get_order_status, list_recent_orders,
            find_place, create_order, estimate_delivery, recall_drone]


_SYSTEM_PROMPT = (
    "You are SkyBot, the AI copilot of SkyCart — a smart drone delivery company. "
    "You help shopkeepers and the admin track drones, create orders and answer "
    "questions using your tools. The shop (drone home base) is '{shop}' at "
    "lat {lat}, lng {lng}. Drones cruise at about {speed} km/h. "
    "When the user names a place for a delivery, call find_place first to resolve "
    "it to coordinates, then create_order. "
    "Always call tools for live data instead of guessing. Be concise and friendly."
)


# ── rule-based fallback (no LLM needed) ─────────────────────────────
def _rule_based(user: Dict[str, Any], message: str) -> str:
    msg = message.lower()
    drone_m = re.search(r"drone[ _-]?(\d+)", msg)
    order_m = re.search(r"order[ _#-]?(\d+)", msg)

    if order_m:
        oid = int(order_m.group(1))
        row = db.order_row(oid)
        if not row or (user["role"] != "admin" and row["created_by"] != user["id"]):
            return f"I couldn't find order #{oid} in your orders."
        o = serialize_order(row)
        return (f"Order #{o['id']} ({o['item']} → {o['customer_name']}): "
                f"status {o['status']}, drone {o['drone_name'] or 'unassigned'}, "
                f"ETA ≈ {o['eta_min']} min, distance {o['distance_km']} km.")

    if drone_m or "where" in msg and "drone" in msg:
        if drone_m:
            d = fleet.drones.get(int(drone_m.group(1)))
            if not d:
                return "No drone with that number."
            dd = d.to_dict()
            return (f"{dd['name']} is {dd['status']} at ({dd['lat']}, {dd['lng']}), "
                    f"battery {dd['battery']}%, speed {dd['speed']} km/h, "
                    f"order {dd['order_id'] or 'none'}.")
        lines = [
            f"{d.to_dict()['name']}: {d.to_dict()['status']} (battery {d.to_dict()['battery']}%)"
            for d in fleet.drones.values()
        ]
        return "Fleet status:\n" + "\n".join(lines)

    if any(k in msg for k in ("help", "what can you", "commands")):
        return (
            "I can: 🚁 report drone status (\"where is drone 1\"), "
            "📦 check orders (\"order status 3\" / \"show recent orders\"), "
            "➕ create an order if you give me item, customer name and drop place name or coordinates, "
            "⏱️ estimate delivery time, and ↩️ recall a drone. "
            "Tip: connect an AI key in .env (GEMINI_API_KEY etc.) to chat naturally."
        )

    if "order" in msg:
        rows = db.query(
            "SELECT id, item, status FROM orders WHERE created_by=? ORDER BY id DESC LIMIT 5",
            (user["id"],),
        )
        listing = "\n".join(f"#{r['id']} {r['item']} [{r['status']}]" for r in rows) or "none yet"
        return f"Your recent orders:\n{listing}\n\nAsk me about a specific order id."

    return (
        "I'm SkyBot 🤖 — try: \"where is drone 1\", \"status of order 3\", "
        "\"show recent orders\", or \"help\"."
    )


# ── the assistant ───────────────────────────────────────────────────
class DroneAI:
    def __init__(self):
        self._llm = None
        self._engine = ""
        self._tried = False

    def engine_label(self) -> str:
        self._ensure_llm()
        return self._engine or "rule-based"

    def _ollama_running(self) -> bool:
        try:
            with urllib.request.urlopen(
                f"{settings.OLLAMA_URL.rstrip('/')}/api/tags", timeout=1.5
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _ensure_llm(self):
        if self._tried:
            return
        self._tried = True
        provider = settings.AI_PROVIDER
        try:
            if provider in ("auto", ""):
                if settings.GEMINI_API_KEY:
                    provider = "gemini"
                elif settings.OPENAI_API_KEY:
                    provider = "openai"
                elif self._ollama_running():
                    provider = "ollama"
                else:
                    provider = "none"

            if provider == "gemini" and settings.GEMINI_API_KEY:
                from langchain_google_genai import ChatGoogleGenerativeAI

                self._llm = ChatGoogleGenerativeAI(
                    model=settings.GEMINI_MODEL,
                    google_api_key=settings.GEMINI_API_KEY,
                    temperature=0.2,
                )
                self._engine = f"langchain-gemini:{settings.GEMINI_MODEL}"
            elif provider == "openai" and settings.OPENAI_API_KEY:
                from langchain_openai import ChatOpenAI

                self._llm = ChatOpenAI(
                    model=settings.OPENAI_MODEL,
                    api_key=settings.OPENAI_API_KEY,
                    temperature=0.2,
                )
                self._engine = f"langchain-openai:{settings.OPENAI_MODEL}"
            elif provider == "ollama" and self._ollama_running():
                from langchain_ollama import ChatOllama

                self._llm = ChatOllama(
                    model=settings.OLLAMA_MODEL, base_url=settings.OLLAMA_URL,
                    temperature=0.2,
                )
                self._engine = f"langchain-ollama:{settings.OLLAMA_MODEL}"
            else:
                self._engine = "rule-based"
        except ImportError as exc:
            log.warning("LangChain provider not installed (%s) — using rule-based AI", exc)
            self._llm = None
            self._engine = "rule-based"
        except Exception as exc:
            log.warning("LLM init failed (%s) — using rule-based AI", exc)
            self._llm = None
            self._engine = "rule-based"

    # ── the tool-calling agent loop (stable across LangChain versions) ──
    def _run_agent(self, user: Dict[str, Any], message: str,
                   history: List[Dict[str, str]]) -> str:
        from langchain_core.messages import (
            AIMessage, HumanMessage, SystemMessage, ToolMessage,
        )

        tools = _build_tools(user)
        tool_map = {t.name: t for t in tools}
        llm = self._llm.bind_tools(tools)

        messages: List[Any] = [
            SystemMessage(content=_SYSTEM_PROMPT.format(
                shop=settings.SHOP_NAME, lat=settings.SHOP_LAT,
                lng=settings.SHOP_LNG, speed=round(settings.speed_kmh))),
        ]
        for m in history[-6:]:
            role = (m.get("role") or "").lower()
            content = (m.get("content") or "")[:1000]
            if not content:
                continue
            messages.append(HumanMessage(content=content) if role in ("user", "human")
                            else AIMessage(content=content))
        messages.append(HumanMessage(content=message))

        reply = "…"
        for _ in range(6):  # hard cap on tool-call rounds
            ai = llm.invoke(messages)
            reply = ai.content or "…"
            calls = getattr(ai, "tool_calls", None)
            if not calls:
                return reply if isinstance(reply, str) else str(reply)
            messages.append(ai)
            for tc in calls:
                tool = tool_map.get(tc.get("name"))
                try:
                    result = tool.invoke(tc.get("args") or {}) if tool else \
                        f"Unknown tool: {tc.get('name')}"
                except Exception as exc:
                    result = f"Tool error: {exc}"
                messages.append(ToolMessage(
                    content=str(result)[:2000], tool_call_id=tc.get("id", "")))
        return reply if isinstance(reply, str) else str(reply)

    async def chat(self, user: Dict[str, Any], message: str,
                   history: List[Dict[str, str]]) -> Tuple[str, str]:
        self._ensure_llm()
        if self._llm is None:
            return _rule_based(user, message), "rule-based"
        try:
            reply = await asyncio.to_thread(self._run_agent, user, message, history)
            if not reply or not reply.strip():
                return _rule_based(user, message), "rule-based (fallback)"
            return reply, self._engine
        except Exception as exc:
            log.warning("LLM call failed (%s) — answering with rule-based AI", exc)
            return _rule_based(user, message), "rule-based (fallback)"


assistant = DroneAI()

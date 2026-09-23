# 🛸 SkyCart — Smart Drone Delivery (AI + C/C++ + Python + Web)

An end-to-end **autonomous drone delivery platform**:

> A shopkeeper enters the customer's location → the platform assigns the
> nearest drone → the drone's **C/C++ flight controller** flies the package to
> the customer automatically → everyone watches it move **live on the map** →
> and **SkyBot, a LangChain-powered AI**, answers questions and can even place
> orders for you.

| Layer | Tech | What it does |
|---|---|---|
| Flight controller | **C++** (`firmware/src/*.cpp`) | PID speed + altitude loops, great-circle navigation — the maths a real flight board runs |
| Telemetry encoder | **C** (`firmware/src/telemetry.c`) | NMEA-style `$PXCTL…*checksum` packets, linked into the C++ binary |
| Backend + AI + simulation | **Python** (FastAPI, LangChain) | Auth, orders, live fleet simulation, WebSocket tracking, SkyBot AI |
| Website | **HTML / CSS / JS** | Login page, live map, orders, fleet, user access, AI chat |

```
┌────────────┐  click map / AI tool   ┌─────────────────────────────┐
│  Website   │ ─────────────────────▶ │  Python backend (FastAPI)   │
│ (login +   │ ◀───────────────────── │  · JWT auth + roles         │
│  dashboard)│   WebSocket 2 Hz live  │  · SQLite orders/users      │
└────────────┘                        │  · fleet simulator          │
                                      └──────────────┬──────────────┘
                                              1 line / tick (stdin→stdout)
                                      ┌──────────────▼──────────────┐
                                      │ C/C++ flight controller     │
                                      │ PID · navigation · telemetry│
                                      └─────────────────────────────┘
```

---

## 1. What you need before starting

| Tool | Check with | Notes |
|---|---|---|
| **Python 3.10+** | `python --version` | [python.org/downloads](https://www.python.org/downloads/) — tick *“Add Python to PATH”* on Windows |
| **VS Code** | — | [code.visualstudio.com](https://code.visualstudio.com) |
| **g++ (C++ compiler)** — *optional* | `g++ --version` | Windows: install [MinGW-w64](https://www.mingw-w64.org/) or `winget install -e --id BrechtSanders.WinLibs.POSIX.UCRT`; macOS: `xcode-select --install`; Ubuntu: `sudo apt install build-essential` |
| Google Maps API key — *optional* | — | Without it the site auto-uses **OpenStreetMap** (no key needed) |
| Gemini / OpenAI / Ollama — *optional* | — | Without any key, SkyBot uses its **built-in rule-based brain** |

> ✅ Everything works even if all optional pieces are missing — the C++
> controller has a pure-Python twin and the AI has a rule-based fallback.

## 2. Open the project in VS Code

1. Put this folder somewhere like `C:\projects\smart-drone-delivery`.
2. **VS Code → File → Open Folder…** → select the folder.
3. Recommended extensions (VS Code will suggest them): **Python**, **Pylance**,
   **C/C++** (for the firmware files).

## 3. Setup (one time) — in the VS Code terminal

Open the terminal in VS Code (**Terminal → New Terminal**, `` Ctrl+` ``):

```bash
# 1. Create a virtual environment
python -m venv .venv

# 2. Activate it
#    Windows (PowerShell):
.venv\Scripts\Activate.ps1
#    Windows (if the line above is blocked, use Git Bash / cmd):
.venv\Scripts\activate.bat
#    macOS / Linux:
source .venv/bin/activate

# 3. Install the Python packages
pip install -r requirements.txt

# 4. Create your settings file
#    Windows:
copy .env.example .env
#    macOS / Linux:
cp .env.example .env
```

> 💡 PowerShell blocked the activate script? Run once:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

## 4. Build the C/C++ firmware (optional but recommended)

```bash
# Linux / macOS / Git Bash:
bash scripts/build_firmware.sh

# Windows (cmd):
scripts\build_firmware.bat
```

Success prints `OK → firmware/build/drone_controller`. The backend detects
this binary automatically at startup and every drone then uses the real
C/C++ control loops (the dashboard footer shows *Firmware: C/C++ flight
controller*). If you skip this, drones fly with the Python twin instead.

## 5. Run it 🚀

```bash
python -m backend.main
```

or press **F5** in VS Code (configurations are pre-made in `.vscode/launch.json`).

Now open **http://localhost:8000** in your browser.

### Logins (created automatically on first run)

| Role | Email | Password | Can do |
|---|---|---|---|
| 👑 **Admin (you)** | `admin@skycart.com` | `admin123` | Everything + **create/disable shopkeeper accounts** + add drones |
| 🏪 **Shopkeeper** | `shop@skycart.com` | `shop123` | Create orders, track their deliveries, ask SkyBot |

> Change these in `.env` (`ADMIN_EMAIL`, `ADMIN_PASSWORD`, …) before first run.

## 6. How to use it (2-minute tour)

1. **Sign in** as admin → you land on **Live Tracking** (the map).
2. Click **＋ New Order** → fill item + customer name → **click any spot on
   the map** to set the customer's location → **Create & Dispatch**.
3. Watch: the drone lifts off at the shop (🏬), flies to the 📍, hovers,
   “delivers”, then flies home. The map updates ~2×/second via WebSocket.
4. **📦 Orders** tab: full history with status, distance, live ETA, cancel.
5. **🚁 Drones** tab: battery bars, speeds, **Recall home** button.
6. **👥 Users** (admin): give a shopkeeper access — name, email, password —
   and they can log in and place orders for your shop. Disable anytime.
7. **🤖 AI Assistant**: chat with SkyBot — try:
   - *“Where is drone 1?”*
   - *“Show recent orders”*
   - *“Status of order 3”*
   - *“Create an order for medicines for Anita at 12.9756, 77.6068”*
8. Log in as the shopkeeper in another browser to see role separation
   (they only see their own orders, and no Users tab).

### Simulation speed

Real-time flights (5 km ≈ 7 min at 12 m/s) are realistic but slow to demo.
Set `SIM_SPEED=4` (4× faster) in `.env` — ETAs update to match.

## 7. Google Maps setup (optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → create a project.
2. Enable **Maps JavaScript API** → *Credentials → Create API key*.
3. Put it in `.env`: `GOOGLE_MAPS_API_KEY=AIza…`
4. Restart the server. The map header will show `Map: Google Maps`.

No key? Everything still works on OpenStreetMap tiles — same features.

## 8. AI assistant setup (optional)

SkyBot uses **LangChain** with a tool-calling agent. Pick one:

- **Gemini (free key):** get one at [aistudio.google.com](https://aistudio.google.com/apikey)
  → `.env`: `GEMINI_API_KEY=…`
- **OpenAI:** `OPENAI_API_KEY=sk-…`
- **Ollama (local, free):** install [ollama.com](https://ollama.com), then
  `ollama pull llama3.1` and `ollama serve`.

`AI_PROVIDER=auto` picks the first available one. With none configured,
the rule-based fallback still answers fleet questions live.

## 9. Project structure (every file separate, as requested)

```
smart-drone-delivery/
├── run & config
│   ├── requirements.txt          Python packages
│   ├── .env.example              copy to .env → your settings
│   └── .vscode/launch.json       press F5 in VS Code
├── backend/                      ── PYTHON ──
│   ├── main.py                   FastAPI app: API + WebSocket + website
│   ├── config.py                 reads .env into one Settings object
│   ├── database.py               SQLite (users, orders) helpers
│   ├── security.py               PBKDF2 password hashing + JWT
│   ├── deps.py                   “who are you / are you admin” guards
│   ├── geoutils.py               distance / bearing / movement maths
│   ├── geocode.py                place name ↔ coordinates (Nominatim / Google)
│   ├── fleet.py                  🚁 drone fleet simulator (state machine)
│   ├── firmware_bridge.py        talks to the C++ binary per drone
│   ├── ws_manager.py             live WebSocket broadcaster
│   ├── order_service.py          create/list/cancel logic (API + AI share it)
│   ├── seed.py                   creates admin + shopkeeper on first run
│   ├── routers/
│   │   ├── auth_routes.py        POST /api/auth/login, GET /api/auth/me
│   │   ├── users.py              admin: create shopkeepers, enable/disable
│   │   ├── drones.py             fleet list, add drone, recall
│   │   ├── orders.py             create / list / track / cancel orders
│   │   ├── geocode.py            place search + reverse geocoding
│   │   └── ai_routes.py          SkyBot chat endpoint
│   └── ai/
│       └── assistant.py          LangChain agent (SkyBot) + fallback
├── firmware/                     ── C / C++ ──
│   ├── Makefile                  make -C firmware
│   ├── include/                  pid.h, navigation.h, telemetry.h
│   └── src/
│       ├── main.cpp              control loop (stdin/stdout protocol)
│       ├── pid.cpp               PID speed + altitude loops
│       ├── navigation.cpp        haversine distance + bearing
│       └── telemetry.c           C telemetry packet encoder
├── frontend/                     ── HTML / CSS / JS ──
│   ├── index.html                login page
│   ├── dashboard.html            command center (map/orders/drones/users/chat)
│   ├── css/style.css             dark ops-center styling
│   └── js/
│       ├── api.js                fetch + WebSocket helpers
│       ├── login.js              login page logic
│       └── dashboard.js          live map (Google/Leaflet) + all UI logic
└── scripts/
    ├── build_firmware.sh / .bat  compile the C/C++ controller
    └── (fallback: no compiler needed, Python twin takes over)
```

### How the pieces connect

1. Browser → `POST /api/auth/login` → JWT stored in `localStorage`.
2. Dashboard opens `ws://…/ws?token=JWT` → receives drone positions 2×/s.
3. “Create order” → type a **place name** (auto-suggested + geocoded) or
   click the map (reverse-geocoded) → `POST /api/orders` →
   `order_service.create_order` →
   `fleet.try_assign_order` picks the best drone → status `LOADING →
   EN_ROUTE → DELIVERING → DELIVERED`.
4. Every 0.5 s the simulator ticks each drone: current state goes **over
   stdin** to `drone_controller` (C++), which returns heading/speed/vertical
   speed computed by its PID loops — Python just applies them.
5. SkyBot (LangChain) gets tools that call the *same* order/fleet functions,
   so anything you can click, the AI can do too.

## 10. API reference (all JSON, `Authorization: Bearer <token>`)

| Method & path | Who | Purpose |
|---|---|---|
| `POST /api/auth/login` | public | get JWT |
| `GET /api/auth/me` | any | current user |
| `GET /api/config` | any | map key, shop location, engines |
| `GET /api/drones` | any | fleet snapshot |
| `POST /api/drones` | admin | add drone |
| `POST /api/drones/{id}/recall` | any | order drone home |
| `GET /api/orders` | any (filtered) | list orders |
| `POST /api/orders` | any | create + auto-assign — accepts a **place name** (`place`) or `lat`/`lng` |
| `GET /api/geocode/search?q=…` | any | place-name autocomplete → `{label, lat, lng}` |
| `POST /api/geocode/reverse` | any | coordinates → place name (map clicks) |
| `GET /api/orders/{id}` | owner/admin | order detail |
| `POST /api/orders/{id}/cancel` | owner/admin | cancel |
| `GET /api/users` / `POST /api/users` | admin | list / create accounts |
| `PATCH /api/users/{id}/active` | admin | enable / disable access |
| `POST /api/ai/chat` | any | SkyBot |
| `WS /ws?token=JWT` | any | live telemetry stream |

## 11. Troubleshooting

| Problem | Fix |
|---|---|
| `python` not found | Reinstall Python with *Add to PATH*, or use `py -m backend.main` |
| Port 8000 busy (`WinError 10048`) | an old server is still running — close that terminal or: `taskkill /F /IM python.exe` (careful: kills all Python) then re-run `python -m backend.main` |
| Build fails `cannot open output file ... Permission denied` | the running server's drones have `drone_controller.exe` locked — run `scripts\build_firmware.bat` again (it now auto-kills stale drone processes), or stop the server first |
| `.ps1 cannot be loaded` (PowerShell) | `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`, or activate from cmd/Git Bash |
| Firmware says “Python fallback” | compile it (step 4) — or install g++ and rerun the build script |
| Map tiles empty | you're offline, or Google key is invalid → clear `GOOGLE_MAPS_API_KEY` to use OSM |
| Google Maps “failed to load” | check the key has *Maps JavaScript API* enabled and billing-free tier set up; the app auto-falls back to Leaflet |
| `pip install` fails on AI packages | they're optional — `pip install fastapi uvicorn PyJWT python-dotenv pydantic` is enough, SkyBot uses its fallback |
| Order stuck “PENDING” | no drone has enough battery for the round trip yet — wait for charging, or lower `DRONE_SPEED_MPS`/add drones |
| Want a fresh database | stop the server, delete `data/drone_delivery.db`, restart |
| Stopping the server cleanly | press `Ctrl + C` in its terminal (or just close that terminal) — closing VS Code does **not** always stop it |

## 12. Taking it to the real sky 🛫

This project is a *digital twin*: the backend state machine, the C++ PID
loops and the telemetry format mirror a real stack. To fly on hardware you
would keep the whole platform and replace `fleet.py`'s simulator with a
**MAVLink** bridge (`pymavlink`) to a **PX4 / ArduPilot** drone — the C++
controller logic maps almost 1:1 onto PX4's flight modes, and the website
would read real GPS from the vehicle messages. Happy to wire that next.

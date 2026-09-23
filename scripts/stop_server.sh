#!/usr/bin/env bash
# ── SkyCart: stop any running server + drone firmware processes ──
echo "Stopping SkyCart server and drone processes..."

pkill -f "drone_controller" 2>/dev/null || true
pkill -f "backend.main" 2>/dev/null || true

sleep 1
echo "Done. Port 8000 should now be free - start the server again with:"
echo "    python -m backend.main"

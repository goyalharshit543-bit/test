"""Bridge between the Python simulator and the compiled C/C++ flight controller.

The C++ binary (firmware/src/main.cpp) implements the real control maths:
haversine navigation + PID speed and altitude loops. Python streams it one
state line per tick and applies the command it returns.

Input line  (9 whitespace-separated numbers):
    cur_lat cur_lng cur_alt tgt_lat tgt_lng tgt_alt battery max_speed dt
Output line:
    heading speed vspeed alt_cmd [$PXCTL,...*checksum]

If the binary has not been compiled (or crashes), the bridge reports
available=False and the simulator uses a pure-Python controller with the
same behaviour — so the demo always runs, even without a C++ toolchain.
"""
import logging
import subprocess
from typing import Dict, Optional

from backend.config import settings

log = logging.getLogger("firmware_bridge")


class FirmwareBridge:
    def __init__(self):
        self.proc: Optional[subprocess.Popen] = None
        self.available: bool = False
        self.binary: str = ""
        self._start()

    def _start(self):
        candidates = [settings.FIRMWARE_BIN, settings.FIRMWARE_BIN + ".exe"]
        for path in candidates:
            try:
                self.proc = subprocess.Popen(
                    [path],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                )
                self.available = True
                self.binary = path
                log.info("Firmware bridge online: %s", path)
                return
            except FileNotFoundError:
                continue
            except OSError as exc:
                log.warning("Could not launch firmware binary %s: %s", path, exc)
        self.proc = None
        self.available = False
        log.info(
            "Firmware binary not found — using built-in Python controller. "
            "Compile it with `make -C firmware` (or scripts/build_firmware.*) "
            "to run the real C/C++ flight controller."
        )

    def step(
        self,
        cur_lat: float, cur_lng: float, cur_alt: float,
        tgt_lat: float, tgt_lng: float, tgt_alt: float,
        battery: float, max_speed: float, dt: float,
    ) -> Dict[str, float]:
        """Run one control-loop iteration. Returns heading/speed/vspeed/alt_cmd."""
        if not self.available or self.proc is None:
            raise RuntimeError("firmware bridge unavailable")
        line = (
            f"{cur_lat:.7f} {cur_lng:.7f} {cur_alt:.2f} "
            f"{tgt_lat:.7f} {tgt_lng:.7f} {tgt_alt:.2f} "
            f"{battery:.1f} {max_speed:.2f} {dt:.3f}\n"
        )
        try:
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
            out = self.proc.stdout.readline()
            if not out:
                raise RuntimeError("firmware process closed stdout")
            parts = out.split()
            if len(parts) >= 4 and parts[0] != "ERR":
                return {
                    "heading": float(parts[0]),
                    "speed": float(parts[1]),
                    "vspeed": float(parts[2]),
                    "alt_cmd": float(parts[3]),
                    "telemetry": parts[4] if len(parts) > 4 else "",
                }
            raise ValueError(f"unexpected firmware output: {out!r}")
        except (BrokenPipeError, ValueError, RuntimeError):
            # Firmware died mid-flight — kill it and let the caller fall back.
            self.kill()
            self.available = False
            raise

    def kill(self):
        if self.proc:
            try:
                self.proc.stdin.close()
            except Exception:
                pass
            try:
                self.proc.kill()
            except Exception:
                pass
            self.proc = None

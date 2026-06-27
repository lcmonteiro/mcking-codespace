#!/usr/bin/env python3
"""
cyberdash.py — Cyberpunk Terminal Dashboard
============================================
Matrix-style rain meets system stats + glitch art.
Pure stdlib, no dependencies.
"""

import json
import logging
import math
import os
import random
import shutil
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Windows UTF-8 fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ====================================================================================================
# ANSI Helpers
# ====================================================================================================


def csi(*seq: int) -> str:
    """Return CSI escape sequence."""
    return f"\033[{';'.join(str(s) for s in seq)}m"


def rgb(r: int, g: int, b: int) -> str:
    """ANSI truecolor foreground."""
    return csi(38, 2, r, g, b)


def bg_rgb(r: int, g: int, b: int) -> str:
    """ANSI truecolor background."""
    return csi(48, 2, r, g, b)


BOLD       : str = csi(1)
DIM        : str = csi(2)
RESET      : str = csi(0)
CLS        : str = "\033[2J"
HOME       : str = "\033[H"
CLEAR_LINE : str = "\033[2K"


# ====================================================================================================
# Palette — Synthwave Sunset
# ====================================================================================================

PALETTE: List[Tuple[int, int, int]] = [
    (255, 50, 100),     # hot pink
    (255, 100, 50),     # orange
    (255, 180, 50),     # gold
    (100, 255, 100),    # neon green
    (50, 200, 255),     # cyan
    (180, 80, 255),     # purple
    (255, 50, 180),     # magenta
    (80, 255, 200),     # mint
]


def palette_color(t: float) -> Tuple[int, int, int]:
    """Interpolate palette by *t* ∈ [0,1]."""
    idx = t * (len(PALETTE) - 1)
    i = int(idx)
    f = idx - i
    if i >= len(PALETTE) - 1:
        return PALETTE[-1]
    r = int(PALETTE[i][0] + (PALETTE[i + 1][0] - PALETTE[i][0]) * f)
    g = int(PALETTE[i][1] + (PALETTE[i + 1][1] - PALETTE[i][1]) * f)
    b = int(PALETTE[i][2] + (PALETTE[i + 1][2] - PALETTE[i][2]) * f)
    return (r, g, b)


# ====================================================================================================
# Matrix Rain Layer
# ====================================================================================================


class MatrixRain:
    """Matrix-style rain column effect."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.drops: List[Dict] = []
        self.reset()

    def reset(self) -> None:
        """Reset all drops to random starting positions."""
        self.drops = []
        cols = max(1, self.width // 2)
        for _ in range(cols):
            self.drops.append({
                "x": random.randint(0, self.width - 1),
                "y": random.randint(-self.height, 0),
                "speed": random.uniform(0.2, 0.8),
                "length": random.randint(3, 12),
                "chars": [random.choice("01アイウエオカキクケコサシスセソ") for _ in range(20)],
                "bright": random.random() > 0.85,
            })

    def update(self) -> None:
        """Advance drops by one step."""
        for d in self.drops:
            d["y"] += d["speed"]
            if d["y"] > self.height + d["length"]:
                d["y"] = random.randint(-self.height, -5)
                d["x"] = random.randint(0, self.width - 1)
                d["speed"] = random.uniform(0.2, 0.8)

    def draw(self, buf: List[Tuple[int, int, int]], overlay_mask: List[float]) -> None:
        """Draw rain into the pixel *buf*, masked by *overlay_mask*."""
        for d in self.drops:
            for i in range(d["length"]):
                y = int(d["y"] - i)
                if 0 <= y < self.height:
                    idx = (y * self.width) + d["x"]
                    if idx < len(overlay_mask) and overlay_mask[idx] > 0.3:
                        continue
                    ch = d["chars"][i % len(d["chars"])]
                    if i == 0:
                        b = 255 if d["bright"] else 200
                        buf[idx] = (b, b, b)
                    elif i < 3:
                        buf[idx] = (100, 255, 100)
                    else:
                        alpha = max(0, 30 - i * 3)
                        buf[idx] = (0, alpha, 0)


# ====================================================================================================
# Glitch / Scanlines
# ====================================================================================================


class GlitchOverlay:
    """Glitch and scanline overlay effect."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.glitch_lines: List[Tuple[int, int, int, str]] = []
        self.flicker = 0.0

    def update(self, dt: float) -> None:
        """Advance glitch animation by *dt* seconds."""
        self.flicker += dt
        self.glitch_lines = []
        if random.random() < 0.3:
            count = random.randint(1, 4)
            for _ in range(count):
                y = random.randint(0, self.height - 1)
                w = random.randint(3, 20)
                x = random.randint(0, self.width - w - 1)
                self.glitch_lines.append((
                    y, x, w,
                    random.choice(["*=#%@&!", "▀▄█▓▒░", "╱╲╳╵╶╷╸", "01!01!", "SCAN", "ERR"]),
                ))

    def apply(self, buf: List[Tuple[int, int, int]]) -> None:
        """Apply glitch effects to pixel *buf*."""
        screen_w = self.width
        for y, x, w, chars in self.glitch_lines:
            for i in range(w):
                idx = y * screen_w + x + i
                if idx < len(buf):
                    ch = chars[i % len(chars)]
                    if ch == ' ':
                        buf[idx] = (0, 0, 0)
                    else:
                        buf[idx] = (255, 0, 80)

        # scanline flicker
        if math.sin(self.flicker * 8) > 0.7:
            for y in range(0, self.height, 2):
                for x in range(screen_w):
                    idx = y * screen_w + x
                    if idx < len(buf):
                        r0, g0, b0 = buf[idx]
                        buf[idx] = (int(r0 * 0.7), int(g0 * 0.7), int(b0 * 0.7))


# ====================================================================================================
# System Info
# ====================================================================================================


def get_cpu_usage() -> int:
    """Return current CPU usage percentage."""
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(
                "wmic cpu get loadpercentage", shell=True, timeout=2,
                stderr=subprocess.DEVNULL
            ).decode("utf-8", errors="replace").strip().split("\n")
            return int(out[-1].strip()) if len(out) > 1 else 0
        else:
            out = subprocess.check_output(
                "top -bn1 | grep 'Cpu(s)'", shell=True, timeout=2
            ).decode()
            return float(out.split()[1].replace("%", ""))
    except Exception:
        import psutil  # type: ignore
        try:
            return int(psutil.cpu_percent(interval=0.1))
        except ImportError:
            return random.randint(10, 60)


def get_memory_usage() -> Tuple[float, float, float]:
    """Return (percent, used_mb, total_mb)."""
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(
                "wmic os get TotalVisibleMemorySize,FreePhysicalMemory /format:csv",
                shell=True, timeout=2, stderr=subprocess.DEVNULL
            ).decode("utf-8", errors="replace").strip().split("\n")
            if len(out) > 1:
                parts = out[-1].split(",")
                if len(parts) >= 3:
                    total = int(parts[-2])
                    free = int(parts[-1])
                    used = total - free
                    return (used / total) * 100, used / 1024, total / 1024
        raise Exception("fallback")
    except Exception:
        import psutil  # type: ignore
        try:
            mem = psutil.virtual_memory()
            return mem.percent, mem.used / (1024 * 1024), mem.total / (1024 * 1024)
        except ImportError:
            return random.randint(30, 80), 0.0, 0.0


# ====================================================================================================
# Renderer
# ====================================================================================================


class Renderer:
    """Cyberpunk dashboard renderer combining rain, glitch, and system stats."""

    def __init__(self) -> None:
        self.rain: Optional[MatrixRain] = None
        self.glitch: Optional[GlitchOverlay] = None
        self.frame_buf: List[Tuple[int, int, int]] = []
        self.last_time: float = time.time()
        self.elapsed: float = 0.0
        self.terminal_w: int = 80
        self.terminal_h: int = 24

    def init(self) -> None:
        """Initialise renderer to current terminal size."""
        self.update_terminal_size()
        self.rain = MatrixRain(self.terminal_w, self.terminal_h)
        self.glitch = GlitchOverlay(self.terminal_w, self.terminal_h)
        self.frame_buf = [(0, 0, 0)] * (self.terminal_w * self.terminal_h)
        print(CLS, end="", flush=False)

    def update_terminal_size(self) -> None:
        """Detect and store current terminal dimensions."""
        try:
            sz = shutil.get_terminal_size((80, 24))
            self.terminal_w = sz.columns
            self.terminal_h = sz.lines
        except Exception:
            self.terminal_w = 80
            self.terminal_h = 24

    def render_frame(self) -> None:
        """Build and flush one frame to the terminal."""
        now = time.time()
        dt = now - self.last_time
        self.last_time = now
        self.elapsed += dt
        w, h = self.terminal_w, self.terminal_h

        buf: List[Tuple[int, int, int]] = [(0, 0, 0)] * (w * h)

        # overlay mask for center text area
        overlay_mask: List[float] = [0.0] * (w * h)
        text_box_y = h // 3
        text_box_h = h // 3 + 3
        for y in range(text_box_y, min(text_box_y + text_box_h, h)):
            for x in range(w):
                overlay_mask[y * w + x] = 0.8

        if self.rain is not None:
            self.rain.update()
            self.rain.draw(buf, overlay_mask)

        if self.glitch is not None:
            self.glitch.update(dt)
            self.glitch.apply(buf)

        out: List[str] = [HOME]

        cpu = get_cpu_usage()
        try:
            mem_pct, mem_used, mem_total = get_memory_usage()
        except Exception:
            mem_pct, mem_used, mem_total = 0.0, 0.0, 0.0

        t = (math.sin(self.elapsed * 0.5) + 1) / 2
        header_color = palette_color(t)

        header = (
            f"{rgb(*header_color)}{BOLD}"
            f"  ╔══╗╔══╗╔╗──╔══╗╔══╗╔══╗╔══╗╔═══╗  "
            f"{RESET}\n"
        )
        header += (
            f"{rgb(*header_color)}{BOLD}"
            f"  ╚╗╔╝║╔╗║║║──║╔═╝║╔═╝║╔╗║║╔╗║║╔══╝  "
            f"{RESET}\n"
        )
        header += (
            f"{rgb(*header_color)}{BOLD}"
            f"  ─║║─║║║║║║──║╚═╗║╚═╗║║║║║╚╝║║╚══╗  "
            f"{RESET}\n"
        )
        header += (
            f"{rgb(*header_color)}{BOLD}"
            f"  ─║║─║║║║║║──║╔═╝║╔═╝║║║║║╔╗║║╔══╝  "
            f"{RESET}\n"
        )
        header += (
            f"{rgb(*header_color)}{BOLD}"
            f"  ╔╝╚╗║╚╝║║╚═╗║║──║║──║╚╝║║║║║║╚══╗  "
            f"{RESET}\n"
        )
        header += (
            f"{rgb(*header_color)}{BOLD}"
            f"  ╚══╝╚══╝╚══╝╚╝──╚╝──╚══╝╚╝╚╝╚═══╝  "
            f"{RESET}\n"
        )

        out.append(header)

        cpu_color = palette_color(cpu / 100)
        mem_color = palette_color(mem_pct / 100)

        status = (
            f"{DIM}┌{'─' * (w - 4)}┐{RESET}\n"
            f"{rgb(*cpu_color)}{BOLD} CPU: {cpu:3d}% {RESET} "
            f"{rgb(*mem_color)}{BOLD} MEM: {mem_pct:5.1f}% "
            f"({mem_used:.0f}/{mem_total:.0f} MB){RESET} "
            f"{rgb(100, 200, 255)}⏱ {self.elapsed:.0f}s{RESET} "
            f"{DIM}{time.strftime('%H:%M:%S')}{RESET}\n"
            f"{DIM}└{'─' * (w - 4)}┘{RESET}\n"
        )
        out.append(status)

        scan_y = int((math.sin(self.elapsed * 2.0) + 1) / 2 * (h - 8)) + 6
        for y in range(6, h - 1):
            if y == scan_y:
                scan_chars = "".join(random.choice("01") for _ in range(w))
                out.append(f"{rgb(0, 255, 0)}{DIM}{scan_chars}{RESET}\n")
            else:
                line_buf = ""
                for x in range(w):
                    idx = y * w + x
                    if idx < len(buf):
                        r0, g0, b0 = buf[idx]
                        if (r0, g0, b0) == (0, 0, 0):
                            line_buf += " "
                        else:
                            ch = random.choice("░▒▓█")
                            line_buf += f"{rgb(r0, g0, b0)}{ch}{RESET}"
                if line_buf.strip():
                    out.append(line_buf + "\n")

        print("".join(out), end="", flush=True)

    def run(self) -> None:
        """Run the dashboard animation loop."""
        self.init()
        try:
            while True:
                self.update_terminal_size()
                if self.rain is not None and (
                    self.terminal_w != self.rain.width or self.terminal_h != self.rain.height
                ):
                    self.rain = MatrixRain(self.terminal_w, self.terminal_h)
                    self.glitch = GlitchOverlay(self.terminal_w, self.terminal_h)
                self.render_frame()
                time.sleep(0.1)
        except KeyboardInterrupt:
            print(f"{RESET}{CLS}{HOME}", end="", flush=True)
            print("🛑 Cyberdash terminated.")


# ====================================================================================================
# Entry Point
# ====================================================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    renderer = Renderer()
    renderer.run()

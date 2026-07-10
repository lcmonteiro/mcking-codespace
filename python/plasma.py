#!/usr/bin/env python3
"""
plasma.py — Terminal Plasma Effect 🔮
=======================================
Classic demoscene plasma rendered to ANSI truecolor terminal.

Combines multiple sine-wave layers to create flowing, organic
colour patterns. Resize-aware, interactive key controls.

Usage:
    python plasma.py

Controls:
    q/ESC  — quit
    1-5    — palette presets
    +/-    — speed up / slow down
    r      — reset to defaults
    SPACE  — pause/resume
    c      — cycle palette continuously

Palettes:
    1 — Lava (red/orange/yellow)
    2 — Ocean (blue/cyan/teal)
    3 — Neon (magenta/pink/blue)
    4 — Forest (green/yellow/brown)
    5 — Ice (cyan/white/purple)

Zero external dependencies. Pure stdlib.
ANSI truecolor required (modern terminals only).

Author: Mcking (AI assistant do Luis Monteiro)
Data: 2026-07-10
"""

import math
import os
import random
import sys
import time
from typing import Callable, List, Optional, Tuple

# ── Windows UTF-8 fix ──────────────────────────────────────────────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
elif hasattr(sys.stdout, "buffer"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── ANSI helpers ───────────────────────────────────────────────────────────────────────────────────
RESET   = "\033[0m"
HOME    = "\033[H"
HIDE    = "\033[?25l"
SHOW    = "\033[?25h"
CLEAR   = "\033[2J"
SAVE    = "\033[s"
RESTORE = "\033[u"
BOLD    = "\033[1m"

def rgb_fg(r: int, g: int, b: int) -> str:
    """ANSI truecolor foreground."""
    return f"\033[38;2;{r};{g};{b}m"

def rgb_bg(r: int, g: int, b: int) -> str:
    """ANSI truecolor background."""
    return f"\033[48;2;{r};{g};{b}m"

def lerp_color(c1: Tuple[int, int, int], c2: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    """Linearly interpolate between two colours."""
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )

# ── Palettes ───────────────────────────────────────────────────────────────────────────────────────
# Each palette is a list of colour stops; the plasma value t ∈ [0,1] maps across them.

Palette = List[Tuple[int, int, int]]

PALETTES: List[Tuple[str, Palette]] = [
    ("Lava", [
        (0, 0, 0),       # black
        (80, 0, 0),      # dark red
        (255, 30, 0),    # red
        (255, 120, 0),   # orange
        (255, 200, 50),  # yellow
        (255, 120, 0),   # orange
        (180, 30, 0),    # dark orange
        (40, 0, 0),      # near-black
    ]),
    ("Ocean", [
        (0, 0, 20),       # deep blue-black
        (0, 30, 80),      # dark blue
        (0, 80, 180),     # blue
        (0, 160, 220),    # cyan-blue
        (40, 200, 200),   # teal
        (0, 120, 180),    # ocean blue
        (0, 30, 80),      # dark blue
        (0, 0, 20),       # deep
    ]),
    ("Neon", [
        (10, 0, 20),      # dark purple
        (80, 0, 120),     # purple
        (200, 0, 150),    # magenta
        (255, 50, 200),   # pink
        (100, 200, 255),  # cyan
        (50, 50, 255),    # blue
        (80, 0, 120),     # purple
        (10, 0, 20),      # dark
    ]),
    ("Forest", [
        (5, 15, 0),       # dark green-black
        (10, 50, 5),      # deep green
        (30, 100, 20),    # forest green
        (80, 160, 40),    # green
        (180, 200, 60),   # yellow-green
        (120, 140, 30),   # olive
        (30, 80, 10),     # dark green
        (5, 15, 0),       # deep
    ]),
    ("Ice", [
        (5, 0, 20),       # dark purple-black
        (20, 10, 60),     # dark indigo
        (40, 60, 140),    # purple-blue
        (100, 180, 220),  # ice blue
        (220, 240, 255),  # white-blue
        (140, 200, 240),  # light blue
        (50, 80, 160),    # medium blue
        (10, 5, 30),      # dark
    ]),
]

# ── Sine-wave plasma ──────────────────────────────────────────────────────────────────────────────

def make_plasma_table(w: int, h: int, t: float, wave_params: List[Tuple[float, float, float, float]]) -> List[float]:
    """
    Compute plasma value for every cell using layered sine waves.

    Each wave param: (angle_degrees, frequency, speed, offset)
    - angle: direction of wave propagation
    - frequency: spatial frequency
    - speed: how fast wave moves over time
    - offset: phase offset
    """
    n_waves = len(wave_params)
    table = [0.0] * (w * h)

    # Precompute wave components for speed
    sin_table = [0.0] * (w * h * n_waves)

    for wi, (angle_deg, freq, speed, offset) in enumerate(wave_params):
        rad = math.radians(angle_deg)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        ox = len(table)
        for yi in range(h):
            base = yi * w + wi * w * h
            for xi in range(w):
                dist = xi * cos_a + yi * sin_a
                val = math.sin(dist * freq + t * speed + offset)
                sin_table[base + xi] = val

    for yi in range(h):
        for xi in range(w):
            total = 0.0
            for wi in range(n_waves):
                total += sin_table[yi * w + xi + wi * w * h]
            # Normalize to roughly [0, 1]
            norm = (total / n_waves + 1.0) * 0.5
            table[yi * w + xi] = max(0.0, min(1.0, norm))

    return table


def sample_palette(palette: Palette, t: float) -> Tuple[int, int, int]:
    """Map t ∈ [0,1] through a colour-stop palette."""
    if t <= 0.0:
        return palette[0]
    if t >= 1.0:
        return palette[-1]

    n = len(palette) - 1
    idx = t * n
    lo = int(idx)
    hi = min(lo + 1, n)
    frac = idx - lo
    return lerp_color(palette[lo], palette[hi], frac)


def render_frame(w: int, h: int, plasma: List[float], palette: Palette) -> str:
    """Build full ANSI frame string from plasma table."""
    parts: List[str] = [HOME]
    for yi in range(h):
        for xi in range(w):
            val = plasma[yi * w + xi]
            r, g, b = sample_palette(palette, val)
            # Use background colour blocks for solid fill
            parts.append(rgb_bg(r, g, b))
            parts.append(" ")
        parts.append(RESET)
        if yi < h - 1:
            parts.append("\n")
    parts.append(RESET)
    return "".join(parts)


# ── Plasma class ───────────────────────────────────────────────────────────────────────────────────

class Plasma:
    """Interactive terminal plasma effect."""

    def __init__(self):
        self.W, self.H = self._get_size()
        self.palette_idx = 0
        self.speed = 1.0
        self.time = 0.0
        self.paused = False
        self.auto_cycle = False
        self.cycle_timer = 0.0
        self.running = True

        # Five wave layers with different directions, frequencies, speeds
        self.wave_params: List[Tuple[float, float, float, float]] = [
            (0.0,   0.04,  1.2, 0.0),     # horizontal
            (60.0,  0.06,  1.8, 1.5),     # diagonal
            (120.0, 0.03,  0.9, 3.0),     # diagonal opposite
            (90.0,  0.05,  1.5, 0.8),     # vertical
            (30.0,  0.07,  2.0, 2.2),     # fast diagonal
        ]

    @staticmethod
    def _get_size() -> Tuple[int, int]:
        """Get terminal size, fallback 80x24."""
        try:
            import shutil
            w, h = shutil.get_terminal_size((80, 24))
            # Leave one row for status bar
            return w, max(h - 1, 10)
        except Exception:
            return 80, 24

    def _read_key(self) -> Optional[str]:
        """Read one keypress without blocking. Returns None if no key."""
        try:
            if sys.platform == "win32":
                import msvcrt
                if msvcrt.kbhit():
                    k = msvcrt.getwch()
                    if k == '\xe0':
                        k2 = msvcrt.getwch()
                        return None  # arrow keys, ignore
                    return k
            else:
                import select
                import termios
                import tty
                fd = sys.stdin.fileno()
                if select.select([fd], [], [], 0.0)[0]:
                    old = termios.tcgetattr(fd)
                    try:
                        tty.setraw(fd)
                        ch = sys.stdin.read(1)
                        if ch == '\x1b':
                            # Possibly escape sequence
                            rest = sys.stdin.read(2) if select.select([fd], [], [], 0.005)[0] else ''
                            if rest:
                                return None  # arrow/escape sequence
                            return 'q'  # ESC key = quit
                        return ch
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old)
            return None
        except (ImportError, AttributeError, OSError):
            return None

    def handle_key(self, key: str) -> None:
        """Process a single keypress."""
        if key in ('q', 'Q', '\x1b'):
            self.running = False
        elif key == ' ':
            self.paused = not self.paused
        elif key == '+':
            self.speed = min(self.speed * 1.3, 5.0)
        elif key == '-':
            self.speed = max(self.speed / 1.3, 0.1)
        elif key == 'r' or key == 'R':
            self.speed = 1.0
            self.paused = False
            self.auto_cycle = False
            self.palette_idx = 0
        elif key == 'c' or key == 'C':
            self.auto_cycle = not self.auto_cycle
        elif key in ('1', '2', '3', '4', '5'):
            idx = int(key) - 1
            if idx < len(PALETTES):
                self.palette_idx = idx
                self.auto_cycle = False

    def status_bar(self) -> str:
        """Build status line."""
        name, _ = PALETTES[self.palette_idx]
        parts = [
            BOLD,
            " 🔮 Plasma | ",
            f"Palette: {name}",
            f" | Speed: {self.speed:.1f}x",
        ]
        if self.paused:
            parts.append(" | ⏸ PAUSED")
        if self.auto_cycle:
            parts.append(" | 🔄 Auto-cycle")
        parts.append(" | [1-5] palette  [+/-] speed  [c] cycle  [SPC] pause  [q] quit")
        parts.append(RESET)
        return "".join(parts)

    def run(self) -> None:
        """Main loop."""
        sys.stdout.write(HIDE + CLEAR)
        sys.stdout.flush()

        last_frame = time.perf_counter()
        target_fps = 30
        frame_time = 1.0 / target_fps

        try:
            while self.running:
                # Resize check
                new_w, new_h = self._get_size()
                if new_w != self.W or new_h != self.H:
                    self.W, self.H = new_w, new_h

                # Handle keys
                while True:
                    k = self._read_key()
                    if k is None:
                        break
                    self.handle_key(k)

                # Update
                now = time.perf_counter()
                dt = now - last_frame
                last_frame = now
                dt = min(dt, 0.1)

                if not self.paused:
                    self.time += dt * self.speed

                if self.auto_cycle:
                    self.cycle_timer += dt
                    if self.cycle_timer > 5.0:
                        self.cycle_timer = 0.0
                        self.palette_idx = (self.palette_idx + 1) % len(PALETTES)

                # Render plasma
                if self.W > 0 and self.H > 0:
                    plasma = make_plasma_table(self.W, self.H, self.time, self.wave_params)
                    frame = render_frame(self.W, self.H, plasma, PALETTES[self.palette_idx][1])
                    status = self.status_bar()
                    sys.stdout.write(frame + RESET + "\n" + status)
                    sys.stdout.flush()

                # Frame rate control
                elapsed = time.perf_counter() - now
                sleep = frame_time - elapsed
                if sleep > 0:
                    time.sleep(sleep)

        except KeyboardInterrupt:
            pass
        finally:
            sys.stdout.write(SHOW + RESET + HOME + CLEAR)
            sys.stdout.flush()
            print("\nPlasma terminado. ✨")


# ── Entry point ────────────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Run the terminal plasma effect."""
    plasma = Plasma()
    plasma.run()


if __name__ == "__main__":
    main()

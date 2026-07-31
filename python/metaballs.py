#!/usr/bin/env python3
"""
metaballs.py — Terminal Metaballs 🧫
=====================================
Classic demoscene metaballs rendered to ANSI truecolor terminal.

Blinn's blobby model: every blob contributes r²/d² to a scalar field,
and the isosurface f = 1 defines the blob boundary. Rendered with the
half-block trick (each cell draws ▀ with fg = top sample, bg = bottom
sample) for 2× vertical resolution, plus optional phosphor trails and
contour-line mode.

Usage:
    python metaballs.py

Controls:
    q/ESC  — quit
    1-5    — palette presets
    +/-    — add / remove a blob
    SPACE  — pause/resume
    c      — cycle palette continuously
    t      — toggle phosphor trails
    f      — toggle field-lines mode
    r      — reset blobs to defaults

Palettes:
    1 — Lava (red/orange/yellow)
    2 — Ocean (blue/cyan/teal)
    3 — Neon (magenta/pink/blue)
    4 — Forest (green/yellow/brown)
    5 — Ice (cyan/white/purple)

Zero external dependencies. Pure stdlib.
ANSI truecolor required (modern terminals only).

Author: Mcking (AI assistant do Luis Monteiro)
Data: 2026-07-31
"""

import math
import random
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

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
BOLD    = "\033[1m"

# ASCII ramp for field-lines mode (dark → bright)
RAMP = " .:-=+*#%@"


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
# Each palette is a list of colour stops; the field value t ∈ [0,1] maps across them,
# dark at the blob edge → bright at the core.

Palette = List[Tuple[int, int, int]]

PALETTES: List[Tuple[str, Palette]] = [
    ("Lava", [
        (10, 0, 0),       # near-black
        (90, 10, 0),      # dark red
        (255, 40, 0),     # red
        (255, 130, 0),    # orange
        (255, 210, 60),   # yellow
        (255, 250, 200),  # white-hot
    ]),
    ("Ocean", [
        (0, 5, 25),       # deep blue-black
        (0, 40, 100),     # dark blue
        (0, 90, 190),     # blue
        (0, 170, 230),    # cyan-blue
        (60, 220, 210),   # teal
        (220, 250, 255),  # foam white
    ]),
    ("Neon", [
        (15, 0, 25),      # dark purple
        (90, 0, 130),     # purple
        (210, 0, 160),    # magenta
        (255, 60, 210),   # pink
        (120, 210, 255),  # cyan
        (240, 240, 255),  # cold white
    ]),
    ("Forest", [
        (5, 12, 0),       # dark green-black
        (15, 55, 10),     # deep green
        (35, 110, 25),    # forest green
        (90, 170, 45),    # green
        (190, 210, 70),   # yellow-green
        (240, 250, 200),  # pale
    ]),
    ("Ice", [
        (5, 10, 25),      # midnight
        (20, 40, 80),     # dark blue
        (60, 120, 190),   # steel blue
        (140, 200, 240),  # ice blue
        (220, 245, 255),  # pale cyan
        (255, 255, 255),  # white
    ]),
]

TRAIL_DECAY = 0.90     # phosphor persistence per frame
GLOW_FALLOFF = 0.35    # outer-glow strength at the isosurface
GLOW_DECAY   = 4.0     # how fast the rim glow fades with distance


# ── Blob ───────────────────────────────────────────────────────────────────────────────────────────

@dataclass
class Blob:
    """A single metaball: position, velocity and radius weight (in sample units)."""
    x  : float
    y  : float
    vx : float
    vy : float
    r  : float


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


# ── Metaballs ──────────────────────────────────────────────────────────────────────────────────────

class Metaballs:
    """Interactive terminal metaballs effect."""

    def __init__(self) -> None:
        self.w, self.h = self._get_size()
        self.palette_idx : int = 0
        self.time        : float = 0.0
        self.paused      : bool = False
        self.auto_cycle  : bool = False
        self.trails      : bool = True
        self.lines_mode  : bool = False
        self.cycle_timer : float = 0.0
        self.running     : bool = True
        self.last_fps    : float = 60.0
        self.blobs       : List[Blob] = []
        self.glow        : List[float] = []
        self._reset_blobs()

    # === Setup =====================================================================================

    @staticmethod
    def _get_size() -> Tuple[int, int]:
        """Get terminal size, fallback 80x24."""
        try:
            import shutil
            w, h = shutil.get_terminal_size((80, 24))
            # Leave one row for the status bar
            return w, max(h - 1, 10)
        except Exception:
            return 80, 24

    def _reset_blobs(self) -> None:
        """Recreate the blob field with random positions, velocities and sizes."""
        w, h = self.w, self.h * 2
        rng = random.Random()
        self.blobs = [
            Blob(
                x  = rng.uniform(w * 0.15, w * 0.85),
                y  = rng.uniform(h * 0.15, h * 0.85),
                vx = rng.uniform(-0.8, 0.8),
                vy = rng.uniform(-1.6, 1.6),
                r  = rng.uniform(2.4, 4.2),
            )
            for _ in range(5)
        ]
        self.glow = [0.0] * (w * h)

    def _add_blob(self) -> None:
        """Add one more blob at a random free position."""
        rng = random.Random()
        self.blobs.append(Blob(
            x  = rng.uniform(2, self.w - 2),
            y  = rng.uniform(2, self.h * 2 - 2),
            vx = rng.uniform(-0.8, 0.8),
            vy = rng.uniform(-1.6, 1.6),
            r  = rng.uniform(2.4, 4.2),
        ))

    # === Input =====================================================================================

    def _read_key(self) -> Optional[str]:
        """Read one keypress without blocking. Returns None if no key."""
        try:
            if sys.platform == "win32":
                import msvcrt
                if msvcrt.kbhit():
                    k = msvcrt.getwch()
                    if k == '\xe0':
                        msvcrt.getwch()  # arrow keys, ignore
                        return None
                    return k
            else:
                import select
                import termios
                import tty
                fd = sys.stdin.fileno()
                if select.select([fd], [], [], 0.0)[0]:
                    try:
                        old = termios.tcgetattr(fd)
                        try:
                            tty.setraw(fd)
                            ch = sys.stdin.read(1)
                            if ch == '\x1b':
                                rest = sys.stdin.read(2) if select.select([fd], [], [], 0.005)[0] else ''
                                if rest:
                                    return None  # arrow/escape sequence
                                return 'q'  # ESC key = quit
                            return ch
                        finally:
                            termios.tcsetattr(fd, termios.TCSADRAIN, old)
                    except termios.error:
                        return None  # not a TTY
                return None
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
            self._add_blob()
        elif key == '-':
            if len(self.blobs) > 2:
                self.blobs.pop()
        elif key == 'r' or key == 'R':
            self._reset_blobs()
            self.auto_cycle = False
            self.lines_mode = False
        elif key == 'c' or key == 'C':
            self.auto_cycle = not self.auto_cycle
        elif key == 't' or key == 'T':
            self.trails = not self.trails
            if not self.trails:
                self.glow = [0.0] * len(self.glow)
        elif key == 'f' or key == 'F':
            self.lines_mode = not self.lines_mode
        elif key in '12345':
            self.palette_idx = int(key) - 1
            self.auto_cycle = False

    # === Rendering =================================================================================

    def _step(self, dt: float) -> None:
        """Advance blob physics by *dt* seconds."""
        w, h = self.w, self.h * 2
        for b in self.blobs:
            b.x += b.vx * dt
            b.y += b.vy * dt
            if b.x < b.r or b.x > w - b.r:
                b.vx = -b.vx
                b.x = max(b.r, min(w - b.r, b.x))
            if b.y < b.r or b.y > h - b.r:
                b.vy = -b.vy
                b.y = max(b.r, min(h - b.r, b.y))

    def _render(self) -> str:
        """Build the full ANSI frame string."""
        w, h = self.w, self.h
        sh = h * 2                   # sample space (2 samples per cell, vertical)
        palette = PALETTES[self.palette_idx][1]
        blobs = self.blobs
        dec = TRAIL_DECAY if self.trails else 0.0

        # ── pass 1: field → per-sample brightness ──
        vals = [0.0] * (w * sh)
        for yi in range(sh):
            for xi in range(w):
                f = 0.0
                for b in blobs:
                    dx = b.x - xi
                    dy = (b.y - yi) * 0.5
                    d2 = dx * dx + dy * dy + 0.01
                    f += b.r * b.r / d2

                idx = yi * w + xi
                if f >= 1.0:
                    t = 1.0 - 1.0 / f          # 0 at isosurface → 1 at core
                else:
                    # thin rim glow just outside the surface, fading exponentially
                    t = GLOW_FALLOFF * math.exp(-GLOW_DECAY * (1.0 - f))

                if self.trails:
                    self.glow[idx] = max(self.glow[idx] * dec, t)
                    t = self.glow[idx]
                vals[idx] = t

        # ── pass 2: combine top/bottom samples into half-block cells ──
        parts: List[str] = [HOME]
        if self.lines_mode:
            ramp_n = len(RAMP) - 1
            for yi in range(h):
                for xi in range(w):
                    t_cell = (vals[(yi * 2) * w + xi] + vals[(yi * 2 + 1) * w + xi]) * 0.5
                    ch = RAMP[min(int(t_cell * ramp_n), ramp_n)]
                    cr, cg, cb = sample_palette(palette, t_cell)
                    parts.append(rgb_fg(cr, cg, cb) + ch)
                parts.append(RESET)
                parts.append("\n")
        else:
            for yi in range(h):
                for xi in range(w):
                    t_t = vals[(yi * 2) * w + xi]
                    t_b = vals[(yi * 2 + 1) * w + xi]
                    cr, cg, cb = sample_palette(palette, t_t)
                    dr, dg, db = sample_palette(palette, t_b)
                    parts.append(rgb_fg(cr, cg, cb) + rgb_bg(dr, dg, db) + "▀")
                parts.append(RESET)
                parts.append("\n")

        # ── status bar ──
        pal_name = PALETTES[self.palette_idx][0]
        mode = "lines" if self.lines_mode else "solid"
        trail = "on" if self.trails else "off"
        parts.append(RESET + BOLD)
        parts.append(
            f"🧫 METABALLS  {pal_name}  {len(blobs)} blobs  {mode}  trails:{trail}  "
            f"{self.last_fps:4.0f} fps"
        )
        parts.append(RESET)
        parts.append(
            "  [1-5]pal [c]cycle [+]add [-]rem [t]trails [f]lines [space]pause [r]reset [q]quit"
        )
        return "".join(parts)

    # === Main loop =================================================================================

    def run(self) -> None:
        """Run the interactive loop until quit."""
        sys.stdout.write(CLEAR + HIDE)
        frame_time = 1.0 / 60.0
        prev = time.monotonic()

        while self.running:
            now = time.monotonic()
            dt = min(now - prev, 0.1)
            prev = now

            # resize-aware
            new_w, new_h = self._get_size()
            if (new_w, new_h) != (self.w, self.h):
                self.w, self.h = new_w, new_h
                self.glow = [0.0] * (self.w * self.h * 2)

            key = self._read_key()
            if key is not None:
                self.handle_key(key)

            if not self.paused:
                self.time += dt
                self._step(dt)

            if self.auto_cycle:
                self.cycle_timer += dt
                if self.cycle_timer >= 5.0:
                    self.cycle_timer = 0.0
                    self.palette_idx = (self.palette_idx + 1) % len(PALETTES)

            sys.stdout.write(self._render())
            sys.stdout.flush()

            self.last_fps = 0.9 * self.last_fps + 0.1 * (1.0 / max(dt, 1e-4))
            elapsed = time.monotonic() - now
            if elapsed < frame_time:
                time.sleep(frame_time - elapsed)

        sys.stdout.write(SHOW + RESET + "\n")


def main() -> None:
    """Entry point."""
    try:
        Metaballs().run()
    except KeyboardInterrupt:
        sys.stdout.write(SHOW + RESET + "\n")


if __name__ == "__main__":
    main()

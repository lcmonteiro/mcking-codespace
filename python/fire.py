#!/usr/bin/env python3
"""
fire.py — Terminal Fire 🔥
===========================
Classic demoscene fire rendered to ANSI truecolor terminal.

The old-school Doom-style algorithm: a 2× vertical-resolution heat grid
where every cell becomes the average of the four cells below it, scaled
by a cooling factor. The bottom rows are re-seeded with random fuel, and
the heat rises into natural, flickering flames. Rendered with the
half-block trick (each cell draws ▀ with fg = bottom sample, bg = top
sample) for 2× vertical resolution.

Usage:
    python fire.py [--wind N] [--fuel N] [--palette N] [--no-embers]
                   [--once [FRAMES]]

Controls:
    q/ESC    — quit
    1-5      — palette presets
    c        — cycle palette continuously
    ←/→      — wind (blows the flames sideways)
    +/-      — more / less fuel (intensity)
    e        — toggle ember sparks
    f        — flare burst (ignite a random column)
    SPACE    — pause/resume
    r        — reset wind/fuel to defaults

Palettes:
    1 — Fire   (classic black → red → orange → yellow → white)
    2 — Inferno(crimson core, hotter whites)
    3 — Toxic  (acid green flame)
    4 — Neon   (purple → magenta → cyan)
    5 — Ice    (inverted cool flame)

Zero external dependencies. Pure stdlib.
ANSI truecolor required (modern terminals only).

Author: Mcking (AI assistant do Luis Monteiro)
Data: 2026-08-02
"""

import argparse
import math
import random
import sys
import time
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

# ASCII ramp for --once dump mode (dark → bright)
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
# Each palette is a list of colour stops; heat t ∈ [0,1] maps across them,
# black at the base → white-hot at the tips.

Palette = List[Tuple[int, int, int]]

PALETTES: List[Tuple[str, Palette]] = [
    ("Fire", [
        (0, 0, 0),        # black base
        (40, 4, 0),       # ember dark red
        (140, 20, 0),     # deep red
        (255, 60, 0),     # red
        (255, 140, 0),    # orange
        (255, 210, 60),   # yellow
        (255, 252, 220),  # white-hot
    ]),
    ("Inferno", [
        (8, 0, 0),        # near-black
        (60, 0, 8),       # maroon
        (150, 0, 30),     # crimson
        (240, 40, 20),    # scarlet
        (255, 120, 30),   # ember orange
        (255, 200, 90),   # gold
        (255, 255, 255),  # white
    ]),
    ("Toxic", [
        (0, 5, 0),        # black-green
        (10, 40, 5),      # deep green
        (30, 110, 20),    # green
        (80, 190, 40),    # acid green
        (180, 230, 60),   # yellow-green
        (230, 255, 120),  # pale lime
        (255, 255, 230),  # white-green
    ]),
    ("Neon", [
        (10, 0, 20),      # dark purple
        (60, 0, 90),      # purple
        (150, 0, 160),    # magenta
        (240, 40, 200),   # hot pink
        (120, 160, 255),  # periwinkle
        (160, 240, 255),  # pale cyan
        (245, 245, 255),  # cold white
    ]),
    ("Ice", [
        (0, 2, 10),       # midnight
        (8, 18, 50),      # deep blue
        (20, 60, 120),    # blue
        (50, 130, 200),   # steel blue
        (120, 200, 240),  # ice blue
        (210, 245, 255),  # pale cyan
        (255, 255, 255),  # white
    ]),
]

DEFAULT_WIND   = 0.0    # cells/frame horizontal bias
DEFAULT_FUEL   = 0.45   # probability per column/frame of igniting the base
COOL_FACTOR    = 0.985  # heat lost per cell per frame
FLARE_MIN_GAP  = 1.2    # seconds between random flare bursts
FLARE_MAX_GAP  = 3.0
EMBER_CHANCE   = 0.10   # per-frame spawn probability while fuel is high
EMBER_MAX      = 220


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


# ── Fire ───────────────────────────────────────────────────────────────────────────────────────────

class Fire:
    """Interactive terminal fire effect."""

    def __init__(self, wind: float = DEFAULT_WIND, fuel: float = DEFAULT_FUEL,
                 palette_idx: int = 0, embers: bool = True) -> None:
        self.w, self.h = self._get_size()   # terminal cols × rows
        self.sample_h = self.h * 2          # heat grid is 2× vertically
        self.heat: List[int] = [0] * (self.w * self.sample_h)

        self.palette_idx = palette_idx
        self.time        = 0.0
        self.paused      = False
        self.auto_cycle  = False
        self.cycle_timer = 0.0
        self.running     = True
        self.last_fps    = 60.0

        self.wind        = max(-3.0, min(3.0, wind))   # target wind
        self.wind_cur    = self.wind                     # smoothed wind
        self.fuel        = max(0.0, min(1.0, fuel))
        self.embers_on   = embers
        self.embers: List[List[float]] = []  # [x, y, vx, vy] in sample space
        self.flare_timer = FLARE_MIN_GAP

        self._build_lut()

    # === Setup =====================================================================================

    @staticmethod
    def _get_size() -> Tuple[int, int]:
        """Get terminal size, fallback 80x24."""
        try:
            import shutil
            w, h = shutil.get_terminal_size((80, 24))
            return w, max(h - 1, 10)   # leave one row for the status bar
        except Exception:
            return 80, 24

    def _resize(self) -> None:
        """Rebuild the heat grid for a new terminal size."""
        self.sample_h = self.h * 2
        self.heat = [0] * (self.w * self.sample_h)
        self.embers = []

    def _build_lut(self) -> None:
        """Precompute per-heat-value colour escape codes for the active palette."""
        self.palette_name = PALETTES[self.palette_idx][0]
        palette = PALETTES[self.palette_idx][1]
        self.FG: List[str] = []
        self.BG: List[str] = []
        for v in range(256):
            r, g, b = sample_palette(palette, v / 255.0)
            self.FG.append(rgb_fg(r, g, b))
            self.BG.append(rgb_bg(r, g, b))

    # === Input =====================================================================================

    def _read_key(self) -> Optional[str]:
        """Read one keypress without blocking. Returns None if no key."""
        try:
            if sys.platform == "win32":
                import msvcrt
                if msvcrt.kbhit():
                    k = msvcrt.getwch()
                    if k == '\xe0':
                        k2 = msvcrt.getwch()
                        return {'H': 'UP', 'P': 'DOWN', 'K': 'LEFT', 'M': 'RIGHT'}.get(k2)
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
                                if rest == '[D':
                                    return 'LEFT'
                                if rest == '[C':
                                    return 'RIGHT'
                                if rest == '[A':
                                    return 'UP'
                                if rest == '[B':
                                    return 'DOWN'
                                return 'q'  # bare ESC = quit
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
        elif key == 'LEFT':
            self.wind = max(-3.0, self.wind - 0.5)
        elif key == 'RIGHT':
            self.wind = min(3.0, self.wind + 0.5)
        elif key == '+':
            self.fuel = min(1.0, self.fuel + 0.05)
        elif key == '-':
            self.fuel = max(0.0, self.fuel - 0.05)
        elif key == 'e' or key == 'E':
            self.embers_on = not self.embers_on
            if not self.embers_on:
                self.embers = []
        elif key == 'f' or key == 'F':
            self._flare()
        elif key == 'r' or key == 'R':
            self.wind = DEFAULT_WIND
            self.fuel = DEFAULT_FUEL
            self.auto_cycle = False
        elif key == 'c' or key == 'C':
            self.auto_cycle = not self.auto_cycle
        elif key in '12345':
            self.palette_idx = int(key) - 1
            self.auto_cycle = False
            self._build_lut()

    # === Simulation ================================================================================

    def _flare(self) -> None:
        """Ignite a random column with a tall burst of heat."""
        w = self.w
        h = self.sample_h
        x = random.randrange(2, w - 2)
        height = random.randint(3, max(3, int(h * 0.4)))
        for k in range(height):
            y = h - 1 - k
            if y < 0:
                break
            self.heat[y * w + x] = 255

    def _step(self, dt: float) -> None:
        """Advance the heat grid by *dt* seconds (the classic fire pass)."""
        w, h = self.w, self.sample_h
        f = self.heat

        # Smooth the wind so arrow presses feel natural.
        self.wind_cur += (self.wind - self.wind_cur) * min(1.0, dt * 8.0)
        self.wind_cur = max(-3.0, min(3.0, self.wind_cur))
        off = int(round(self.wind_cur))

        # Bottom-up diffusion: each cell averages the 4 cells below it, then cools.
        for y in range(h - 2, 0, -1):
            r0 = (y + 1) * w
            r1 = (y + 2) * w
            rw = y * w
            for x in range(1, w - 1):
                sx = x + off
                if sx < 1:
                    sx = 1
                elif sx > w - 2:
                    sx = w - 2
                v = f[r0 + sx - 1] + f[r0 + sx] + f[r0 + sx + 1]
                if y + 2 < h:
                    v += f[r1 + sx]
                    v *= 0.25
                else:
                    v /= 3.0
                f[rw + x] = int(v * COOL_FACTOR)

        # Seed fuel along the bottom rows.
        bottom = (h - 1) * w
        second = (h - 2) * w
        for x in range(w):
            if random.random() < self.fuel:
                f[bottom + x] = 255
                if random.random() < self.fuel * 0.5:
                    f[second + x] = 255

        # Random flare bursts for liveliness.
        self.flare_timer -= dt
        if self.flare_timer <= 0.0:
            self._flare()
            self.flare_timer = random.uniform(FLARE_MIN_GAP, FLARE_MAX_GAP)

        # Ember sparks.
        if self.embers_on:
            if len(self.embers) < EMBER_MAX and random.random() < EMBER_CHANCE * self.fuel * 4:
                self.embers.append([
                    random.uniform(1, w - 2),
                    float(h - 1),
                    random.uniform(-0.6, 0.6) + self.wind_cur * 0.5,
                    random.uniform(-28.0, -12.0),
                ])
        alive = []
        for e in self.embers:
            e[0] += e[2] * dt
            e[1] += e[3] * dt
            if e[1] > 0.0 and 0.0 < e[0] < w - 1:
                alive.append(e)
        self.embers = alive

    # === Rendering =================================================================================

    def _render(self) -> str:
        """Build the full frame (fire + embers + status bar)."""
        w, h = self.w, self.h
        f = self.heat
        rows: List[List[str]] = []
        for y in range(h):
            r0 = (y * 2) * w
            r1 = (y * 2 + 1) * w
            row = [f"{self.BG[f[r0 + x]]}{self.FG[f[r1 + x]]}▀" for x in range(w)]
            rows.append(row)

        # Ember overlay: replace the cell at the ember's position.
        for e in self.embers:
            ex, ey = int(e[0]), int(e[1])
            if not (0 <= ex < w and 0 <= ey < self.sample_h):
                continue
            ry = ey // 2
            if ry >= h:
                continue
            hot = min(255, f[ey * w + ex] + 130)
            ch = '*' if random.random() < 0.6 else '·'
            rows[ry][ex] = f"{self.BG[f[ey * w + ex]]}{BOLD}{self.FG[hot]}{ch}"

        # Status bar.
        wind_arrow = '←' * int(round(-self.wind_cur)) if self.wind_cur < -0.25 else \
                     '→' * int(round(self.wind_cur)) if self.wind_cur > 0.25 else '·'
        parts = [RESET, CLEAR, HOME]
        parts.extend(''.join(row) for row in rows)
        parts.append(RESET)
        parts.append(
            f"\r\n{BOLD}{self.palette_name}🔥 "
            f"wind {wind_arrow:<3} fuel {self.fuel * 100:3.0f}% "
            f"embers {len(self.embers):3d} "
            f"[1-5]pal [c]cycle [←→]wind [+/-]fuel [e]embers [f]flare "
            f"[space]pause [r]reset [q]quit — {self.last_fps:4.1f} fps"
        )
        return "".join(parts)

    def render_ascii(self) -> str:
        """Static ASCII dump of the current heat grid (for --once / tests)."""
        w, h = self.w, self.sample_h
        f = self.heat
        n = len(RAMP) - 1
        lines = []
        for y in range(h):
            lines.append("".join(RAMP[min(n, f[y * w + x] * n // 255)] for x in range(w)))
        return "\n".join(lines)

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
                self._resize()

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
                    self._build_lut()

            sys.stdout.write(self._render())
            sys.stdout.flush()

            self.last_fps = 0.9 * self.last_fps + 0.1 * (1.0 / max(dt, 1e-4))
            elapsed = time.monotonic() - now
            if elapsed < frame_time:
                time.sleep(frame_time - elapsed)

        sys.stdout.write(SHOW + RESET + "\n")


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Terminal Fire 🔥 — classic demoscene flame")
    parser.add_argument("--wind", type=float, default=DEFAULT_WIND, help="initial wind (-3..3)")
    parser.add_argument("--fuel", type=float, default=DEFAULT_FUEL, help="initial fuel (0..1)")
    parser.add_argument("--palette", type=int, default=1, choices=range(1, len(PALETTES) + 1),
                        help="palette preset (1-5)")
    parser.add_argument("--no-embers", action="store_true", help="disable ember sparks")
    parser.add_argument("--once", nargs="?", const=30, type=int, metavar="FRAMES",
                        help="simulate FRAMES steps, dump ASCII frame, exit (for demos/tests)")
    args = parser.parse_args()

    fire = Fire(
        wind=args.wind,
        fuel=args.fuel,
        palette_idx=args.palette - 1,
        embers=not args.no_embers,
    )

    if args.once is not None:
        # Non-interactive: warm up the grid, then dump a static ASCII frame.
        for _ in range(args.once):
            fire._step(1.0 / 60.0)
        print(fire.render_ascii())
        return

    try:
        fire.run()
    except KeyboardInterrupt:
        sys.stdout.write(SHOW + RESET + "\n")


if __name__ == "__main__":
    main()

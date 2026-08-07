#!/usr/bin/env python3
"""
ripples.py — Terminal Water Ripples 💧
========================================
Classic demoscene water effect rendered to ANSI truecolor terminal.

A 2D heightfield on a half-resolution grid runs the canonical wave
propagation pass — each cell becomes the average of its four
neighbours minus its previous height, scaled by a damping factor —
so dropped stones bloom into expanding, interfering rings. The
surface is lit by fake slope shading (gradient · light direction):
calm water glows, wave troughs darken, crests sparkle white.
Rendered with the half-block trick (each cell draws ▀ with
fg = bottom sample, bg = top sample) for 2× vertical resolution.

Usage:
    python ripples.py [--seed N] [--palette N] [--damping N] [--rain]
                      [--width W] [--height H] [--once [FRAMES]]

Controls:
    q/ESC    — quit
    SPACE    — drop a stone (random position)
    s        — splash (big stone, big rings)
    d        — toggle rain mode (constant drizzle)
    +/-      — more / less damping (how long ripples last)
    1-5      — palette presets
    c        — cycle palette continuously
    p        — pause/resume
    r        — calm the water (reset)

Palettes:
    1 — Lagoon (tropical teal, pale sparkle)
    2 — Ocean  (deep navy, ice-blue crests)
    3 — Neon   (violet → magenta → electric cyan)
    4 — Toxic  (acid green)
    5 — Sunset (crimson → ember orange → gold)

Zero external dependencies. Pure stdlib.
ANSI truecolor required (modern terminals only).

Author: Mcking (AI assistant do Luis Monteiro)
Data: 2026-08-07
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


def sample_palette(palette: List[Tuple[int, int, int]], t: float) -> Tuple[int, int, int]:
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


# ── Palettes ───────────────────────────────────────────────────────────────────────────────────────
# Each palette is a ramp dark → white. Calm water renders at the bright
# (crest) end, wave troughs slide down into the deep colour, and slopes
# facing the light clamp to pure white sparkles.

Palette = List[Tuple[int, int, int]]

PALETTES: List[Tuple[str, Palette]] = [
    ("Lagoon", [
        (4, 18, 34),       # abyss
        (10, 56, 84),      # deep teal
        (34, 128, 152),    # mid lagoon
        (120, 214, 224),   # bright crest
        (252, 254, 255),   # sparkle
    ]),
    ("Ocean", [
        (2, 8, 26),        # midnight deep
        (8, 28, 74),       # navy
        (26, 76, 148),     # open sea
        (110, 170, 226),   # ice crest
        (240, 248, 255),   # sparkle
    ]),
    ("Neon", [
        (14, 2, 34),       # dark violet
        (72, 12, 110),     # purple
        (180, 50, 200),    # magenta
        (110, 240, 250),   # electric cyan
        (255, 255, 255),   # sparkle
    ]),
    ("Toxic", [
        (3, 12, 4),        # black-green
        (12, 48, 14),      # deep swamp
        (46, 132, 30),     # acid
        (150, 226, 74),    # lime crest
        (240, 255, 220),   # sparkle
    ]),
    ("Sunset", [
        (26, 4, 16),       # burnt dark
        (96, 16, 42),      # crimson
        (200, 64, 44),     # ember
        (255, 168, 74),    # gold crest
        (255, 244, 214),   # sparkle
    ]),
]

# ── Physics constants ──────────────────────────────────────────────────────────────────────────────
DEFAULT_DAMPING = 0.980    # wave persistence (lower = ripples die faster)
DAMPING_MIN     = 0.900
DAMPING_MAX     = 0.999
GRAD_SCALE      = 16.0     # height → slope normalisation for the lighting model
LIGHT_X         = 0.45     # light direction (points toward the viewer-left/top)
LIGHT_Y         = 0.25
LIGHT_Z         = 0.58     # ambient: calm water sits mid-tone so ripples
                              # can darken (troughs) AND sparkle (crests)
DROP_STRENGTH   = 90.0     # stone drop
SPLASH_STRENGTH = 260.0    # splash drop
RAIN_STRENGTH   = 38.0     # drizzle drop
HEIGHT_CLAMP    = 256.0    # safety clamp for the heightfield


class Water:
    """Interactive terminal water ripple effect."""

    def __init__(self, seed: int = 1337, palette_idx: int = 0,
                 damping: float = DEFAULT_DAMPING, rain: bool = False,
                 size: Optional[Tuple[int, int]] = None) -> None:
        self.seed = seed
        if size is not None:
            self.w, self.h = size
        else:
            self.w, self.h = self._get_size()
        self.sample_h = self.h * 2          # heightfield is 2× vertically

        self.palette_idx = palette_idx
        self.damping     = max(DAMPING_MIN, min(DAMPING_MAX, damping))
        self.rain        = rain
        self.rain_timer  = 0.0
        self.time        = 0.0
        self.paused      = False
        self.auto_cycle  = False
        self.cycle_timer = 0.0
        self.running     = True
        self.last_fps    = 60.0

        self.rng = random.Random(seed)
        self._alloc_grids()
        self._build_lut()

    # === Setup =====================================================================================

    @staticmethod
    def _get_size() -> Tuple[int, int]:
        """Get terminal size, fallback 100x30."""
        try:
            import shutil
            w, h = shutil.get_terminal_size((100, 30))
            return max(w, 40), max(h - 1, 12)   # leave one row for the status bar
        except Exception:
            return 100, 30

    def _alloc_grids(self) -> None:
        """(Re)allocate the heightfield with a 1-cell zero border, so the
        hot propagation/render loops never bounds-check neighbour reads."""
        self.stride = self.w + 2
        n = (self.sample_h + 2) * self.stride
        self.cur = [0.0] * n     # current heights
        self.old = [0.0] * n     # previous heights (wave memory)

    def _build_lut(self) -> None:
        """Precompute per-brightness colour escape codes for the active palette."""
        self.palette_name = PALETTES[self.palette_idx][0]
        palette = PALETTES[self.palette_idx][1]
        self.FG: List[str] = []
        self.BG: List[str] = []
        for v in range(256):
            t = (v / 255.0) ** 1.3   # mild gamma: keep midtones rich, sparkles white
            r, g, b = sample_palette(palette, t)
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
            self._drop_at(random.uniform(0.15, 0.85) * self.w,
                          random.uniform(0.15, 0.85) * self.sample_h,
                          DROP_STRENGTH, radius=2.0)
        elif key == 's' or key == 'S':
            self._drop_at(random.uniform(0.2, 0.8) * self.w,
                          random.uniform(0.2, 0.8) * self.sample_h,
                          SPLASH_STRENGTH, radius=4.5)
        elif key == 'd' or key == 'D':
            self.rain = not self.rain
        elif key == '+' or key == '=':
            self.damping = min(DAMPING_MAX, self.damping + 0.003)
        elif key == '-':
            self.damping = max(DAMPING_MIN, self.damping - 0.003)
        elif key == 'p' or key == 'P':
            self.paused = not self.paused
        elif key == 'r' or key == 'R':
            self.cur = [0.0] * len(self.cur)
            self.old = [0.0] * len(self.old)
            self.auto_cycle = False
        elif key == 'c' or key == 'C':
            self.auto_cycle = not self.auto_cycle
        elif key in '12345':
            self.palette_idx = int(key) - 1
            self.auto_cycle = False
            self._build_lut()

    # === Simulation ================================================================================

    def _drop_at(self, x: float, y: float, strength: float, radius: float) -> None:
        """Sink a blob of negative height into the *old* grid: the classic
        trick that makes the next propagation pass bloom into an expanding,
        slightly wobbly ring."""
        stride = self.stride
        old = self.old
        w, sh = self.w, self.sample_h
        r = self.rng.uniform(0.7, 1.0) * strength
        for _ in range(int(radius * radius * 14)):
            dx = self.rng.uniform(-radius, radius)
            dy = self.rng.uniform(-radius, radius)
            if dx * dx + dy * dy > radius * radius:
                continue
            ix = int(x + dx)
            iy = int(y + dy)
            if 2 <= ix <= w - 1 and 2 <= iy <= sh - 1:
                fall = 1.0 - math.sqrt(dx * dx + dy * dy) / radius
                old[iy * stride + ix] -= r * (0.4 + 0.6 * fall) * self.rng.uniform(0.5, 1.0)

    def _step(self, dt: float) -> None:
        """Advance the wave field by *dt* seconds (canonical water pass)."""
        stride = self.stride
        cur, old = self.cur, self.old
        damp = self.damping
        new = [0.0] * len(cur)
        for y in range(1, self.sample_h + 1):
            base = y * stride
            for x in range(1, self.w + 1):
                i = base + x
                v = (cur[i - 1] + cur[i + 1] + cur[i - stride] + cur[i + stride]) * 0.5 - old[i]
                nv = v * damp
                if nv > HEIGHT_CLAMP:
                    nv = HEIGHT_CLAMP
                elif nv < -HEIGHT_CLAMP:
                    nv = -HEIGHT_CLAMP
                new[i] = nv
        self.old, self.cur = cur, new

        # Rain mode: a light drizzle, biased toward the upper part of the pool.
        if self.rain:
            self.rain_timer -= dt
            if self.rain_timer <= 0.0:
                self._drop_at(self.rng.uniform(0.1, 0.9) * self.w,
                              self.rng.uniform(0.05, 0.6) * self.sample_h,
                              RAIN_STRENGTH, radius=1.3)
                self.rain_timer = self.rng.uniform(0.05, 0.22)

    def _update(self, dt: float) -> None:
        """Advance the simulation by *dt* seconds."""
        if self.paused:
            return
        self.time += dt
        self._step(dt)
        if self.auto_cycle:
            self.cycle_timer += dt
            if self.cycle_timer >= 6.0:
                self.cycle_timer = 0.0
                self.palette_idx = (self.palette_idx + 1) % len(PALETTES)
                self._build_lut()

    # === Rendering =================================================================================

    @staticmethod
    def _brightness(f: List[float], stride: int, i: int) -> float:
        """Fake slope lighting: brightness = LIGHT_Z − ∇h·L, clamped to [0,1].
        Calm water (∇h = 0) renders at the bright end; slopes away from the
        light darken; slopes facing it clamp to pure white sparkles."""
        gx = (f[i + 1] - f[i - 1]) * 0.5
        gy = (f[i + stride] - f[i - stride]) * 0.5
        b = LIGHT_Z - (gx * LIGHT_X + gy * LIGHT_Y) / GRAD_SCALE
        if b < 0.0:
            return 0.0
        if b > 1.0:
            return 1.0
        return b

    def _render(self) -> str:
        """Build the full frame (water + status bar)."""
        w, h = self.w, self.h
        stride = self.stride
        f = self.cur
        FG, BG = self.FG, self.BG
        rows: List[str] = []
        for sy in range(h):
            r0 = (sy * 2 + 1) * stride   # top half-sample row
            r1 = r0 + stride             # bottom half-sample row
            cells: List[str] = []
            for x in range(1, w + 1):
                i0 = r0 + x
                t0 = int(self._brightness(f, stride, i0) * 255.0)
                t1 = int(self._brightness(f, stride, r1 + x) * 255.0)
                cells.append(BG[t0])
                cells.append(FG[t1])
                cells.append('▀')
            rows.append(''.join(cells))

        parts = [RESET, CLEAR, HOME]
        parts.extend(rows)
        parts.append(RESET)
        parts.append(
            f"\r\n{BOLD}💧 {self.palette_name} | "
            f"{self.last_fps:5.0f} fps | damp {self.damping:.3f} | "
            f"rain {'ON ' if self.rain else 'OFF'} | 🗺 {self.seed}{RESET}  "
            f"space drop · s splash · d rain · +/- damp · 1-5 pal · "
            f"c cycle · p pause · r calm · q quit"
        )
        return ''.join(parts)

    def render_ascii(self) -> str:
        """Static ASCII dump of the current frame (for --once / tests)."""
        w = self.w
        stride = self.stride
        f = self.cur
        n = len(RAMP) - 1
        lines = []
        for y in range(1, self.sample_h + 1):
            base = y * stride
            lines.append("".join(
                RAMP[int(self._brightness(f, stride, base + x) * n)]
                for x in range(1, w + 1)
            ))
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

            key = self._read_key()
            if key is not None:
                self.handle_key(key)

            self._update(dt)

            # Handle terminal resize
            try:
                import shutil
                w, h = shutil.get_terminal_size((self.w, self.h))
                w, h = max(w, 40), max(h - 1, 12)
                if (w, h) != (self.w, self.h):
                    self.w, self.h = w, h
                    self.sample_h = h * 2
                    self._alloc_grids()
            except Exception:
                pass

            sys.stdout.write(self._render())
            sys.stdout.flush()

            self.last_fps = 0.9 * self.last_fps + 0.1 * (1.0 / max(dt, 1e-4))
            elapsed = time.monotonic() - now
            if elapsed < frame_time:
                time.sleep(frame_time - elapsed)

        sys.stdout.write(SHOW + RESET + "\n")


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Terminal Water Ripples 💧 — classic demoscene water effect")
    parser.add_argument("--seed", type=int, default=1337, help="world seed (0..2^32)")
    parser.add_argument("--palette", type=int, default=1, choices=range(1, len(PALETTES) + 1),
                        help="palette preset (1-5)")
    parser.add_argument("--damping", type=float, default=DEFAULT_DAMPING,
                        help="wave persistence (0.90..0.999)")
    parser.add_argument("--rain", action="store_true", help="start with rain mode on")
    parser.add_argument("--width", type=int, default=100, help="width for --once mode")
    parser.add_argument("--height", type=int, default=30, help="height for --once mode")
    parser.add_argument("--once", nargs="?", const=30, type=int, metavar="FRAMES",
                        help="run FRAMES frames, dump ASCII frame, exit (for demos/tests)")
    args = parser.parse_args()

    # In --once mode, default to rain so the static frame actually shows
    # ripples (a perfectly calm pool is just a flat grey rectangle).
    rain = args.rain or args.once is not None

    water = Water(seed=args.seed, palette_idx=args.palette - 1,
                  damping=args.damping, rain=rain,
                  size=(args.width, args.height) if args.once is not None else None)

    if args.once is not None:
        # Non-interactive: let the ripples bloom, then dump a static ASCII
        # frame. The full update+render loop is timed so headless/CI runs
        # catch performance regressions; stats go to stderr, stdout stays
        # pure ASCII.
        t0 = time.monotonic()
        out = ""
        for _ in range(args.once):
            water._update(1.0 / 30.0)
            out = water.render_ascii()   # full render, like the interactive loop
        dt = max(time.monotonic() - t0, 1e-9)
        print(out)
        print(f"[bench] {args.once} frames in {dt:.2f}s "
              f"\u2192 {args.once / dt:.0f} fps ({water.w}x{water.sample_h} grid, "
              f"seed {args.seed}, palette {args.palette}, damping {water.damping:.3f})",
              file=sys.stderr)
        return

    try:
        water.run()
    except KeyboardInterrupt:
        sys.stdout.write(SHOW + RESET + "\n")


if __name__ == "__main__":
    main()

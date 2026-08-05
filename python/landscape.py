#!/usr/bin/env python3
"""
landscape.py — Terminal Landscape 🌄
=====================================
Classic demoscene 3D terrain flyover rendered to ANSI truecolor terminal.

A periodic fractal heightmap (6-octave fBm value noise, seamlessly
wrapped so the world is a torus) is ray-marched per screen column:
the camera cruises over mountains, rolling plains and tide-washed
lakes while distance fog melts the horizon into the sky. Mountains
are ridge-lit, shorelines foam, and each palette brings its own
weather. Rendered with the half-block trick (each cell draws ▀ with
fg = bottom sample, bg = top sample) for 2× vertical resolution.

Usage:
    python landscape.py [--seed N] [--palette N] [--speed N]
                        [--width W] [--height H] [--once [FRAMES]]

Controls:
    q/ESC    — quit
    ←/→      — turn (hold)
    ↑/↓      — climb / dive (hold)
    +/-      — faster / slower
    1-5      — palette presets
    c        — cycle palette continuously
    SPACE    — pause/resume
    r        — reset flight (position, altitude, speed)

Palettes:
    1 — Day    (blue sky, green lowlands, snowy peaks)
    2 — Sunset (amber sky, golden terrain, low sun)
    3 — Neon   (violet sky, electric terrain)
    4 — Arctic (pale ice world, mirror water)
    5 — Night  (moonlit terrain, twinkling stars)

Zero external dependencies. Pure stdlib.
ANSI truecolor required (modern terminals only).

Author: Mcking (AI assistant do Luis Monteiro)
Data: 2026-08-03
"""

import argparse
import math
import random
import sys
import time
from typing import Dict, List, Optional, Tuple

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

# Precomputed ANSI escape codes, quantized to 5 bits/channel (32³ = 32768)
# so the hot render path is just two table lookups per half-block cell.
_ESC_FG: List[str] = []
_ESC_BG: List[str] = []


def _ensure_esc_lut() -> None:
    """Build the quantized foreground/background escape tables (once)."""
    if _ESC_FG:
        return
    for i in range(32768):
        r = (i >> 10) & 0x1F
        g = (i >> 5) & 0x1F
        b = i & 0x1F
        r8, g8, b8 = r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2
        _ESC_FG.append(f"\033[38;2;{r8};{g8};{b8}m")
        _ESC_BG.append(f"\033[48;2;{r8};{g8};{b8}m")


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
# Each palette: sky gradient, sun (colour + azimuth/elevation), water, terrain
# colour stops (shore → peaks), and whether stars twinkle at night.
# The fog colour is always the horizon sky colour, so far terrain melts
# seamlessly into the sky.

Palette = Dict[str, object]

PALETTES: List[Tuple[str, Palette]] = [
    ("Day", {
        "sky_top": (64, 128, 222), "sky_hor": (206, 222, 240),
        "sun": (255, 246, 205), "sun_az": 2.4, "sun_el": 0.42,
        "water": (26, 92, 152), "deep": (6, 28, 58),
        "foam": (236, 244, 250), "stars": False,
        "terrain": [
            (158, 182, 108),   # shore sand
            (92, 152, 62),     # lowland green
            (122, 112, 72),    # hill brown
            (142, 130, 118),   # rock grey
            (244, 248, 252),   # snow
        ],
    }),
    ("Sunset", {
        "sky_top": (34, 26, 78), "sky_hor": (255, 148, 66),
        "sun": (255, 214, 130), "sun_az": 2.4, "sun_el": 0.12,
        "water": (46, 56, 112), "deep": (14, 12, 40),
        "foam": (255, 226, 180), "stars": False,
        "terrain": [
            (206, 160, 96),    # sand
            (128, 96, 52),     # dry grass
            (152, 96, 58),     # hill
            (172, 112, 92),    # rock
            (252, 214, 184),   # snow
        ],
    }),
    ("Neon", {
        "sky_top": (12, 4, 30), "sky_hor": (128, 44, 168),
        "sun": (255, 96, 220), "sun_az": 2.4, "sun_el": 0.5,
        "water": (34, 12, 66), "deep": (8, 2, 20),
        "foam": (220, 200, 255), "stars": False,
        "terrain": [
            (150, 70, 190),    # shore
            (46, 182, 126),    # acid lowland
            (70, 66, 196),     # electric hill
            (168, 66, 208),    # magenta rock
            (236, 186, 255),   # pale peak
        ],
    }),
    ("Arctic", {
        "sky_top": (28, 44, 84), "sky_hor": (182, 202, 216),
        "sun": (255, 252, 228), "sun_az": 2.4, "sun_el": 0.32,
        "water": (16, 54, 96), "deep": (4, 18, 38),
        "foam": (232, 242, 248), "stars": False,
        "terrain": [
            (168, 186, 198),   # ice shore
            (96, 142, 152),    # frozen moss
            (124, 152, 172),   # tundra
            (152, 164, 182),   # rock
            (240, 248, 252),   # snow
        ],
    }),
    ("Night", {
        "sky_top": (3, 5, 14), "sky_hor": (22, 32, 52),
        "sun": (226, 232, 255), "sun_az": 2.4, "sun_el": 0.55,   # the moon
        "water": (10, 18, 42), "deep": (2, 4, 12),
        "foam": (120, 132, 156), "stars": True,
        "terrain": [
            (64, 74, 92),      # shore
            (40, 62, 52),      # dark lowland
            (56, 56, 72),      # hill
            (82, 82, 102),     # rock
            (158, 162, 188),   # snow
        ],
    }),
]

# ── World constants ────────────────────────────────────────────────────────────────────────────────
MAP_SIZE   = 600.0    # world units (toroidal: wraps around)
GRID_SIZE  = 256      # heightmap resolution (GRID_SIZE²)
H_MAX      = 30.0     # highest peak
WATER      = 9.0      # base water level (tides move it slightly)
TIDE_AMP   = 0.8      # tide amplitude
FOG_DIST   = 200.0    # full fog at this distance

NEAR       = 0.7      # ray-march start distance
FAR        = 250.0    # ray-march cutoff (beyond fog — no wrap artefacts)
STEP       = 1.17     # multiplicative march step (classic landscape trick)

FOV_H      = 75.0 * math.pi / 180.0
PITCH      = -0.18    # camera looks slightly down

DEFAULT_CRUISE = 16.0   # altitude above terrain
DEFAULT_SPEED  = 55.0   # world units / second


class PeriodicNoise:
    """Seeded value noise, periodic on [0,1)² (toroidal world)."""

    def __init__(self, size: int, seed: int) -> None:
        rng = random.Random(seed)
        self.size = size
        self.vals = [rng.random() for _ in range(size * size)]

    def at(self, x: float, y: float) -> float:
        """Smooth bilinear value noise at (x, y), x/y ∈ [0,1) (wraps)."""
        size = self.size
        gx = x * size
        ix = int(gx) % size
        fx = gx - math.floor(gx)
        gy = y * size
        iy = int(gy) % size
        fy = gy - math.floor(gy)
        ix1 = (ix + 1) % size
        iy1 = (iy + 1) % size
        sx = fx * fx * (3.0 - 2.0 * fx)
        sy = fy * fy * (3.0 - 2.0 * fy)
        v = self.vals
        a = v[iy * size + ix]
        b = v[iy * size + ix1]
        c = v[iy1 * size + ix]
        d = v[iy1 * size + ix1]
        return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy


def make_heightmap(seed: int) -> List[List[float]]:
    """Precompute the 6-octave fBm heightmap grid (one-time cost).

    The 6th octave (freq 32) bakes fine ridge texture straight into the
    grid, so the runtime ray-march needs just one bilinear lookup.
    """
    noise = PeriodicNoise(GRID_SIZE, seed)
    grid: List[List[float]] = []
    for iy in range(GRID_SIZE):
        row: List[float] = []
        u = iy / GRID_SIZE
        for ix in range(GRID_SIZE):
            v = ix / GRID_SIZE
            f = 0.0
            amp = 1.0
            tot = 0.0
            for octave in range(6):
                f += amp * noise.at(v * (1 << octave), u * (1 << octave))
                tot += amp
                amp *= 0.5
            row.append(f / tot)
        grid.append(row)
    return grid


def bilinear(grid: List[List[float]], u: float, v: float) -> float:
    """Wrap-around bilinear sample of the heightmap grid at (u, v) ∈ [0,1)²."""
    size = GRID_SIZE
    gx = u * size
    ix = int(gx)
    fx = gx - ix
    gy = v * size
    iy = int(gy)
    fy = gy - iy
    ix1 = ix + 1
    if ix1 >= size:
        ix1 -= size
    iy1 = iy + 1
    if iy1 >= size:
        iy1 -= size
    sx = fx * fx * (3.0 - 2.0 * fx)
    sy = fy * fy * (3.0 - 2.0 * fy)
    a = grid[iy][ix]
    b = grid[iy][ix1]
    c = grid[iy1][ix]
    d = grid[iy1][ix1]
    return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy


# ── Landscape ──────────────────────────────────────────────────────────────────────────────────────

class Landscape:
    """Interactive terminal 3D terrain flyover."""

    def __init__(self, seed: int = 1337, palette_idx: int = 0,
                 speed: float = DEFAULT_SPEED, size: Optional[Tuple[int, int]] = None) -> None:
        self.seed = seed
        if size is not None:
            self.w, self.h = size
        else:
            self.w, self.h = self._get_size()
        self.sample_h = self.h * 2          # half-block → 2× vertical resolution

        self.palette_idx = palette_idx
        self.time        = 0.0
        self.paused      = False
        self.auto_cycle  = False
        self.cycle_timer = 0.0
        self.running     = True
        self.last_fps    = 60.0

        # Camera state
        self.angle    = 0.7
        self.turn     = 0.0
        self.cruise   = DEFAULT_CRUISE
        self.climb    = 0.0
        self.speed    = speed
        self.cam_x    = MAP_SIZE * 0.5
        self.cam_z    = MAP_SIZE * 0.5
        self.cam_y    = 0.0

        self.water_level = WATER

        # Height shaping LUT: fbm ∈ [0,1] → (f ** 1.7) * H_MAX (pow is slow)
        self._height_lut = [(i / 255.0) ** 1.7 * H_MAX for i in range(256)]
        self._inv_map = 1.0 / MAP_SIZE

        # Heightmap generation (one-time, ~0.6 s)
        self.grid = make_heightmap(seed)
        self.cam_y = self._height(self.cam_x, self.cam_z) + self.cruise

        # Per-palette colour LUTs (rebuilt lazily on palette switch)
        self._pal_lut: Optional[Tuple[int, Tuple[int, int, int], Tuple[int, int, int],
                                     List[Tuple[int, int, int]], List[Tuple[int, int, int]],
                                     Tuple[int, int, int]]] = None

        self._recompute_geometry()

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

    def _recompute_geometry(self) -> None:
        """Recalculate per-size projection constants."""
        self.sample_h = self.h * 2
        self.tan_half = math.tan(FOV_H / 2.0)
        aspect = self.w / self.sample_h
        self.fov_v = 2.0 * math.atan(self.tan_half / aspect)

    # === Terrain ===================================================================================

    def _height(self, x: float, z: float) -> float:
        """Terrain height at (x, z): shaped fBm sampled from the grid."""
        u = (x % MAP_SIZE) * self._inv_map
        v = (z % MAP_SIZE) * self._inv_map
        return self._height_lut[min(255, int(bilinear(self.grid, u, v) * 255.0))]

    def _palette_lut(self) -> Tuple[int, Tuple[int, int, int], Tuple[int, int, int],
                                    List[Tuple[int, int, int]], List[Tuple[int, int, int]],
                                    Tuple[int, int, int]]:
        """(palette_idx, sky_top, sky_hor, terrain_lut, water_lut, foam) — cached."""
        if self._pal_lut is not None and self._pal_lut[0] == self.palette_idx:
            return self._pal_lut
        pal = PALETTES[self.palette_idx][1]
        terrain_lut = [sample_palette(pal["terrain"], i / 255.0) for i in range(256)]
        water_lut = [lerp_color(pal["water"], pal["deep"], i / 255.0) for i in range(256)]
        self._pal_lut = (self.palette_idx, pal["sky_top"], pal["sky_hor"],
                         terrain_lut, water_lut, pal["foam"])
        return self._pal_lut

    def _shade(self, h: float, d: float, dh: float, sky_hor: Tuple[int, int, int],
               terrain_lut: List[Tuple[int, int, int]],
               water_lut: List[Tuple[int, int, int]],
               foam: Tuple[int, int, int]) -> Tuple[int, int, int]:
        """Colour a terrain sample: water/terrain LUT + foam + cliff light + fog."""
        water = self.water_level
        if h < water:
            idx = min(255, int((water - h) / 8.0 * 255.0))
            col = water_lut[idx]
            if water - h < 1.5:                       # shoreline foam
                col = lerp_color(col, foam, 0.55)
        else:
            ht = min(1.0, (h - water) / (H_MAX - water))
            col = terrain_lut[int(ht * 255.0)]
            if h - water < 2.5:                       # wet sand near shore
                col = lerp_color(col, foam, 0.5 * (1.0 - (h - water) / 2.5))

        # Cliff light: steep drops catch the light (ignores small-scale texture)
        s = min(1.0, max(0.0, (abs(dh) - 3.0) / 6.0))
        if s > 0.02:
            col = lerp_color(col, (255, 255, 255), s * s * 0.4)

        # Distance fog → horizon sky colour (inlined lerp: hot path)
        fog_t = min(1.0, d / FOG_DIST)
        if fog_t > 0.02:
            r0, g0, b0 = col
            r1, g1, b1 = sky_hor
            col = (int(r0 + (r1 - r0) * fog_t),
                   int(g0 + (g1 - g0) * fog_t),
                   int(b0 + (b1 - b0) * fog_t))
        return col

    # === Rendering =================================================================================

    @staticmethod
    def _star(c: int, r: int, t: float) -> float:
        """Twinkle brightness for a hash-based star at (c, r), 0 = no star."""
        hsh = (c * 374761393 + r * 668265263) & 0xFFFFFFFF
        if hsh % 113 != 0:
            return 0.0
        tw = max(0.0, math.sin(t * 2.0 + (hsh % 628) * 0.01)) ** 4
        return tw * 0.9

    def _render_frame(self) -> List[List[Tuple[int, int, int]]]:
        """Ray-march the terrain and return a SH × W grid of RGB colours."""
        W, SH = self.w, self.sample_h
        half_w = W / 2.0
        pal = PALETTES[self.palette_idx][1]
        sky_top, sky_hor = pal["sky_top"], pal["sky_hor"]
        sun_col = pal["sun"]
        stars_on = pal["stars"]

        # Sun / moon screen position (project the fixed world direction)
        rel = ((pal["sun_az"] - self.angle + math.pi) % (2 * math.pi)) - math.pi
        sx = sy = None
        if abs(rel) < FOV_H / 2.0 + 0.5:
            sx = half_w + math.tan(rel) / self.tan_half * half_w
            sy = SH / 2.0 - (pal["sun_el"] - PITCH) * (SH / self.fov_v)

        frame = [[(0, 0, 0)] * W for _ in range(SH)]
        cam_x, cam_z, cam_y = self.cam_x, self.cam_z, self.cam_y
        angle = self.angle
        _, _, sky_hor, terrain_lut, water_lut, foam = self._palette_lut()
        shade = self._shade

        for c in range(W):
            # Horizontal ray direction for this column
            off = (c - half_w) / half_w
            ra = angle + math.atan(off * self.tan_half)
            dx, dz = math.cos(ra), math.sin(ra)

            # March near → far; each sample that lands higher on screen than
            # anything seen so far fills the rows down to the previous sample
            # (classic per-column heightfield painter). Each segment is shaded
            # once at its midpoint — segments are only 1-2 rows tall, so this
            # halves the shading cost with no visible difference.
            d = NEAR
            px = (cam_x + dx * d) % MAP_SIZE
            pz = (cam_z + dz * d) % MAP_SIZE
            h_prev = self._height(px, pz)
            d_prev = d
            filled = SH
            while d < FAR and filled > 0:
                d *= STEP
                px = (cam_x + dx * d) % MAP_SIZE
                pz = (cam_z + dz * d) % MAP_SIZE
                h = self._height(px, pz)
                y = SH / 2.0 - (math.atan2(h - cam_y, d) - PITCH) * (SH / self.fov_v)
                if y < filled:
                    yi = max(0, int(math.ceil(y)))
                    if yi < filled:
                        col = shade((h + h_prev) * 0.5, (d + d_prev) * 0.5, h - h_prev,
                                    sky_hor, terrain_lut, water_lut, foam)
                        for r in range(yi, filled):
                            frame[r][c] = col
                    filled = yi
                    if filled <= 0:
                        break
                d_prev, h_prev = d, h

            # Sky above the silhouette
            for r in range(filled):
                col = lerp_color(sky_top, sky_hor, min(1.0, r / SH * 2.0))
                if sx is not None:
                    glow = math.exp(-(((c - sx) / 9.0) ** 2 + ((r - sy) / 6.5) ** 2) * 0.5)
                    if glow > 0.01:
                        col = lerp_color(col, sun_col, min(1.0, glow))
                if stars_on and r < SH * 0.55:
                    tw = self._star(c, r, self.time)
                    if tw > 0.0:
                        col = lerp_color(col, (255, 255, 255), tw)
                frame[r][c] = col

        return frame

    def render_ascii(self) -> str:
        """Static ASCII dump of the current frame (for --once / tests)."""
        frame = self._render_frame()
        lines = []
        for row in frame:
            lines.append("".join(
                RAMP[(row[x][0] * 299 + row[x][1] * 587 + row[x][2] * 114) * (len(RAMP) - 1) // (255 * 1000)]
                for x in range(self.w)
            ))
        return "\n".join(lines)

    def _render(self) -> str:
        """Build the full truecolor frame (terrain + status bar)."""
        _ensure_esc_lut()
        frame = self._render_frame()
        W = self.w
        esc_bg, esc_fg = _ESC_BG, _ESC_FG
        rows: List[str] = []
        for y in range(self.h):
            fr0 = frame[y * 2]
            fr1 = frame[y * 2 + 1]
            cells: List[str] = []
            for x in range(W):
                c0 = fr0[x]
                c1 = fr1[x]
                cells.append(esc_bg[((c0[0] >> 3) << 10) | ((c0[1] >> 3) << 5) | (c0[2] >> 3)])
                cells.append(esc_fg[((c1[0] >> 3) << 10) | ((c1[1] >> 3) << 5) | (c1[2] >> 3)])
                cells.append('▀')
            rows.append(''.join(cells))
        parts = [RESET, CLEAR, HOME]
        parts.extend(rows)
        parts.append(RESET)
        parts.append(
            f"\r\n{BOLD}🌄 {PALETTES[self.palette_idx][0]} | "
            f"{self.last_fps:5.0f} fps | ⚡{self.speed:3.0f} | ⛰ {self.cruise:3.0f} | "
            f"🗺 {self.seed}{RESET}  "
            f"←→ turn · ↑↓ alt · +/- spd · 1-5 pal · c cycle · space pause · r reset · q quit"
        )
        return ''.join(parts)

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
            self.turn = -1.5
        elif key == 'RIGHT':
            self.turn = 1.5
        elif key == 'UP':
            self.climb = 16.0
        elif key == 'DOWN':
            self.climb = -16.0
        elif key in ('+', '='):
            self.speed = min(140.0, self.speed + 10.0)
        elif key == '-':
            self.speed = max(15.0, self.speed - 10.0)
        elif key == 'r' or key == 'R':
            self.angle = 0.7
            self.cruise = DEFAULT_CRUISE
            self.speed = DEFAULT_SPEED
            self.cam_x = MAP_SIZE * 0.5
            self.cam_z = MAP_SIZE * 0.5
            self.auto_cycle = False
        elif key == 'c' or key == 'C':
            self.auto_cycle = not self.auto_cycle
        elif key in '12345':
            self.palette_idx = int(key) - 1
            self.auto_cycle = False
            self._pal_lut = None   # rebuild LUTs for the new palette

    # === Main loop =================================================================================

    def _update(self, dt: float) -> None:
        """Advance the flight by *dt* seconds."""
        if self.paused:
            return
        self.time += dt

        # Smooth steering (turn/climb decay handled in run())
        self.angle += self.turn * dt
        self.cruise = max(6.0, min(60.0, self.cruise + self.climb * dt))

        self.cam_x = (self.cam_x + math.cos(self.angle) * self.speed * dt) % MAP_SIZE
        self.cam_z = (self.cam_z + math.sin(self.angle) * self.speed * dt) % MAP_SIZE
        self.cam_y = self._height(self.cam_x, self.cam_z) + self.cruise

        # Tide
        self.water_level = WATER + math.sin(self.time * 0.4) * TIDE_AMP

        if self.auto_cycle:
            self.cycle_timer += dt
            if self.cycle_timer >= 6.0:
                self.cycle_timer = 0.0
                self.palette_idx = (self.palette_idx + 1) % len(PALETTES)
                self._pal_lut = None   # rebuild LUTs for the new palette

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
            # Arrow keys are hold-to-steer: decay when released
            if key not in ('LEFT', 'RIGHT'):
                self.turn *= 0.6
            if key not in ('UP', 'DOWN'):
                self.climb *= 0.6

            self._update(dt)

            # Handle terminal resize
            try:
                import shutil
                w, h = shutil.get_terminal_size((self.w, self.h))
                w, h = max(w, 40), max(h - 1, 12)
                if (w, h) != (self.w, self.h):
                    self.w, self.h = w, h
                    self._recompute_geometry()
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
        description="Terminal Landscape 🌄 — classic demoscene 3D terrain flyover")
    parser.add_argument("--seed", type=int, default=1337, help="world seed (0..2^32)")
    parser.add_argument("--palette", type=int, default=1, choices=range(1, len(PALETTES) + 1),
                        help="palette preset (1-5)")
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED, help="initial flight speed")
    parser.add_argument("--width", type=int, default=100, help="width for --once mode")
    parser.add_argument("--height", type=int, default=30, help="height for --once mode")
    parser.add_argument("--once", nargs="?", const=30, type=int, metavar="FRAMES",
                        help="fly FRAMES frames, dump ASCII frame, exit (for demos/tests)")
    args = parser.parse_args()

    land = Landscape(seed=args.seed, palette_idx=args.palette - 1,
                     speed=args.speed,
                     size=(args.width, args.height) if args.once is not None else None)

    if args.once is not None:
        # Non-interactive: fly a bit, then dump a static ASCII frame.
        # The full update+render loop is timed so headless/CI runs catch
        # performance regressions; stats go to stderr, stdout stays pure ASCII.
        t0 = time.monotonic()
        out = ""
        for _ in range(args.once):
            land._update(1.0 / 30.0)
            out = land.render_ascii()   # full render, like the interactive loop
        dt = max(time.monotonic() - t0, 1e-9)
        print(out)
        print(f"[bench] {args.once} frames in {dt:.2f}s "
              f"\u2192 {args.once / dt:.0f} fps ({land.w}x{land.h}, "
              f"seed {args.seed}, palette {args.palette})", file=sys.stderr)
        return

    try:
        land.run()
    except KeyboardInterrupt:
        sys.stdout.write(SHOW + RESET + "\n")


if __name__ == "__main__":
    main()

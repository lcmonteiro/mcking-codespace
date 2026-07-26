#!/usr/bin/env python3
"""
ocean.py — Terminal Ocean Surface Simulator 🌊🌙
=================================================
Animated ocean waves with dynamic sky, celestial bodies,
clouds, seabirds, and atmospheric colour palettes.

Companion piece to nocturne.py and aurora.py — the ocean
trilogy of terminal atmospherics.

Usage:
    python ocean.py

Controls:
    q/ESC  — quit
    1-5    — palette presets (Sunset, Moonlit, Dawn, Storm, Tropical)
    +/-    — speed up / slow down
    w      — toggle wind direction
    s      — toggle sea state (calm / moderate / rough)
    c      — cycle palettes continuously
    SPACE  — pause/resume
    r      — reset to defaults

Zero external dependencies. Pure stdlib.
ANSI truecolor required (modern terminals only).
"""

import io
import logging
import math
import os
import random
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Force UTF-8 for stdout so Unicode renders on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
elif hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


# ── Palette ────────────────────────────────────────────────────────────────────

@dataclass
class SkyPalette:
    """A colour palette for sky, water, and highlights."""
    name: str
    sky_top: Tuple[int, int, int]       # top of sky
    sky_mid: Tuple[int, int, int]       # middle of sky
    sky_low: Tuple[int, int, int]       # near horizon
    horizon: Tuple[int, int, int]       # horizon line
    water_deep: Tuple[int, int, int]    # deep water
    water_mid: Tuple[int, int, int]     # mid water
    water_surface: Tuple[int, int, int] # surface / wave crests
    wave_char: str                      # primary wave character
    foam_char: str                      # foam / crest character
    star_color: Tuple[int, int, int]    # star colour
    moon_color: Tuple[int, int, int]    # moon / sun colour
    cloud_color: Tuple[int, int, int]   # cloud colour
    bird_color: Tuple[int, int, int]    # seabird colour
    reflection_char: str                # water reflection character


PALETTES = [
    SkyPalette(
        name="🌅 Sunset",
        sky_top=(25, 10, 60),
        sky_mid=(180, 60, 30),
        sky_low=(255, 140, 50),
        horizon=(255, 200, 100),
        water_deep=(20, 30, 80),
        water_mid=(180, 80, 40),
        water_surface=(255, 160, 60),
        wave_char='~', foam_char='≈',
        star_color=(255, 255, 200),
        moon_color=(255, 180, 80),
        cloud_color=(200, 100, 60),
        bird_color=(60, 20, 40),
        reflection_char='║',
    ),
    SkyPalette(
        name="🌙 Moonlit",
        sky_top=(5, 5, 20),
        sky_mid=(15, 15, 45),
        sky_low=(25, 30, 70),
        horizon=(40, 50, 100),
        water_deep=(8, 12, 35),
        water_mid=(20, 30, 80),
        water_surface=(60, 80, 150),
        wave_char='~', foam_char='≈',
        star_color=(200, 200, 255),
        moon_color=(220, 220, 200),
        cloud_color=(30, 30, 60),
        bird_color=(20, 20, 50),
        reflection_char='│',
    ),
    SkyPalette(
        name="🌅 Dawn",
        sky_top=(40, 20, 80),
        sky_mid=(120, 60, 140),
        sky_low=(255, 150, 120),
        horizon=(255, 200, 150),
        water_deep=(30, 20, 60),
        water_mid=(100, 50, 100),
        water_surface=(200, 130, 120),
        wave_char='~', foam_char='≈',
        star_color=(255, 220, 255),
        moon_color=(255, 200, 150),
        cloud_color=(180, 100, 140),
        bird_color=(80, 40, 80),
        reflection_char='║',
    ),
    SkyPalette(
        name="⛈️  Storm",
        sky_top=(15, 15, 25),
        sky_mid=(40, 40, 55),
        sky_low=(70, 75, 90),
        horizon=(100, 105, 120),
        water_deep=(15, 20, 35),
        water_mid=(40, 50, 75),
        water_surface=(80, 95, 120),
        wave_char='~', foam_char='░',
        star_color=(180, 180, 200),
        moon_color=(200, 200, 210),
        cloud_color=(60, 60, 75),
        bird_color=(30, 30, 45),
        reflection_char='│',
    ),
    SkyPalette(
        name="🏖️  Tropical",
        sky_top=(10, 80, 160),
        sky_mid=(40, 140, 210),
        sky_low=(100, 200, 240),
        horizon=(180, 230, 255),
        water_deep=(10, 60, 120),
        water_mid=(30, 120, 190),
        water_surface=(80, 180, 230),
        wave_char='~', foam_char='≈',
        star_color=(255, 255, 240),
        moon_color=(255, 240, 180),
        cloud_color=(220, 240, 255),
        bird_color=(40, 60, 80),
        reflection_char='║',
    ),
]


# ── Data Structures ────────────────────────────────────────────────────────────

@dataclass
class Star:
    x: int
    y: int
    brightness: float
    twinkle_speed: float
    twinkle_phase: float


@dataclass
class Cloud:
    x: float
    y: int
    width: int
    speed: float
    density: float  # 0-1, how opaque


@dataclass
class Seabird:
    x: float
    y: int
    wing_phase: float
    speed: float
    direction: int  # 1 or -1


@dataclass
class WaveLayer:
    """A single sine wave layer for the ocean surface."""
    amplitude: float
    frequency: float
    speed: float
    phase: float
    char: str


@dataclass
class ShootingStar:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    active: bool = False


@dataclass
class OceanState:
    """Complete state for the ocean simulation."""
    width: int = 80
    height: int = 24
    time: float = 0.0
    speed: float = 1.0
    paused: bool = False
    auto_cycle: bool = False
    palette_idx: int = 0
    sea_state: int = 1          # 0=calm, 1=moderate, 2=rough
    wind_dir: int = 1           # 1=right, -1=left
    horizon_row: int = 0        # set during init
    sky_rows: int = 0           # rows for sky above horizon
    water_rows: int = 0         # rows for water below horizon
    stars: List[Star] = field(default_factory=list)
    clouds: List[Cloud] = field(default_factory=list)
    birds: List[Seabird] = field(default_factory=list)
    wave_layers: List[WaveLayer] = field(default_factory=list)
    shooting_star: ShootingStar = field(default_factory=lambda: ShootingStar(0, 0, 0, 0, 0, 0))


# ── Helpers ────────────────────────────────────────────────────────────────────

def lerp_color(a: Tuple[int, int, int], b: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    """Linearly interpolate between two RGB colours."""
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def ansi_fg(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"


def ansi_bg(r: int, g: int, b: int) -> str:
    return f"\033[48;2;{r};{g};{b}m"


def ansi_reset() -> str:
    return "\033[0m"


def get_terminal_size() -> Tuple[int, int]:
    """Get terminal size, fallback to 80x24."""
    try:
        size = os.get_terminal_size()
        return size.columns, size.lines
    except (OSError, ValueError):
        return 80, 24


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ── Initialization ─────────────────────────────────────────────────────────────

def init_state(state: OceanState) -> OceanState:
    """Populate stars, clouds, birds, and wave layers."""
    w, h = get_terminal_size()
    state.width = w
    state.height = h
    state.horizon_row = h // 3
    state.sky_rows = state.horizon_row
    state.water_rows = h - state.horizon_row - 1

    # Stars
    state.stars = []
    for _ in range(w * 2):
        state.stars.append(Star(
            x=random.randint(0, w - 1),
            y=random.randint(0, max(1, state.sky_rows - 2)),
            brightness=random.uniform(0.3, 1.0),
            twinkle_speed=random.uniform(1.5, 4.0),
            twinkle_phase=random.uniform(0, 2 * math.pi),
        ))

    # Clouds
    state.clouds = []
    for _ in range(random.randint(3, 6)):
        state.clouds.append(Cloud(
            x=random.uniform(-10, w + 10),
            y=random.randint(1, max(2, state.sky_rows // 3)),
            width=random.randint(5, 12),
            speed=random.uniform(0.02, 0.08),
            density=random.uniform(0.3, 0.8),
        ))

    # Seabirds
    state.birds = []
    for _ in range(random.randint(1, 3)):
        state.birds.append(Seabird(
            x=random.uniform(0, w),
            y=random.randint(state.sky_rows // 3, state.sky_rows - 2),
            wing_phase=random.uniform(0, 2 * math.pi),
            speed=random.uniform(0.3, 0.8),
            direction=random.choice([-1, 1]),
        ))

    # Wave layers
    update_waves(state)

    # Shooting star (inactive)
    state.shooting_star = ShootingStar(0, 0, 0, 0, 0, 0, False)

    return state


def update_waves(state: OceanState):
    """Recreate wave layers based on sea state."""
    sea_configs = [
        # calm
        [
            WaveLayer(0.5, 0.15, 0.8, 0, '~'),
            WaveLayer(0.3, 0.1, 0.5, 1.0, '≈'),
        ],
        # moderate
        [
            WaveLayer(1.0, 0.12, 1.0, 0, '~'),
            WaveLayer(0.6, 0.08, 0.7, 1.5, '≈'),
            WaveLayer(0.4, 0.2, 1.3, 3.0, '~'),
        ],
        # rough
        [
            WaveLayer(1.8, 0.1, 1.5, 0, '~'),
            WaveLayer(1.0, 0.06, 1.0, 2.0, '≈'),
            WaveLayer(0.7, 0.15, 1.8, 4.0, '≈'),
            WaveLayer(0.5, 0.25, 2.2, 1.0, '~'),
        ],
    ]
    state.wave_layers = sea_configs[state.sea_state]


# ── Update ─────────────────────────────────────────────────────────────────────

def update(state: OceanState, dt: float):
    """Advance simulation by dt seconds."""
    if state.paused:
        return

    state.time += dt * state.speed

    t = state.time
    w = state.width

    # Stars twinkle (no position change, just managed via brightness in render)

    # Clouds drift
    for cloud in state.clouds:
        cloud.x += cloud.speed * state.wind_dir * dt * state.speed
        if state.wind_dir > 0 and cloud.x > w + 15:
            cloud.x = -cloud.width - 5
        elif state.wind_dir < 0 and cloud.x < -15:
            cloud.x = w + cloud.width + 5

    # Birds fly
    for bird in state.birds:
        bird.x += bird.speed * bird.direction * dt * state.speed * 3
        bird.wing_phase += dt * 5.0
        if bird.x > w + 5:
            bird.x = -3
        elif bird.x < -5:
            bird.x = w + 3

    # Shooting star
    ss = state.shooting_star
    if ss.active:
        ss.x += ss.vx * dt
        ss.y += ss.vy * dt
        ss.life -= dt
        if ss.life <= 0:
            ss.active = False
    elif random.random() < 0.003 * dt * 60:
        # Spawn new shooting star
        ss.x = random.uniform(w * 0.2, w * 0.8)
        ss.y = random.uniform(0, max(1, state.sky_rows // 2))
        angle = random.uniform(0.3, 0.8) * math.pi
        speed = random.uniform(15, 30)
        ss.vx = math.cos(angle) * speed
        ss.vy = math.sin(angle) * speed
        ss.life = random.uniform(0.3, 0.6)
        ss.max_life = ss.life
        ss.active = True


# ── Rendering ──────────────────────────────────────────────────────────────────

def render_frame(state: OceanState) -> str:
    """Render one complete frame as a string with ANSI colour."""
    pal = PALETTES[state.palette_idx]
    w, h = state.width, state.height
    t = state.time
    lines = []
    buffer = []

    horizon = state.horizon_row

    # ── Sky ──
    for row in range(horizon):
        row_ratio = row / max(1, horizon - 1)

        # Sky gradient
        if row_ratio < 0.5:
            sky_col = lerp_color(pal.sky_top, pal.sky_mid, row_ratio * 2)
        else:
            sky_col = lerp_color(pal.sky_mid, pal.sky_low, (row_ratio - 0.5) * 2)

        # Background colour for sky
        buffer.append(ansi_bg(*sky_col))

        line_chars = [' '] * w

        # Stars (only visible in upper sky, and depend on palette)
        show_stars = pal.sky_top[0] < 50  # dark sky = show stars
        if show_stars:
            for star in state.stars:
                if star.y == row and 0 <= star.x < w:
                    twinkle = max(0, math.sin(t * star.twinkle_speed + star.twinkle_phase)) ** 3
                    brightness = star.brightness * (0.3 + 0.7 * twinkle)
                    if brightness > 0.4:
                        r = int(pal.star_color[0] * brightness)
                        g = int(pal.star_color[1] * brightness)
                        b = int(pal.star_color[2] * brightness)
                        char = random.choice(['·', '✦', '✧', '·', '·'])
                        buffer.append(ansi_fg(r, g, b))
                        line_chars[star.x] = char

        # Moon / sun position
        moon_x = int(w * 0.75 + math.sin(t * 0.02) * 3)
        moon_y = max(1, horizon // 3)
        if row == moon_y:
            # Moon glow
            for dx in range(-2, 3):
                mx = moon_x + dx
                if 0 <= mx < w:
                    dist = abs(dx)
                    glow = max(0, 1.0 - dist * 0.4)
                    r = int(pal.moon_color[0] * glow)
                    g = int(pal.moon_color[1] * glow)
                    b = int(pal.moon_color[2] * glow)
                    buffer.append(ansi_fg(r, g, b))
                    if dist == 0:
                        line_chars[mx] = '◉'
                    elif dist == 1:
                        line_chars[mx] = '○'
                    else:
                        line_chars[mx] = '·'

        # Clouds
        for cloud in state.clouds:
            if cloud.y == row:
                cx_start = int(cloud.x)
                for dx in range(cloud.width):
                    cx = cx_start + dx
                    if 0 <= cx < w and line_chars[cx] == ' ':
                        # Cloud density varies across width
                        center_dist = abs(dx - cloud.width / 2) / (cloud.width / 2)
                        density = cloud.density * (1.0 - center_dist * 0.5)
                        cr = int(pal.cloud_color[0] * density + sky_col[0] * (1 - density))
                        cg = int(pal.cloud_color[1] * density + sky_col[1] * (1 - density))
                        cb = int(pal.cloud_color[2] * density + sky_col[2] * (1 - density))
                        buffer.append(ansi_fg(cr, cg, cb))
                        cloud_chars = ['░', '▒', '▓', '▒', '░']
                        line_chars[cx] = cloud_chars[min(dx, len(cloud_chars) - 1)]

        # Seabirds
        for bird in state.birds:
            if bird.y == row:
                bx = int(bird.x)
                if 0 <= bx < w and line_chars[bx] == ' ':
                    wing = math.sin(bird.wing_phase)
                    bird_char = '˘' if wing > 0 else '∧'
                    buffer.append(ansi_fg(*pal.bird_color))
                    line_chars[bx] = bird_char
                    if 0 <= bx + 1 < w:
                        line_chars[bx + 1] = '˘' if wing < 0 else '∧'

        # Shooting star
        ss = state.shooting_star
        if ss.active and 0 <= int(ss.x) < w and 0 <= int(ss.y) < h:
            sx, sy = int(ss.x), int(ss.y)
            if sy == row and 0 <= sx < w:
                trail_len = 4
                for i in range(trail_len):
                    tx = sx - int(ss.vx * i * 0.02)
                    if 0 <= tx < w:
                        alpha = 1.0 - i / trail_len
                        brightness = ss.life / ss.max_life * alpha
                        r = int(255 * brightness)
                        g = int(255 * brightness)
                        b = int(200 * brightness)
                        buffer.append(ansi_fg(r, g, b))
                        line_chars[tx] = '·' if i > 0 else '★'

        # Horizon line
        if row == horizon - 1:
            for x in range(w):
                h_col = lerp_color(pal.sky_low, pal.horizon, 0.5)
                buffer.append(ansi_fg(*pal.horizon))
                line_chars[x] = '─'

        # Build line
        current_fg = None
        for i, ch in enumerate(line_chars):
            buffer.append(ch)
        buffer.append(ansi_reset())
        lines.append(''.join(buffer))
        buffer = []

    # ── Horizon separator ──
    buffer.append(ansi_fg(*pal.horizon))
    buffer.append(ansi_bg(*pal.horizon))
    buffer.append('═' * w)
    buffer.append(ansi_reset())
    lines.append(''.join(buffer))
    buffer = []

    # ── Water ──
    for row in range(state.water_rows):
        water_ratio = row / max(1, state.water_rows - 1)
        row_in_water = horizon + 1 + row

        # Water colour gradient
        if water_ratio < 0.4:
            water_col = lerp_color(pal.water_surface, pal.water_mid, water_ratio / 0.4)
        else:
            water_col = lerp_color(pal.water_mid, pal.water_deep, (water_ratio - 0.4) / 0.6)

        buffer.append(ansi_bg(*water_col))

        line_chars = [' '] * w
        fg_colors = [None] * w

        # Wave layers
        for wl in state.wave_layers:
            wave_offset = wl.speed * state.wind_dir * t * 2
            for x in range(w):
                wave_y = wl.amplitude * math.sin(
                    (x * wl.frequency) + wave_offset + wl.phase
                )
                # Wave character appears at the wave crest position
                crest_y = row_in_water + wave_y
                # Check if this row is near a wave crest
                nearest_crest = round(crest_y)
                dist_to_crest = abs(crest_y - row_in_water)

                if dist_to_crest < 0.5:
                    # This is a wave surface row
                    blend = 1.0 - dist_to_crest / 0.5
                    # Wave crest character
                    char = wl.char if blend > 0.7 else pal.foam_char
                    wave_col = lerp_color(water_col, pal.water_surface, blend * 0.6)
                    fg_colors[x] = wave_col
                    line_chars[x] = char

        # Moon / sun reflection
        if row < 4:  # only near surface
            moon_x = int(w * 0.75 + math.sin(t * 0.02) * 3)
            for dx in range(-1, 2):
                rx = moon_x + dx + int(math.sin(t * 3 + row) * 1.5)
                if 0 <= rx < w and line_chars[rx] == ' ':
                    reflect_col = lerp_color(
                        pal.water_surface,
                        pal.moon_color,
                        0.4 * (1 - row / 4)
                    )
                    fg_colors[rx] = reflect_col
                    line_chars[rx] = pal.reflection_char

        # Foam at surface (first few water rows)
        if row < 3:
            for x in range(w):
                noise = math.sin(x * 0.5 + t * 2) * 0.5 + 0.5
                if noise > 0.7 and line_chars[x] == ' ':
                    foam_col = lerp_color(pal.water_surface, (255, 255, 255), 0.3)
                    fg_colors[x] = foam_col
                    line_chars[x] = '·'

        # Build line
        for i, ch in enumerate(line_chars):
            if fg_colors[i]:
                buffer.append(ansi_fg(*fg_colors[i]))
            buffer.append(ch)
        buffer.append(ansi_reset())
        lines.append(''.join(buffer))
        buffer = []

    # ── Info bar ──
    info = f" {pal.name} │ 🌊 {['Calm', 'Moderate', 'Rough'][state.sea_state]} │ 💨 {'→' if state.wind_dir > 0 else '←'} │ ⏱ {state.speed:.1f}x"
    padding = w - len(info) - 2
    if padding < 0:
        padding = 0
    buffer.append(ansi_bg(20, 20, 30))
    buffer.append(ansi_fg(150, 160, 180))
    buffer.append(f" {info}{' ' * padding} ")
    buffer.append(ansi_reset())
    lines.append(''.join(buffer))
    buffer = []

    # Control hint
    ctrl = " [1-5] palette  [w] wind  [s] sea  [+/-] speed  [SPACE] pause  [c] cycle  [q] quit"
    ctrl_padding = w - len(ctrl) - 1
    if ctrl_padding < 0:
        ctrl_padding = 0
    buffer.append(ansi_bg(15, 15, 25))
    buffer.append(ansi_fg(100, 100, 120))
    buffer.append(f"{ctrl}{' ' * ctrl_padding}")
    buffer.append(ansi_reset())
    lines.append(''.join(buffer))

    return '\r\n'.join(lines)


# ── Input ──────────────────────────────────────────────────────────────────────

def read_input_nonblocking():
    """Read a single keypress if available (non-blocking)."""
    import select
    if sys.platform == 'win32':
        import msvcrt
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch in ('\x00', '\xe0'):
                ch2 = msvcrt.getwch()
                if ch2 == 'H': return 'UP'
                if ch2 == 'P': return 'DOWN'
                if ch2 == 'K': return 'LEFT'
                if ch2 == 'R': return 'RIGHT'
                return None
            return ch
    else:
        if select.select([sys.stdin], [], [], 0)[0]:
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                # Check for escape sequence
                if select.select([sys.stdin], [], [], 0.05)[0]:
                    seq = sys.stdin.read(1)
                    if seq == '[':
                        if select.select([sys.stdin], [], [], 0.05)[0]:
                            code = sys.stdin.read(1)
                            if code == 'A': return 'UP'
                            if code == 'B': return 'DOWN'
                            if code == 'C': return 'RIGHT'
                            if code == 'D': return 'LEFT'
                return 'ESC'
            return ch
    return None


def handle_input(state: OceanState, key: str) -> bool:
    """Handle a keypress. Returns False to quit."""
    if key is None:
        return True

    if key in ('q', 'Q', 'ESC'):
        return False

    if key == ' ':
        state.paused = not state.paused
    elif key in ('+', '='):
        state.speed = min(5.0, state.speed + 0.25)
    elif key == '-':
        state.speed = max(0.25, state.speed - 0.25)
    elif key == 'c':
        state.auto_cycle = not state.auto_cycle
    elif key == 'r':
        state.speed = 1.0
        state.paused = False
        state.auto_cycle = False
        state.palette_idx = 0
        state.sea_state = 1
        state.wind_dir = 1
    elif key == 'w':
        state.wind_dir *= -1
    elif key == 's':
        state.sea_state = (state.sea_state + 1) % 3
        update_waves(state)
    elif key in ('1', '2', '3', '4', '5'):
        idx = int(key) - 1
        if 0 <= idx < len(PALETTES):
            state.palette_idx = idx
            state.auto_cycle = False
    elif key == 'UP':
        state.speed = min(5.0, state.speed + 0.25)
    elif key == 'DOWN':
        state.speed = max(0.25, state.speed - 0.25)

    return True


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    state = OceanState()
    state = init_state(state)

    # Hide cursor, clear screen
    sys.stdout.write('\033[?25l\033[2J\033[H')
    sys.stdout.flush()

    last_time = time.monotonic()
    cycle_timer = 0.0

    try:
        while True:
            now = time.monotonic()
            dt = now - last_time
            last_time = now

            # Auto-cycle palettes
            if state.auto_cycle:
                cycle_timer += dt
                if cycle_timer > 8.0:
                    cycle_timer = 0.0
                    state.palette_idx = (state.palette_idx + 1) % len(PALETTES)

            # Read input
            key = read_input_nonblocking()
            if not handle_input(state, key):
                break

            # Update simulation
            update(state, dt)

            # Render
            frame = render_frame(state)
            sys.stdout.write(f'\033[H{frame}')
            sys.stdout.flush()

            # Frame rate cap (~30 FPS)
            elapsed = time.monotonic() - now
            sleep_time = max(0, 0.033 - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        pass
    finally:
        # Show cursor, reset colours
        sys.stdout.write('\033[?25h\033[0m\033[2J\033[H')
        sys.stdout.flush()


if __name__ == '__main__':
    main()

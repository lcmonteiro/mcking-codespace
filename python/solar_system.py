#!/usr/bin/env python3
"""
Solar System — Terminal Orbital Simulator 🌌🪐
==============================================
Top-down ASCII view of the solar system with Keplerian orbits,
planet trails, interactive zoom/speed, and real orbital ratios.

Controls:
  +/-     Speed up / slow down
  z/Z     Zoom in / out
  t       Toggle orbital trails
  i       Toggle info panel
  arrows  Pan view
  SPACE   Pause / Resume
  q/Esc   Quit

Keys are case-insensitive. All values respect real Keplerian mechanics
(period ∝ a^1.5, semi-major axes compressed for terminal display).
"""

import math
import sys
import time
import curses
from typing import List, Tuple, Optional

# ── Encoding fix for Windows terminals ──
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Colour palettes ──
PALETTES = {
    "realistic": {
        "bg":       (8, 8, 12),
        "sun":      (255, 220, 50),
        "sun_glow": (200, 160, 30),
        "mercury":  (169, 169, 169),
        "venus":    (230, 200, 100),
        "earth":    (80, 160, 255),
        "mars":     (200, 80, 50),
        "jupiter":  (200, 170, 100),
        "saturn":   (210, 190, 140),
        "uranus":   (150, 220, 220),
        "neptune":  (70, 100, 200),
        "moon":     (200, 200, 200),
        "belt":     (100, 90, 80),
        "trail":    (50, 50, 60),
        "grid":     (25, 25, 35),
        "text":     (180, 180, 200),
        "highlight":(255, 200, 80),
    },
    "neon": {
        "bg":       (5, 5, 15),
        "sun":      (255, 255, 0),
        "sun_glow": (255, 200, 0),
        "mercury":  (200, 200, 200),
        "venus":    (255, 150, 50),
        "earth":    (0, 200, 255),
        "mars":     (255, 50, 0),
        "jupiter":  (255, 180, 0),
        "saturn":   (200, 150, 255),
        "uranus":   (0, 255, 200),
        "neptune":  (100, 100, 255),
        "moon":     (180, 180, 180),
        "belt":     (150, 150, 50),
        "trail":    (30, 30, 80),
        "grid":     (20, 20, 50),
        "text":     (200, 200, 255),
        "highlight":(255, 100, 255),
    },
    "retro": {
        "bg":       (0, 0, 0),
        "sun":      (255, 255, 0),
        "sun_glow": (200, 200, 0),
        "mercury":  (0, 255, 0),
        "venus":    (0, 200, 0),
        "earth":    (0, 255, 100),
        "mars":     (255, 0, 0),
        "jupiter":  (255, 100, 0),
        "saturn":   (255, 200, 0),
        "uranus":   (0, 255, 255),
        "neptune":  (0, 100, 255),
        "moon":     (0, 200, 0),
        "belt":     (100, 100, 0),
        "trail":    (0, 40, 0),
        "grid":     (0, 30, 0),
        "text":     (0, 255, 0),
        "highlight":(0, 255, 100),
    },
}

# ── Planet data ──
# name, semi-major axis (AU), orbital period (Earth years), eccentricity,
# display char, radius (terminal units), colour key, moons
# Orbital periods:  Mercury 0.241, Venus 0.615, Earth 1.0, Mars 1.88,
# Jupiter 11.86, Saturn 29.46, Uranus 84.01, Neptune 164.8
PLANETS = [
    ("Mercury",  0.387,  0.241, 0.2056, "·", 1, "mercury", 0),
    ("Venus",    0.723,  0.615, 0.0068, "o", 1, "venus",   0),
    ("Earth",    1.000,  1.000, 0.0167, "⊕", 1, "earth",   1),
    ("Mars",     1.524,  1.881, 0.0934, "•", 1, "mars",    2),
    ("Jupiter",  3.000, 11.86,  0.0485, "O", 2, "jupiter", 4),
    ("Saturn",   4.000, 29.46,  0.0556, "()", 3, "saturn", 3),
    ("Uranus",   5.200, 84.01,  0.0463, "o", 2, "uranus",  1),
    ("Neptune",  6.500, 164.8,  0.0095, "·", 2, "neptune", 1),
]

# Asteroid belt between Mars and Jupiter
ASTEROID_INNER = 2.2   # AU
ASTEROID_OUTER = 2.8   # AU
NUM_ASTEROIDS = 120

# Time compression: 1 second = BASE_SPEED Earth years
BASE_SPEED = 0.02

# Max trail length per planet
MAX_TRAIL = 60


def rgb_to_ansi(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"


def rgb_bg(r: int, g: int, b: int) -> str:
    return f"\033[48;2;{r};{g};{b}m"


RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"


def kepler_position(a: float, e: float, mean_anomaly: float) -> Tuple[float, float]:
    """Solve Kepler's equation via Newton-Raphson, return (x, y) in AU."""
    E = mean_anomaly
    for _ in range(15):
        dE = (E - e * math.sin(E) - mean_anomaly) / (1 - e * math.cos(E))
        E -= dE
        if abs(dE) < 1e-9:
            break
    # True anomaly
    theta = 2 * math.atan2(
        math.sqrt(1 + e) * math.sin(E / 2),
        math.sqrt(1 - e) * math.cos(E / 2),
    )
    r = a * (1 - e * math.cos(E))
    return r * math.cos(theta), r * math.sin(theta)


def init_asteroids() -> List[Tuple[float, float, float]]:
    """Create asteroid belt: list of (semi-major axis, eccentricity, phase)."""
    import random
    random.seed(42)
    asteroids = []
    for _ in range(NUM_ASTEROIDS):
        a = ASTEROID_INNER + random.random() * (ASTEROID_OUTER - ASTEROID_INNER)
        ecc = random.random() * 0.3
        phase = random.random() * 2 * math.pi
        asteroids.append((a, ecc, phase))
    return asteroids


def main(stdscr: "curses.window"):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(50)  # ~20 FPS

    # Colours
    if curses.can_change_color():
        curses.start_color()
        curses.use_default_colors()

    palette_key = "realistic"
    pal = PALETTES[palette_key]
    palette_names = list(PALETTES.keys())
    palette_idx = 0

    # State
    speed_mult = 1.0
    zoom = 8.0          # AU per screen half-height
    show_trails = True
    show_info = True
    paused = False
    pan_x, pan_y = 0.0, 0.0
    elapsed_years = 0.0

    # Initial angles
    angles = [0.0] * len(PLANETS)
    trails: List[List[Tuple[int, int]]] = [[] for _ in PLANETS]
    asteroids = init_asteroids()

    # Planet selection for info panel
    selected_planet = 2  # Earth by default

    def render():
        nonlocal zoom
        try:
            term_h, term_w = stdscr.getmaxyx()
        except Exception:
            term_h, term_w = 40, 80

        # Buffer: (char, fg_r, fg_g, fg_b, bg_r, bg_g, bg_b)
        screen = [[' '] * term_w for _ in range(term_h)]
        fg_buf  = [[(200, 200, 200)] * term_w for _ in range(term_h)]
        bg_buf  = [[pal["bg"]] * term_w for _ in range(term_h)]

        cx = term_w // 2
        cy = term_h // 2

        # Scale: 1 AU = (term_h / 2) / zoom  (in character cells)
        # But characters are ~2x tall as wide, so compress x
        au_per_row = zoom
        au_per_col = zoom * 2  # characters are ~half width in real coords

        def to_screen(x_au: float, y_au: float) -> Optional[Tuple[int, int]]:
            """Convert AU coords to screen (col, row), or None if off-screen."""
            sx = cx + int((x_au - pan_x) / au_per_col)
            sy = cy + int((y_au - pan_y) / au_per_row)
            if 0 <= sx < term_w and 0 <= sy < term_h:
                return sx, sy
            return None

        # ── Draw grid rings ──
        for ring_au in range(1, int(zoom) + 2):
            grid_r, grid_g, grid_b = pal["grid"]
            # Horizontal-ish ring at this distance
            for angle_deg in range(0, 360, 3):
                rad = math.radians(angle_deg)
                px = ring_au * math.cos(rad)
                py = ring_au * math.sin(rad)
                pos = to_screen(px, py)
                if pos:
                    sx, sy = pos
                    if screen[sy][sx] == ' ':
                        screen[sy][sx] = '·'
                        fg_buf[sy][sx] = (grid_r, grid_g, grid_b)

        # ── Draw asteroid belt ──
        belt_r, belt_g, belt_b = pal["belt"]
        for a, ecc, phase in asteroids:
            period = a ** 1.5  # Kepler's 3rd law (relative)
            mean_anom = ((elapsed_years / period) * 2 * math.pi + phase) % (2 * math.pi)
            x, y = kepler_position(a, ecc, mean_anom)
            pos = to_screen(x, y)
            if pos:
                sx, sy = pos
                if screen[sy][sx] == ' ':
                    screen[sy][sx] = ','
                    fg_buf[sy][sx] = (belt_r, belt_g, belt_b)

        # ── Draw trails ──
        trail_r, trail_g, trail_b = pal["trail"]
        if show_trails:
            for i, trail in enumerate(trails):
                for j, (tx, ty) in enumerate(trail):
                    if 0 <= tx < term_w and 0 <= ty < term_h:
                        if screen[ty][tx] == ' ':
                            # Fade older trail points
                            fade = max(0.2, j / len(trail))
                            r2 = int(trail_r * fade + pal["bg"][0] * (1 - fade))
                            g2 = int(trail_g * fade + pal["bg"][1] * (1 - fade))
                            b2 = int(trail_b * fade + pal["bg"][2] * (1 - fade))
                            screen[ty][tx] = '·'
                            fg_buf[ty][tx] = (r2, g2, b2)

        # ── Draw planets ──
        for i, (name, a, period, ecc, char, radius, col_key, _) in enumerate(PLANETS):
            period_years = period
            mean_anom = ((elapsed_years / period_years) * 2 * math.pi + angles[i]) % (2 * math.pi)
            x, y = kepler_position(a, ecc, mean_anom)
            pos = to_screen(x, y)
            if pos:
                sx, sy = pos
                cr, cg, cb = pal[col_key]
                # Draw planet character
                if 0 <= sx < term_w and 0 <= sy < term_h:
                    screen[sy][sx] = char
                    fg_buf[sy][sx] = (cr, cg, cb)

                # Draw rings for Saturn
                if name == "Saturn" and radius >= 3:
                    ring_char = "═"
                    for dx in range(-radius - 1, radius + 2):
                        rx = sx + dx
                        ry = sy
                        if 0 <= rx < term_w and 0 <= ry < term_h:
                            if screen[ry][rx] == ' ':
                                screen[ry][rx] = ring_char
                                fg_buf[ry][rx] = (cr // 2, cg // 2, cb // 2)

                # Moon for Earth
                if name == "Earth" and _ > 0:
                    moon_angle = elapsed_years * 13.37  # Moon orbits ~13x/year
                    moon_dist = 0.15  # AU (compressed)
                    mx = x + moon_dist * math.cos(moon_angle)
                    my = y + moon_dist * math.sin(moon_angle)
                    mpos = to_screen(mx, my)
                    if mpos:
                        msx, msy = mpos
                        if 0 <= msx < term_w and 0 <= msy < term_h:
                            screen[msy][msx] = "°"
                            fg_buf[msy][msx] = pal["moon"]

                # Update trail
                if show_trails and pos:
                    trail_pos = to_screen(x, y)
                    if trail_pos:
                        trails[i].append(trail_pos)
                        if len(trails[i]) > MAX_TRAIL:
                            trails[i] = trails[i][-MAX_TRAIL:]

        # ── Draw Sun ──
        sun_r, sun_g, sun_b = pal["sun"]
        sun_glow_r, sun_glow_g, sun_glow_b = pal["sun_glow"]
        sun_pos = to_screen(0, 0)
        if sun_pos:
            ssx, ssy = sun_pos
            # Glow (3x3)
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    gx, gy = ssx + dx, ssy + dy
                    if 0 <= gx < term_w and 0 <= gy < term_h:
                        if screen[gy][gx] == ' ' or screen[gy][gx] == '·':
                            dist = math.sqrt(dx * dx + dy * dy)
                            if dist < 1.5:
                                screen[gy][gx] = '█'
                                fg_buf[gy][gx] = (sun_glow_r, sun_glow_g, sun_glow_b)
            # Core
            screen[ssy][ssx] = '☀'
            fg_buf[ssy][ssx] = (sun_r, sun_g, sun_b)

        # ── Render to terminal ──
        lines = []
        lines.append("\033[H")  # Move to top-left

        for row in range(term_h):
            line_parts = []
            for col in range(term_w):
                ch = screen[row][col]
                fg = fg_buf[row][col]
                bg = pal["bg"]
                line_parts.append(f"{rgb_to_ansi(*fg)}{ch}")
            lines.append(''.join(line_parts) + RESET)

        # ── Info panel ──
        if show_info:
            info_y = 1
            info_x = 2
            # Title
            if info_y < term_h:
                title = f"🌌 SOLAR SYSTEM  {DIM}[Speed: {speed_mult:.1f}x | Zoom: {zoom:.1f} AU | {'⏸ PAUSED' if paused else '▶ RUNNING'}]{RESET}"
                lines[info_y] = lines[info_y][:info_x] + title[:term_w - info_x - 2] + RESET + lines[info_y][info_x + len(title):]

            # Planet list
            for i, (name, a, period, ecc, char, _, col_key, moons) in enumerate(PLANETS):
                if info_y + 2 + i >= term_h - 1:
                    break
                cr, cg, cb = pal[col_key]
                marker = f" {BOLD}▸{RESET}" if i == selected_planet else " "
                moon_str = f" 🌙×{moons}" if moons else ""
                orbit_info = f"{DIM}T={period:.2f}y  a={a:.3f}AU  e={ecc:.4f}{RESET}"
                planet_line = f"{marker} {rgb_to_ansi(cr, cg, cb)}{char} {name}{RESET}{moon_str} {orbit_info}"
                # Overlay on existing line
                pad = " " * info_x
                if info_y + 2 + i < len(lines):
                    lines[info_y + 2 + i] = pad + planet_line + RESET

            # Keyboard hints at bottom
            hint_y = term_h - 2
            if hint_y > 0 and hint_y < len(lines):
                hints = f"{DIM}[+/-] Speed  [z/Z] Zoom  [t] Trails  [i] Info  [←→] Select  [SPACE] Pause  [c] Palette  [q] Quit{RESET}"
                lines[hint_y] = "\033[K" + hints[:term_w - 2]

            # Selected planet detail
            if selected_planet < len(PLANETS):
                det_y = term_h - 3
                if det_y > 0 and det_y < len(lines):
                    name, a, period, ecc, char, _, col_key, moons = PLANETS[selected_planet]
                    # Current position
                    mean_anom = ((elapsed_years / period) * 2 * math.pi + angles[selected_planet]) % (2 * math.pi)
                    x, y = kepler_position(a, ecc, mean_anom)
                    r_now = a * (1 - ecc * ecc) / (1 + ecc * math.cos(mean_anom))
                    vel = math.sqrt(2.0 / r_now - 1.0 / a)  # relative velocity (vis-viva)
                    detail = f"  {rgb_to_ansi(*pal[col_key])}{BOLD}{name}{RESET}  r={r_now:.3f}AU  v={vel:.3f}u/y  θ={math.degrees(mean_anom):.1f}°  ⏱ {elapsed_years:.2f}y"
                    lines[det_y] = "\033[K" + detail[:term_w - 2]

        # Write everything
        sys.stdout.write(''.join(lines))
        sys.stdout.flush()

    try:
        # Track asteroid positions (need to update them each frame)
        while True:
            # ── Handle input ──
            try:
                key = stdscr.getch()
            except Exception:
                key = -1

            while key != -1:
                k = key if 32 <= key < 127 else -1
                if k != -1:
                    ch = chr(k)
                else:
                    ch = ''

                if ch in ('q', 'Q', '\x1b'):  # Esc or q
                    raise KeyboardInterrupt
                elif ch == '+':
                    speed_mult = min(100.0, speed_mult * 1.5)
                elif ch == '-' or ch == '_':
                    speed_mult = max(0.1, speed_mult / 1.5)
                elif ch == 'z':
                    zoom = max(1.0, zoom * 0.8)
                elif ch == 'Z':
                    zoom = min(30.0, zoom * 1.25)
                elif ch == 't':
                    show_trails = not show_trails
                    if not show_trails:
                        trails = [[] for _ in PLANETS]
                elif ch == 'i':
                    show_info = not show_info
                elif ch == ' ':
                    paused = not paused
                elif ch == 'c':
                    palette_idx = (palette_idx + 1) % len(palette_names)
                    palette_key = palette_names[palette_idx]
                    pal = PALETTES[palette_key]
                elif key == curses.KEY_LEFT:
                    pan_x -= zoom * 0.2
                elif key == curses.KEY_RIGHT:
                    pan_x += zoom * 0.2
                elif key == curses.KEY_UP:
                    pan_y -= zoom * 0.2
                elif key == curses.KEY_DOWN:
                    pan_y += zoom * 0.2
                elif ch == 'l' and selected_planet < len(PLANETS) - 1:
                    selected_planet += 1
                elif ch == 'h' and selected_planet > 0:
                    selected_planet -= 1
                elif key == curses.KEY_RESIZE:
                    pass

                try:
                    key = stdscr.getch()
                except Exception:
                    key = -1

            # ── Update simulation ──
            if not paused:
                dt = BASE_SPEED * speed_mult
                elapsed_years += dt
                # Update planet angles
                for i, (_, _, period, _, _, _, _, _) in enumerate(PLANETS):
                    angular_speed = (2 * math.pi) / period  # radians per year
                    angles[i] += angular_speed * dt

            # ── Render ──
            render()

    except KeyboardInterrupt:
        pass
    finally:
        # Restore terminal
        sys.stdout.write("\033[?25h")  # Show cursor
        sys.stdout.write("\033[0m")
        sys.stdout.write("\033[2J\033[H")  # Clear screen
        sys.stdout.flush()


if __name__ == '__main__':
    print(f"{RESET}\033[?25l")  # Hide cursor
    try:
        curses.wrapper(main)
    except Exception:
        print(f"{RESET}\033[?25h")
        raise

#!/usr/bin/env python3
"""
Nocturne — Terminal Atmospheric Scene Generator
================================================
Creates animated night landscapes with stars, moon, shooting stars,
meteor showers, and silhouette horizons.

Pure Python, zero dependencies. ANSI truecolor.
Press Ctrl+C to exit gracefully.
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

# ====================================================================================================
# ANSI Helpers
# ====================================================================================================


def fg(r: int, g: int, b: int) -> str:
    """Return ANSI truecolor foreground escape code."""
    return f"\033[38;2;{r};{g};{b}m"


def bg(r: int, g: int, b: int) -> str:
    """Return ANSI truecolor background escape code."""
    return f"\033[48;2;{r};{g};{b}m"


RESET   : str = "\033[0m"
HOME    : str = "\033[H"
HIDE    : str = "\033[?25l"
SHOW    : str = "\033[?25h"
SAVE    : str = "\033[s"
RESTORE : str = "\033[u"


# ====================================================================================================
# Constants
# ====================================================================================================

FPS     : int = 24
FRAME_S : float = 1.0 / FPS


# ====================================================================================================
# Dataclasses
# ====================================================================================================


@dataclass
class Star:
    """A twinkling star in the night sky."""
    x : float
    y : float
    phase : float           # phase offset for twinkle
    twinkle_speed : float   # how fast it twinkles
    base_brightness : float # 0-1
    size : int              # 1 or 2 (2 = bright star)
    hue_variance : float    # slight color variation


@dataclass
class ShootingStar:
    """A shooting star streaking across the sky."""
    x : float
    y : float
    dx : float
    dy : float
    life : float           # remaining life
    max_life : float
    tail_length : int
    color : Tuple[int, int, int]
    active : bool = True


@dataclass
class Moon:
    """The moon with a glow pulse phase."""
    x : float
    y : float
    phase : float


@dataclass
class Firefly:
    """A glowing firefly near the ground."""
    x : float
    y : float
    vx : float
    vy : float
    phase : float
    brightness : float


@dataclass
class Scene:
    """The complete night scene with all objects."""
    stars : List[Star] = field(default_factory=list)
    shooting_stars : List[ShootingStar] = field(default_factory=list)
    fireflies : List[Firefly] = field(default_factory=list)
    moon : Optional[Moon] = None
    time : float = 0.0
    horizon_y : float = 0.75  # fraction of height
    W : int = 120
    H : int = 40


# ====================================================================================================
# Terminal Helpers
# ====================================================================================================


def get_terminal_size() -> Tuple[int, int]:
    """Get terminal (columns, lines), fall back to 120x40."""
    try:
        import shutil
        w, h = shutil.get_terminal_size((120, 40))
        return w, h
    except Exception:
        return 120, 40


# ====================================================================================================
# Scene Generation
# ====================================================================================================


def make_stars(w: int, h: int, n: int, rng: random.Random) -> List[Star]:
    """Generate *n* stars across the sky."""
    stars: List[Star] = []
    for _ in range(n):
        x = rng.random() * w
        y = rng.random() * h * 0.72
        stars.append(Star(
            x=x, y=y,
            phase=rng.random() * 2 * math.pi,
            twinkle_speed=1.0 + rng.random() * 3.0,
            base_brightness=0.3 + rng.random() * 0.7,
            size=1 if rng.random() < 0.85 else 2,
            hue_variance=rng.random() * 0.15,
        ))
    return stars


def make_fireflies(w: int, h: int, n: int, horizon_y: float,
                   rng: random.Random) -> List[Firefly]:
    """Generate *n* fireflies near the ground."""
    flies: List[Firefly] = []
    for _ in range(n):
        x = rng.random() * w
        y = horizon_y * h + rng.random() * (1 - horizon_y) * h * 0.5
        flies.append(Firefly(
            x=x, y=y,
            vx=(rng.random() - 0.5) * 0.5,
            vy=-(rng.random() * 0.3),
            phase=rng.random() * 2 * math.pi,
            brightness=0.0,
        ))
    return flies


def init_scene() -> Scene:
    """Create a new Scene matching the current terminal size."""
    rng = random.Random()
    w, h = get_terminal_size()
    scene = Scene(W=w, H=h)

    scene.horizon_y = 0.72

    n_stars = min(int(w * h * 0.15), 800)
    scene.stars = make_stars(w, h, n_stars, rng)

    scene.moon = Moon(x=w * 0.8, y=h * 0.15, phase=0.0)

    scene.fireflies = make_fireflies(w, h, 15, scene.horizon_y, rng)

    return scene


# ====================================================================================================
# Update Logic
# ====================================================================================================


def update_scene(scene: Scene, dt: float) -> None:
    """Advance the scene simulation by *dt* seconds."""
    scene.time += dt

    # Spawn shooting stars occasionally (~0.3 per second)
    if random.random() < dt * 0.3:
        w, h = scene.W, scene.H
        x = random.random() * w * 0.8 + w * 0.1
        y = random.random() * h * 0.3
        angle = math.pi * 0.25 + random.random() * math.pi * 0.15
        speed = 8 + random.random() * 6
        life = 0.8 + random.random() * 0.6
        colors: List[Tuple[int, int, int]] = [
            (255, 255, 255),    # white
            (200, 220, 255),    # blue-white
            (255, 240, 200),    # warm white
            (200, 255, 220),    # greenish
        ]
        color = random.choice(colors)
        scene.shooting_stars.append(ShootingStar(
            x=x, y=y,
            dx=math.cos(angle) * speed,
            dy=math.sin(angle) * speed,
            life=life,
            max_life=life,
            tail_length=random.randint(8, 18),
            color=color,
        ))

    for ss in scene.shooting_stars:
        ss.life -= dt
        if ss.life <= 0:
            ss.active = False
            continue
        ss.x += ss.dx * dt
        ss.y += ss.dy * dt

    scene.shooting_stars = [ss for ss in scene.shooting_stars if ss.active]

    if scene.moon:
        scene.moon.phase += dt * 0.5

    for f in scene.fireflies:
        f.x += f.vx * dt
        f.y += f.vy * dt
        f.phase += dt * 2.5
        f.brightness = max(0.0, (math.sin(f.phase) + 1) * 0.5)
        if f.x < 0 or f.x > scene.W or f.y < 0:
            f.x = random.random() * scene.W
            f.y = scene.horizon_y * scene.H \
                + random.random() * (1 - scene.horizon_y) * scene.H * 0.4
            f.phase = 0.0


# ====================================================================================================
# Rendering
# ====================================================================================================


def lerp_color(c1: Tuple[int, int, int], c2: Tuple[int, int, int],
               t: float) -> Tuple[int, int, int]:
    """Linearly interpolate between two colours."""
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def sky_gradient(t: float) -> Tuple[int, int, int]:
    """Sky colour based on vertical position (0=top, 1=horizon)."""
    top = (8, 4, 28)
    mid = (20, 12, 50)
    horizon = (60, 35, 80)

    if t < 0.5:
        return lerp_color(top, mid, t * 2)
    else:
        return lerp_color(mid, horizon, (t - 0.5) * 2)


def ground_gradient(t: float) -> Tuple[int, int, int]:
    """Ground colour, *t*=0 at horizon, *t*=1 at bottom."""
    top = (15, 10, 8)
    bottom = (5, 3, 2)
    return lerp_color(top, bottom, t)


def star_brightness(star: Star, time: float) -> float:
    """Compute current brightness with twinkle effect."""
    twinkle = math.sin(time * star.twinkle_speed + star.phase)
    twinkle = max(0.0, twinkle ** 4)
    return star.base_brightness * (0.4 + twinkle * 0.6)


def draw_moon(screen: List[List[str]], scene: Scene) -> None:
    """Draw the moon with glow effect."""
    m = scene.moon
    if m is None:
        return
    mx, my = int(m.x), int(m.y)
    r, g, b = 245, 240, 210

    glow_radius = 5
    base_glow = 0.5 + math.sin(m.phase) * 0.15
    for gy in range(-glow_radius, glow_radius + 1):
        for gx in range(-glow_radius, glow_radius + 1):
            dist = math.sqrt(gx * gx + gy * gy)
            if dist > glow_radius:
                continue
            intensity = base_glow * (1 - dist / glow_radius) * 0.4
            if intensity <= 0.05:
                continue
            px, py = mx + gx, my + gy
            if 0 <= px < scene.W and 0 <= py < scene.H:
                glow_r = int(r * intensity)
                glow_g = int(g * intensity)
                glow_b = int(b * intensity * 0.8)
                screen[py][px] = bg(glow_r, glow_g, glow_b) + " " + RESET

    moon_radius = 3
    for gy in range(-moon_radius, moon_radius + 1):
        for gx in range(-moon_radius, moon_radius + 1):
            dist = math.sqrt(gx * gx + gy * gy)
            if dist > moon_radius:
                continue
            if dist > moon_radius - 0.5 and random.random() < 0.3:
                continue
            px, py = mx + gx, my + gy
            if 0 <= px < scene.W and 0 <= py < scene.H:
                shade = random.uniform(-15, 15) if dist < moon_radius - 1 else 0
                mr = max(0, min(255, r + int(shade)))
                mg = max(0, min(255, g + int(shade)))
                mb = max(0, min(255, b + int(shade)))
                screen[py][px] = fg(mr, mg, mb) + bg(mr, mg, mb) + "o" + RESET


def render_frame(scene: Scene) -> str:
    """Render the current scene to an ANSI string."""
    w, h = scene.W, scene.H
    horizon = int(h * scene.horizon_y)

    screen: List[List[str]] = [["" for _ in range(w)] for _ in range(h)]

    # ── Background pass: sky and ground ────────────────────────────────
    for y in range(h):
        for x in range(w):
            if y < horizon:
                t = y / horizon
                r, g, b = sky_gradient(t)
                screen[y][x] = bg(r, g, b) + " " + RESET
            else:
                t = (y - horizon) / (h - horizon)
                r, g, b = ground_gradient(t)
                screen[y][x] = bg(r, g, b) + " " + RESET

    # ── Draw moon (behind stars) ───────────────────────────────────────
    draw_moon(screen, scene)

    # ── Draw stars ─────────────────────────────────────────────────────
    for star in scene.stars:
        bx = int(star.x)
        by = int(star.y)
        if by >= horizon or by < 0 or bx < 0 or bx >= w:
            continue
        brightness = star_brightness(star, scene.time)
        if brightness < 0.05:
            continue

        r = int(180 + 75 * brightness)
        g = int(180 + 75 * brightness)
        b = int(200 + 55 * brightness)
        if star.hue_variance > 0.1:
            r = int(r * (1 - star.hue_variance * 0.3))
            b = int(b * (1 + star.hue_variance * 0.2))

        char = "*" if star.size == 2 else "."
        screen[by][bx] = fg(r, g, b) + char + RESET

    # ── Draw shooting stars ────────────────────────────────────────────
    for ss in scene.shooting_stars:
        tail_intensity = ss.life / ss.max_life
        for i in range(ss.tail_length):
            t = i / ss.tail_length
            alpha = tail_intensity * (1 - t)
            if alpha < 0.1:
                break
            px = int(ss.x - ss.dx * t / 5)
            py = int(ss.y - ss.dy * t / 5)
            if 0 <= px < w and 0 <= py < horizon:
                r = int(ss.color[0] * alpha)
                g = int(ss.color[1] * alpha)
                b = int(ss.color[2] * alpha)
                screen[py][px] = fg(r, g, b) + "." + RESET

    # ── Fireflies near ground ──────────────────────────────────────────
    for f in scene.fireflies:
        if f.brightness < 0.1:
            continue
        px = int(f.x)
        py = int(f.y)
        if 0 <= px < w and 0 <= py < h:
            intensity = f.brightness
            r = int(180 * intensity)
            g = int(255 * intensity)
            b = int(100 * intensity)
            screen[py][px] = fg(r, g, b) + "*" + RESET

    # ── Horizon line ────────────────────────────────────────────────────
    for x in range(w):
        if 0 <= x < w and 0 <= horizon < h:
            screen[horizon][x] = fg(40, 25, 60) + bg(30, 18, 40) + "-" + RESET

    lines: List[str] = []
    for y in range(h):
        lines.append("".join(screen[y]))
    return HOME + "\n".join(lines)


# ====================================================================================================
# Main Loop
# ====================================================================================================


def main() -> None:
    """Run the Nocturne night-scene animation."""
    sys.stdout.write(HIDE)
    sys.stdout.flush()

    scene = init_scene()

    last_time = time.perf_counter()
    try:
        while True:
            new_w, new_h = get_terminal_size()
            if new_w != scene.W or new_h != scene.H:
                scale_x = new_w / scene.W
                scale_y = new_h / scene.H
                scene.W = new_w
                scene.H = new_h
                scene.horizon_y = 0.72
                for s in scene.stars:
                    s.x *= scale_x
                    s.y *= scale_y
                if scene.moon:
                    scene.moon.x *= scale_x
                    scene.moon.y *= scale_y
                for f in scene.fireflies:
                    f.x *= scale_x
                    f.y *= scale_y

            now = time.perf_counter()
            dt = now - last_time
            last_time = now
            dt = min(dt, 0.1)

            update_scene(scene, dt)
            frame = render_frame(scene)

            sys.stdout.write(frame)
            sys.stdout.flush()

            sleep_time = FRAME_S - (time.perf_counter() - now)
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(SHOW)
        sys.stdout.write("\033[0m")
        sys.stdout.write(HOME + "\033[J")
        sys.stdout.flush()
        print("\nNocturne terminado. Boas noites estreladas!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()

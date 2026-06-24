#!/usr/bin/env python3
"""
Aurora — Terminal Aurora Borealis Simulator ✨🌌

Animated aurora curtains dancing across a starry arctic sky,
with mountain silhouettes, shooting stars, and ethereal glows.

Pure Python, zero dependencies. ANSI truecolor.
Press Ctrl+C to exit gracefully.

Companion piece to nocturne.py — daytime/nighttime sibling.
"""

import sys
import io

# Force UTF-8 for stdout so Unicode renders on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
elif hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import time
import os
import random
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

# ── ANSI helpers ──────────────────────────────────────────────────────────

def fg(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"

def bg(r: int, g: int, b: int) -> str:
    return f"\033[48;2;{r};{g};{b}m"

RESET   = "\033[0m"
HOME    = "\033[H"
HIDE    = "\033[?25l"
SHOW    = "\033[?25h"

# ── Config ────────────────────────────────────────────────────────────────

FPS = 30
FRAME_S = 1.0 / FPS

# ── Types ─────────────────────────────────────────────────────────────────

@dataclass
class Star:
    x: float
    y: float
    phase: float
    twinkle_speed: float
    base_brightness: float
    size: int        # 1 or 2
    hue_variance: float

@dataclass
class ShootingStar:
    x: float
    y: float
    vx: float
    vy: float
    life: float       # seconds remaining
    max_life: float
    trail_len: int    # how many tail segments

@dataclass
class AuroraCurtain:
    offset_x: float      # horizontal phase offset
    peak_y: float        # vertical center of curtain
    height: float        # vertical spread
    speed: float         # wave speed multiplier
    amplitude: float     # wave amplitude
    frequency: float     # wave frequency
    hue_shift: float     # color hue shift (0-1 maps to green->purple->pink)
    brightness: float    # overall brightness multiplier
    turbulence: float    # secondary noise for organic feel

@dataclass
class Snowflake:
    x: float
    y: float
    speed: float
    drift: float
    size: int            # 1 | 2
    phase: float

# ── Color palettes ────────────────────────────────────────────────────────

def aurora_gradient(t: float, hue_shift: float) -> Tuple[int, int, int]:
    """
    Map t ∈ [0,1] to a color along the aurora spectrum.
    hue_shift ∈ [0,1) shifts between green, teal, purple, pink.

    Base aurora colors (all at full saturation ~100, value modulated):
      Green:    (0, 200, 80)   # classic
      Teal:     (0, 180, 160)
      Purple:   (120, 60, 220)
      Pink:     (220, 60, 180)
    """
    # We blend between color stops based on t and hue_shift
    stops = [
        (0,   200, 80),   # green
        (0,   180, 160),  # teal
        (80,  100, 220),  # blue-purple
        (180, 60,  200),  # purple
        (220, 60,  140),  # pink
        (60,  180, 80),   # back to green
    ]

    hue_idx = hue_shift * (len(stops) - 1)
    idx = int(hue_idx)
    frac = hue_idx - idx

    # Wrap around
    if idx >= len(stops) - 1:
        idx = len(stops) - 2

    c1 = stops[idx]
    c2 = stops[idx + 1] if idx + 1 < len(stops) else stops[0]

    # Interpolate
    r = int(c1[0] + (c2[0] - c1[0]) * frac)
    g = int(c1[1] + (c2[1] - c1[1]) * frac)
    b = int(c1[2] + (c2[2] - c1[2]) * frac)

    # Modulate by t (brightness falls off at edges)
    intensity = max(0.0, min(1.0, 1.0 - abs(t - 0.5) * 1.8))
    # Soft glow at peak
    intensity = intensity ** 0.7

    r = min(255, int(r * intensity))
    g = min(255, int(g * intensity))
    b = min(255, int(b * intensity))

    return (r, g, b)


def sky_gradient(t: float) -> Tuple[int, int, int]:
    """Sky color: dark blue at top, near-black at bottom."""
    intensity = 1.0 - t * 0.7  # gets darker toward horizon
    r = int(10 * intensity)
    g = int(15 * intensity)
    b = int(40 * intensity)
    return (r, g, b)


def mountain_color(t: float) -> Tuple[int, int, int]:
    """Silhouette with slight blue tint."""
    # Gradient from slightly lighter at top to black at base
    darkness = 0.3 + 0.7 * t
    r = int(15 * (1 - t * 0.3))
    g = int(20 * (1 - t * 0.3))
    b = int(35 * (1 - t * 0.3))
    return (r, g, b)


# ── Scene generation ─────────────────────────────────────────────────────

def generate_stars(w: int, h: int, count: int) -> List[Star]:
    stars = []
    for _ in range(count):
        stars.append(Star(
            x=random.random(),
            y=random.random() * 0.65,  # keep in upper portion
            phase=random.random() * math.pi * 2,
            twinkle_speed=0.5 + random.random() * 3.0,
            base_brightness=0.3 + random.random() * 0.7,
            size=1 if random.random() < 0.85 else 2,
            hue_variance=random.random() * 0.15,
        ))
    return stars


def generate_aurora(w: int, h: int, count: int = 3) -> List[AuroraCurtain]:
    curtains = []
    for i in range(count):
        curtains.append(AuroraCurtain(
            offset_x=random.random() * math.pi * 2,
            peak_y=0.15 + random.random() * 0.3,
            height=0.08 + random.random() * 0.15,
            speed=0.1 + random.random() * 0.25,
            amplitude=0.04 + random.random() * 0.08,
            frequency=0.8 + random.random() * 1.5,
            hue_shift=i * 0.25 + random.random() * 0.15,
            brightness=0.5 + random.random() * 0.5,
            turbulence=0.3 + random.random() * 0.5,
        ))
    return curtains


def generate_mountains() -> List[Tuple[float, float]]:
    """Generate mountain silhouette points for a given width."""
    # We generate a profile based on multiple sine waves
    profile = []
    for i in range(101):  # normalized 0..100
        x = i / 100.0
        y = 0.25 + 0.15 * (  # base height
            math.sin(x * math.pi * 3.7) * 0.5 + 0.5 +
            math.sin(x * math.pi * 7.2 + 0.5) * 0.25 +
            math.sin(x * math.pi * 13.1 + 1.2) * 0.125
        )
        # Random seed for reproducibility
        r = hash(i * 137) % 1000 / 1000.0
        y += r * 0.03
        profile.append((x, y))
    return profile


def generate_snowflakes(count: int) -> List[Snowflake]:
    flakes = []
    for _ in range(count):
        flakes.append(Snowflake(
            x=random.random(),
            y=random.random(),
            speed=0.01 + random.random() * 0.04,
            drift=(random.random() - 0.5) * 0.008,
            size=1 if random.random() < 0.7 else 2,
            phase=random.random() * math.pi * 2,
        ))
    return flakes


# ── Frame rendering ──────────────────────────────────────────────────────

def render_frame(
    w: int, h: int,
    stars: List[Star],
    auroras: List[AuroraCurtain],
    mountains: List[Tuple[float, float]],
    snowflakes: List[Snowflake],
    shooting_stars: List[ShootingStar],
    t: float,
) -> str:
    """
    Build one frame as a string of ANSI-colored characters.
    """
    lines: List[str] = []
    # Precompute aurora values per column for smooth curtain
    aurora_cache: List[List[Optional[Tuple[int, int, int]]]] = [
        [None] * w for _ in range(h)
    ]

    # ── Aurora pass ──
    for curtain in auroras:
        for py in range(h):
            for px in range(w):
                nx = px / w
                ny = py / h

                # Distance from peak_y
                dy = abs(ny - curtain.peak_y)
                if dy > curtain.height:
                    continue

                # Main wave: multiple overlapping sine waves for organic look
                wave = math.sin(
                    nx * math.pi * 2 * curtain.frequency
                    + t * curtain.speed
                    + curtain.offset_x
                )

                # Secondary wave (turbulence)
                wave2 = math.sin(
                    nx * math.pi * 4 * curtain.frequency
                    + t * curtain.speed * 0.7
                    + curtain.offset_x * 1.3
                    + 1.5
                ) * 0.5

                # Tertiary wave for shimmer
                wave3 = math.sin(
                    nx * math.pi * 0.5
                    + t * 0.3
                    + px * 0.1
                ) * 0.3

                combined = wave + wave2 + wave3
                # Normalize to [0, 1]
                combined = combined * 0.5 + 0.5

                # Vertical fade: strongest at peak_y, fade at edges
                vert_fade = max(0.0, 1.0 - (dy / curtain.height) ** 2)

                # Create bright spots where curtain is strongest
                intensity = combined * vert_fade * curtain.brightness

                if intensity < 0.05:
                    continue

                # Feather the bottom for ethereal look
                if ny > curtain.peak_y:
                    intensity *= 1.0 - ((ny - curtain.peak_y) / curtain.height) ** 0.5

                # Map to color
                color_t = combined * 0.6 + 0.2  # keep in mid-range
                color = aurora_gradient(color_t, curtain.hue_shift + math.sin(t * 0.05 + curtain.offset_x) * 0.1)

                # Blend with existing (for overlapping curtains)
                existing = aurora_cache[py][px]
                if existing is None:
                    aurora_cache[py][px] = (
                        min(255, int(color[0] * intensity + 2)),
                        min(255, int(color[1] * intensity + 4)),
                        min(255, int(color[2] * intensity + 6)),
                    )
                else:
                    # Additive blending for overlapping curtains
                    aurora_cache[py][px] = (
                        min(255, existing[0] + int(color[0] * intensity * 0.6)),
                        min(255, existing[1] + int(color[1] * intensity * 0.6)),
                        min(255, existing[2] + int(color[2] * intensity * 0.6)),
                    )

    # ── Render lines ──
    for py in range(h):
        line_parts: List[str] = []
        for px in range(w):
            nx = px / w
            ny = py / h

            # Mountain silhouette occupies bottom portion
            mountain_y = 0.65  # mountains start here
            is_mountain = False
            mountain_height = 0.0

            if ny >= mountain_y:
                # Find mountain height at this x
                # Interpolate from profile
                m_idx = nx * (len(mountains) - 1)
                m_idx_int = int(m_idx)
                m_frac = m_idx - m_idx_int
                if m_idx_int < len(mountains) - 1:
                    m_y = mountains[m_idx_int][1] * (1 - m_frac) + mountains[m_idx_int + 1][1] * m_frac
                else:
                    m_y = mountains[-1][1]

                # Map ny to local vertical position within mountain
                local_y = (ny - mountain_y) / (1.0 - mountain_y)
                # mountain height from profile
                usable_height = m_y * 0.35  # scale m_y to screen
                if local_y > usable_height:
                    is_mountain = True
                    mountain_height = (local_y - usable_height) / (1.0 - usable_height)

            if is_mountain:
                mc = mountain_color(mountain_height)
                line_parts.append(bg(mc[0], mc[1], mc[2]) + " ")
            elif ny < 0.65:
                # Sky: check for aurora, then stars
                aurora_color = aurora_cache[py][px]

                if aurora_color is not None:
                    line_parts.append(bg(aurora_color[0], aurora_color[1], aurora_color[2]) + " ")
                else:
                    # Pure sky
                    sc = sky_gradient(ny / 0.65)
                    line_parts.append(bg(sc[0], sc[1], sc[2]) + " ")
            else:
                # Lower portion of mountains (below mountain silhouette)
                mc = mountain_color(0.95)
                line_parts.append(bg(mc[0], mc[1], mc[2]) + " ")

        # Build line character by character (star/snowflake overlay integrated)
        line_chars = []
        for px in range(w):
            nx = px / w
            ny = py / h

            # Determine what's at this position
            mountain_y = 0.65
            is_mountain = False
            mountain_height = 0.0
            is_sky = False
            is_mountain_below = False

            if ny >= mountain_y:
                m_idx = nx * (len(mountains) - 1)
                m_idx_int = int(m_idx)
                m_frac = m_idx - m_idx_int
                if m_idx_int < len(mountains) - 1:
                    m_y = mountains[m_idx_int][1] * (1 - m_frac) + mountains[m_idx_int + 1][1] * m_frac
                else:
                    m_y = mountains[-1][1]

                local_y = (ny - mountain_y) / (1.0 - mountain_y)
                usable_height = m_y * 0.35
                if local_y > usable_height:
                    is_mountain = True
                    mountain_height = (local_y - usable_height) / (1.0 - usable_height)
                else:
                    is_mountain_below = True
            else:
                is_sky = True

            # Check for star at this position (approximate)
            star_here = None
            for star in stars:
                spx = int(star.x * w)
                spy = int(star.y * h)
                if spx == px and spy == py:
                    twinkle = max(0.0, math.sin(t * star.twinkle_speed + star.phase))
                    bright = star.base_brightness * (0.3 + 0.7 * twinkle)
                    if bright > 0.15:
                        warmth = 0.8 + star.hue_variance * 0.4
                        star_here = (
                            min(255, int(200 * warmth * bright)),
                            min(255, int(200 * (1.0 - star.hue_variance * 0.5) * bright)),
                            min(255, int(255 * (1.0 - star.hue_variance * 0.3) * bright)),
                            "·" if star.size == 1 else "✦",
                        )
                    break

            # Check for shooting star at this position
            shooting_here = None
            for ss in shooting_stars:
                ssx = int(ss.x)
                ssy = int(ss.y)
                if ssx == px and ssy == py:
                    remaining = ss.life / ss.max_life
                    shooting_here = (
                        min(255, int(255 * remaining)),
                        min(255, int(255 * remaining)),
                        min(255, int(200 * remaining)),
                        "✦" if remaining > 0.5 else "·",
                    )
                    break

            # Check for snowflake at this position
            flake_here = None
            for flake in snowflakes:
                fpx = int(flake.x * w)
                fpy = int(flake.y * h)
                if fpx == px and fpy == py:
                    flake_here = (200, 220, 255, "*" if flake.size == 2 else "·")
                    break

            # Determine background and foreground color
            if is_sky:
                bg_color = sky_gradient(ny / 0.65)
                # Check aurora overlay
                aurora_color = aurora_cache[py][px]
                if aurora_color is not None:
                    bg_color = aurora_color
            elif is_mountain:
                bg_color = mountain_color(mountain_height)
            else:
                bg_color = mountain_color(0.95)

            # Determine character and foreground
            if shooting_here:
                char = shooting_here[3]
                color = (shooting_here[0], shooting_here[1], shooting_here[2])
                line_chars.append(fg(color[0], color[1], color[2]) + bg(bg_color[0], bg_color[1], bg_color[2]) + char)
            elif star_here:
                char = star_here[3]
                color = (star_here[0], star_here[1], star_here[2])
                line_chars.append(fg(color[0], color[1], color[2]) + bg(bg_color[0], bg_color[1], bg_color[2]) + char)
            elif flake_here:
                char = flake_here[3]
                line_chars.append(bg(bg_color[0], bg_color[1], bg_color[2]) + fg(flake_here[0], flake_here[1], flake_here[2]) + char)
            else:
                # Just background with space
                line_chars.append(bg(bg_color[0], bg_color[1], bg_color[2]) + " ")

        lines.append("".join(line_chars) + RESET)

    return "\n".join(lines)


# ── Main loop ─────────────────────────────────────────────────────────────

def main():
    try:
        os.system("")  # Enable ANSI on Windows
        print(HIDE, end="", flush=True)

        # Detect terminal size
        w, h = 80, 40
        try:
            ts = os.get_terminal_size()
            w, h = ts.columns, ts.lines
        except (ValueError, OSError):
            pass

        # Clamp for performance
        w = min(w, 140)
        h = min(h, 50)

        # Generate scene
        stars = generate_stars(w, h, count=min(w * 3, 300))
        auroras = generate_aurora(w, h, count=3)
        mountains = generate_mountains()
        snowflakes = generate_snowflakes(count=20)
        shooting_stars: List[ShootingStar] = []

        t = 0.0
        next_shooting = 5.0  # seconds until next shooting star
        frame_count = 0

        print(f"✨ Aurora Borealis — {w}×{h} | Ctrl+C to exit")

        while True:
            frame_start = time.perf_counter()

            # Update shooting stars
            new_shooting = []
            for ss in shooting_stars:
                ss.x += ss.vx
                ss.y += ss.vy
                ss.life -= FRAME_S
                if ss.life > 0:
                    new_shooting.append(ss)

            # Spawn new shooting stars
            next_shooting -= FRAME_S
            if next_shooting <= 0 and len(new_shooting) < 3:
                angle = math.radians(random.uniform(20, 60))
                speed = 3 + random.random() * 5
                new_shooting.append(ShootingStar(
                    x=random.random() * w * 0.7,
                    y=random.random() * h * 0.15,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed,
                    life=0.5 + random.random() * 1.0,
                    max_life=1.5,
                    trail_len=random.randint(3, 6),
                ))
                next_shooting = 4 + random.random() * 12
            shooting_stars = new_shooting

            # Update snowflakes
            for flake in snowflakes:
                flake.x += flake.drift
                flake.y += flake.speed * 0.5
                # Wrap
                if flake.x > 1.0:
                    flake.x = 0.0
                elif flake.x < 0.0:
                    flake.x = 1.0
                if flake.y > 1.0:
                    flake.y = 0.0
                    flake.x = random.random()
                    flake.speed = 0.01 + random.random() * 0.04

            # Render
            frame = render_frame(w, h, stars, auroras, mountains, snowflakes, shooting_stars, t)
            print(HOME + frame, end="", flush=True)

            # Frame timing
            elapsed = time.perf_counter() - frame_start
            sleep = FRAME_S - elapsed
            if sleep > 0:
                time.sleep(sleep)

            t += FRAME_S
            frame_count += 1

            # Optionally print FPS counter every 5 seconds
            if frame_count % (FPS * 5) == 0:
                pass  # keep clean

    except KeyboardInterrupt:
        pass
    finally:
        print(SHOW + RESET + "\n🌌 Aurora faded. Até à próxima!\n")


if __name__ == "__main__":
    main()

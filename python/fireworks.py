#!/usr/bin/env python3
"""
🎆 ASCII Fireworks Simulator
Terminal fireworks display with particle physics, multiple types, and ANSI truecolor.

Controls:
  Space / Enter  — Launch a random firework
  1-5            — Launch a specific type (Burst, Fountain, Comet, Crossette, Willow)
  p              — Cycle palette
  t              — Toggle trails
  g              — Toggle gravity toggle
  q / Ctrl+C     — Quit
"""

import sys
import os
import time
import math
import random
import threading
import curses
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from enum import Enum

# ── UTF-8 on Windows terminals ───────────────────────────────────────────────
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Constants ────────────────────────────────────────────────────────────────
FRAME_DELAY = 0.045  # seconds per frame (~22 FPS)
GRAVITY = 0.06
DRAG = 0.985
MAX_PARTICLES = 600
GROUND_Y_RATIO = 0.92  # ground at 92% of screen height
TRAIL_DECAY = 0.75

# Density chars for depth/brightness: dim ─── bright
DENSITY = " .·░▒▓█"
CHARS_BURST = "·*:;o@█"
CHARS_SPARKLE = "✦✧★☆"
CHARS_FOUNTAIN = "|/\\·*"
CHARS_COMET = "·:*°●"
CHARS_WILLOW = "~≈∽"


# ── Color Palettes ───────────────────────────────────────────────────────────
# Each palette: list of (r, g, b) tuples, cycling through them
PALETTES = {
    "Classic": [
        (255, 100, 100), (100, 255, 100), (100, 100, 255),
        (255, 255, 100), (255, 100, 255), (100, 255, 255),
        (255, 170, 50), (170, 100, 255),
    ],
    "Patriotic": [
        (255, 30, 30), (30, 60, 255), (255, 255, 255),
        (255, 60, 30), (30, 100, 255), (255, 200, 200),
    ],
    "Sunset": [
        (255, 80, 0), (255, 150, 30), (255, 50, 80),
        (255, 200, 50), (200, 40, 100), (255, 100, 50),
        (180, 30, 70), (255, 220, 100),
    ],
    "Neon": [
        (255, 0, 255), (0, 255, 255), (255, 255, 0),
        (0, 255, 128), (255, 64, 128), (128, 0, 255),
    ],
    "Galaxy": [
        (180, 100, 255), (80, 150, 255), (255, 130, 255),
        (100, 255, 200), (255, 200, 100), (150, 80, 255),
        (200, 255, 180), (255, 100, 200),
    ],
}

PALETTE_NAMES = list(PALETTES.keys())


# ── Firework Types ───────────────────────────────────────────────────────────
class FireworkType(Enum):
    BURST = "burst"
    FOUNTAIN = "fountain"
    COMET = "comet"
    CROSSETTE = "crossette"
    WILLOW = "willow"


FW_TYPE_LIST = list(FireworkType)


# ── Particle ─────────────────────────────────────────────────────────────────
@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    r: int = 255
    g: int = 255
    b: int = 255
    char: str = "·"
    life: float = 1.0
    decay: float = 0.02
    gravity_mult: float = 1.0
    trail: List[Tuple[float, float, str]] = field(default_factory=list)
    age: float = 0.0
    sparkle: bool = False
    sparkle_speed: float = 0.0

    def update(self, dt: float, use_gravity: bool) -> bool:
        """Advance particle. Returns False when dead."""
        self.age += dt
        self.life -= self.decay * dt * 3.0
        if self.life <= 0:
            return False

        # Store trail point
        if self.trail is not None:
            self.trail.append((self.x, self.y, self.char))
            max_trail = 8
            if len(self.trail) > max_trail:
                self.trail = self.trail[-max_trail:]

        if use_gravity:
            self.vy += GRAVITY * self.gravity_mult * dt * 3.0
        self.vx *= DRAG
        self.vy *= DRAG
        self.x += self.vx * dt * 3.0
        self.y += self.vy * dt * 3.0

        # Sparkle flicker
        if self.sparkle:
            flicker = math.sin(self.age * self.sparkle_speed) ** 2
            if random.random() > flicker + 0.3:
                return False

        return True


# ── Firework ─────────────────────────────────────────────────────────────────
@dataclass
class Firework:
    """A single firework: manages launch + explosion phases."""
    x: float
    y: float  # target height
    vy: float
    fw_type: FireworkType
    palette_idx: int = 0
    phase: str = "rising"  # rising | exploding | dead
    trail: List[Tuple[float, float, str]] = field(default_factory=list)
    rise_progress: float = 0.0
    particles: List[Particle] = field(default_factory=list)
    explode_delay: float = 0.0
    alive: bool = True

    def __post_init__(self):
        self.current_y = self.y  # start from ground
        self.rise_x = self.x

    def update(self, dt: float, ground_y: float, use_gravity: bool,
               palette: List[Tuple[int, int, int]]) -> bool:
        if not self.alive:
            return False

        if self.phase == "rising":
            self.current_y -= self.vy * dt * 3.0
            # Slight drift
            self.rise_x += random.uniform(-0.02, 0.02) * dt * 3.0
            self.trail.append((self.rise_x, self.current_y, "│"))

            # Reached target height?
            if self.current_y <= self.y:
                self.phase = "exploding"
                self._explode(palette)
                return True

            return True

        elif self.phase == "exploding":
            dead = []
            for p in self.particles:
                if not p.update(dt, use_gravity):
                    dead.append(p)
            for p in dead:
                self.particles.remove(p)

            if not self.particles:
                self.alive = False
                return False
            return True

        return False

    def _explode(self, palette: List[Tuple[int, int, int]]):
        self.phase = "exploding"
        cx, cy = self.rise_x, self.current_y
        base_color = random.choice(palette)
        variation = 30

        def v(base, rng=40):
            return max(0, min(255, base + random.randint(-rng, rng)))

        color_fn = lambda: (v(base_color[0], variation),
                            v(base_color[1], variation),
                            v(base_color[2], variation))

        if self.fw_type == FireworkType.BURST:
            n = random.randint(40, 80)
            for _ in range(n):
                angle = random.uniform(0, 2 * math.pi)
                speed = random.uniform(0.8, 3.0)
                r, g, b = color_fn()
                ch = random.choice(CHARS_BURST)
                self.particles.append(Particle(
                    x=cx, y=cy,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed - 0.5,
                    r=r, g=g, b=b, char=ch,
                    decay=random.uniform(0.015, 0.035),
                    gravity_mult=random.uniform(0.6, 1.4),
                    trail=[],
                    sparkle=random.random() > 0.6,
                    sparkle_speed=random.uniform(8, 20),
                ))

        elif self.fw_type == FireworkType.FOUNTAIN:
            n = random.randint(50, 90)
            for _ in range(n):
                angle = random.uniform(-0.6, 0.6)  # narrow cone upward
                speed = random.uniform(1.5, 4.0)
                r, g, b = color_fn()
                ch = random.choice(CHARS_FOUNTAIN)
                self.particles.append(Particle(
                    x=cx + random.uniform(-0.3, 0.3), y=cy,
                    vx=math.sin(angle) * speed * 0.4,
                    vy=-abs(math.cos(angle) * speed),
                    r=r, g=g, b=b, char=ch,
                    decay=random.uniform(0.01, 0.03),
                    gravity_mult=random.uniform(0.4, 1.0),
                    trail=[],
                ))

        elif self.fw_type == FireworkType.COMET:
            n = random.randint(3, 6)
            for _ in range(n):
                angle = random.uniform(0, 2 * math.pi)
                speed = random.uniform(2.0, 4.0)
                r, g, b = (v(255, 20), v(255, 30), v(255, 20))  # bright white-gold
                self.particles.append(Particle(
                    x=cx, y=cy,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed - 1.0,
                    r=r, g=g, b=b, char=random.choice(CHARS_COMET),
                    decay=random.uniform(0.005, 0.015),  # long-lived
                    gravity_mult=0.3,
                    trail=[],
                    sparkle=True,
                    sparkle_speed=random.uniform(15, 30),
                ))

        elif self.fw_type == FireworkType.CROSSETTE:
            # Burst then each particle bursts again
            n = random.randint(8, 14)
            for _ in range(n):
                angle = random.uniform(0, 2 * math.pi)
                speed = random.uniform(1.5, 3.0)
                r, g, b = color_fn()
                p = Particle(
                    x=cx, y=cy,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed - 0.5,
                    r=r, g=g, b=b, char="✦",
                    decay=random.uniform(0.02, 0.04),
                    gravity_mult=0.5,
                    trail=[],
                )
                self.particles.append(p)

        elif self.fw_type == FireworkType.WILLOW:
            n = random.randint(30, 50)
            for _ in range(n):
                angle = random.uniform(0, 2 * math.pi)
                speed = random.uniform(0.5, 1.5)
                r, g, b = (v(255, 15), v(220, 20), v(100, 40))  # warm gold
                self.particles.append(Particle(
                    x=cx, y=cy,
                    vx=math.cos(angle) * speed * 0.3,
                    vy=math.sin(angle) * speed - 0.3,
                    r=r, g=g, b=b, char=random.choice(CHARS_WILLOW),
                    decay=random.uniform(0.003, 0.008),  # very long-lived
                    gravity_mult=1.5,  # heavy gravity for droopy effect
                    trail=[],
                ))


# ── Renderer ─────────────────────────────────────────────────────────────────
class Renderer:
    """Renders the scene into a character buffer with ANSI truecolor."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.ground_y = int(height * GROUND_Y_RATIO)
        self.buffer: List[List[str]] = [[" "] * width for _ in range(height)]
        self.color: List[List[Tuple[int, int, int]]] = [[(0, 0, 0)] * width for _ in range(height)]
        self.stars: List[Tuple[int, int, float, float]] = []
        self._init_stars()

    def _init_stars(self):
        """Generate random twinkling stars."""
        n = max(20, self.width * self.height // 80)
        for _ in range(n):
            sx = random.randint(0, self.width - 1)
            sy = random.randint(0, self.ground_y - 5)
            brightness = random.uniform(0.3, 1.0)
            speed = random.uniform(1.0, 4.0)
            self.stars.append((sx, sy, brightness, speed))

    def resize(self, width: int, height: int):
        self.width = width
        self.height = height
        self.ground_y = int(height * GROUND_Y_RATIO)
        self.buffer = [[" "] * width for _ in range(height)]
        self.color = [[(0, 0, 0)] * width for _ in range(height)]
        self.stars = []
        self._init_stars()

    def clear(self):
        self.buffer = [[" "] * self.width for _ in range(self.height)]
        self.color = [[(0, 0, 0)] * self.width for _ in range(self.height)]

    def draw_stars(self, t: float):
        for sx, sy, brightness, speed in self.stars:
            if sy >= self.height or sx >= self.width:
                continue
            twinkle = (math.sin(t * speed + sx * 0.1) ** 2) * brightness
            if twinkle > 0.3:
                idx = min(len(DENSITY) - 1, int(twinkle * len(DENSITY)))
                self.buffer[sy][sx] = DENSITY[idx]
                c = int(200 * twinkle)
                self.color[sy][sx] = (c, c, min(255, c + 40))

    def draw_ground(self):
        """Draw ground line and buildings."""
        gy = self.ground_y
        if gy >= self.height:
            return
        for x in range(self.width):
            if gy < self.height:
                self.buffer[gy][x] = "─"
                self.color[gy][x] = (60, 80, 60)
        # Draw some random buildings
        seed = 42
        bx = 0
        while bx < self.width:
            random.seed(seed)
            seed += 1
            bw = random.randint(3, 8)
            bh = random.randint(2, 6)
            for dy in range(1, bh + 1):
                for dx in range(bw):
                    px = bx + dx
                    py = gy + dy
                    if py < self.height and px < self.width:
                        self.buffer[py][px] = "█"
                        self.color[py][px] = (30, 35, 40)
            # Windows
            for dy in range(2, bh + 1):
                for dx in range(1, bw - 1, 2):
                    px = bx + dx
                    py = gy + dy
                    if py < self.height and px < self.width and random.random() > 0.4:
                        self.buffer[py][px] = "▪"
                        self.color[py][px] = (200, 180, 80)
            bx += bw + random.randint(2, 5)
        random.seed()  # reset seed

    def draw_firework(self, fw: Firework):
        """Draw a firework's trail and particles."""
        # Rising trail
        if fw.phase == "rising":
            for tx, ty, ch in fw.trail:
                ix, iy = int(tx), int(ty)
                if 0 <= ix < self.width and 0 <= iy < self.height:
                    self.buffer[iy][ix] = "│"
                    self.color[iy][ix] = (255, 200, 100)
            # Head
            hx, hy = int(fw.rise_x), int(fw.current_y)
            if 0 <= hx < self.width and 0 <= hy < self.height:
                self.buffer[hy][hx] = "●"
                self.color[hy][hx] = (255, 255, 200)

        # Particles
        for p in fw.particles:
            # Trail
            if hasattr(p, 'trail') and p.trail:
                for ti, (tx, ty, tch) in enumerate(p.trail):
                    ix, iy = int(tx), int(ty)
                    if 0 <= ix < self.width and 0 <= iy < self.height:
                        fade = ti / max(1, len(p.trail))
                        fc = int(p.r * fade * TRAIL_DECAY)
                        fg = int(p.g * fade * TRAIL_DECAY)
                        fb = int(p.b * fade * TRAIL_DECAY)
                        self.buffer[iy][ix] = "·"
                        self.color[iy][ix] = (fc, fg, fb)

            # Head
            ix, iy = int(p.x), int(p.y)
            if 0 <= ix < self.width and 0 <= iy < self.height:
                alpha = max(0.2, p.life)
                r = int(p.r * alpha)
                g = int(p.g * alpha)
                b = int(p.b * alpha)
                self.buffer[iy][ix] = p.char
                self.color[iy][ix] = (r, g, b)

    def render_frame(self) -> str:
        """Convert buffer to ANSI truecolor string."""
        lines = []
        for y in range(self.height):
            parts = []
            prev_color = None
            for x in range(self.width):
                ch = self.buffer[y][x]
                c = self.color[y][x]
                if c != prev_color:
                    parts.append(f"\033[38;2;{c[0]};{c[1]};{c[2]}m")
                    prev_color = c
                parts.append(ch)
            parts.append("\033[0m")
            lines.append("".join(parts))
        return "\n".join(lines)


# ── Main Simulation ──────────────────────────────────────────────────────────
def run_simulation(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(10)  # 10ms input polling

    # Initialize
    palette_name = PALETTE_NAMES[0]
    palette = PALETTES[palette_name]
    use_trails = True
    use_gravity = True
    auto_launch = True
    auto_timer = 0.0
    auto_interval = 2.5  # seconds between auto-launches
    firework_type_idx = 0
    show_hud = True
    time_val = 0.0

    # Get terminal size
    def get_size():
        try:
            y, x = stdscr.getmaxyx()
            return x, y
        except Exception:
            return 80, 24

    w, h = get_size()
    renderer = Renderer(w, h)
    fireworks: List[Firework] = []

    # Hide cursor, enter alternate screen
    sys.stdout.write("\033[?1049h\033[?25l")
    sys.stdout.flush()

    def cleanup():
        sys.stdout.write("\033[?25h\033[?1049l")
        sys.stdout.flush()
        curses.endwin()

    try:
        while True:
            t0 = time.time()

            # ── Input ───────────────────────────────────────────────────
            try:
                key = stdscr.getch()
            except Exception:
                key = -1

            while key != -1:
                if key in (ord('q'), ord('Q')):
                    cleanup()
                    return
                elif key in (ord(' '), ord('\n')):
                    ft = FW_TYPE_LIST[firework_type_idx]
                    fx = random.uniform(w * 0.15, w * 0.85)
                    fy = random.uniform(h * 0.15, h * 0.45)
                    fireworks.append(Firework(
                        x=fx, y=fy,
                        vy=random.uniform(2.0, 4.0),
                        fw_type=ft,
                    ))
                elif key in (ord('1'), ord('2'), ord('3'), ord('4'), ord('5')):
                    ft = FW_TYPE_LIST[key - ord('1')]
                    firework_type_idx = key - ord('1')
                    fx = random.uniform(w * 0.15, w * 0.85)
                    fy = random.uniform(h * 0.15, h * 0.45)
                    fireworks.append(Firework(
                        x=fx, y=fy,
                        vy=random.uniform(2.0, 4.0),
                        fw_type=ft,
                    ))
                elif key == ord('p'):
                    idx = (PALETTE_NAMES.index(palette_name) + 1) % len(PALETTE_NAMES)
                    palette_name = PALETTE_NAMES[idx]
                    palette = PALETTES[palette_name]
                elif key == ord('t'):
                    use_trails = not use_trails
                elif key == ord('g'):
                    use_gravity = not use_gravity
                elif key == ord('h'):
                    show_hud = not show_hud
                elif key == ord('a'):
                    auto_launch = not auto_launch
                    auto_timer = 0.0

                try:
                    key = stdscr.getch()
                except Exception:
                    key = -1

            # ── Resize check ────────────────────────────────────────────
            new_w, new_h = get_size()
            if new_w != w or new_h != h:
                w, h = new_w, new_h
                renderer.resize(w, h)

            # ── Auto-launch ─────────────────────────────────────────────
            if auto_launch:
                auto_timer += FRAME_DELAY
                if auto_timer >= auto_interval:
                    auto_timer = 0.0
                    ft = random.choice(FW_TYPE_LIST)
                    fx = random.uniform(w * 0.15, w * 0.85)
                    fy = random.uniform(h * 0.1, h * 0.4)
                    fireworks.append(Firework(
                        x=fx, y=fy,
                        vy=random.uniform(2.0, 4.0),
                        fw_type=ft,
                    ))
                    # Occasionally launch 2-3 at once for a finale effect
                    if random.random() < 0.15:
                        for _ in range(random.randint(1, 2)):
                            ft2 = random.choice(FW_TYPE_LIST)
                            fireworks.append(Firework(
                                x=random.uniform(w * 0.1, w * 0.9),
                                y=random.uniform(h * 0.1, h * 0.35),
                                vy=random.uniform(2.0, 4.0),
                                fw_type=ft2,
                            ))

            # ── Update ──────────────────────────────────────────────────
            alive = []
            for fw in fireworks:
                if fw.update(FRAME_DELAY, renderer.ground_y, use_gravity, palette):
                    alive.append(fw)
            fireworks = alive

            # ── Render ──────────────────────────────────────────────────
            renderer.clear()
            renderer.draw_stars(time_val)
            renderer.draw_ground()
            for fw in fireworks:
                renderer.draw_firework(fw)

            # ── HUD ─────────────────────────────────────────────────────
            if show_hud:
                fw_type = FW_TYPE_LIST[firework_type_idx].value.capitalize()
                hud_lines = [
                    f"🎆 Fireworks  │ Palette: {palette_name}  │ Type: {fw_type}  │ "
                    f"Particles: {sum(len(fw.particles) for fw in fireworks)}",
                    f"SPACE/ENTER: launch  │ 1-5: type  │ p: palette  │ t: trails  │ "
                    f"g: gravity  │ a: auto  │ h: HUD  │ q: quit",
                ]
                for i, line in enumerate(hud_lines):
                    if i < renderer.height:
                        for j, ch in enumerate(line):
                            if j < renderer.width:
                                renderer.buffer[i][j] = ch
                                renderer.color[i][j] = (180, 180, 200)

            # ── Draw ────────────────────────────────────────────────────
            frame = renderer.render_frame()
            sys.stdout.write(f"\033[H{frame}")
            sys.stdout.flush()

            # Cap FPS
            elapsed = time.time() - t0
            sleep_time = FRAME_DELAY - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

            time_val += FRAME_DELAY

    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


# ── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    curses.wrapper(run_simulation)

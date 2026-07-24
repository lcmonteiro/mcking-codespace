#!/usr/bin/env python3
"""
Lorenz Attractor — Terminal 3D Chaotic System
===============================================
Visualises the Lorenz system (1963) as a rotating 3D trajectory
rendered with ANSI colour and ASCII depth shading.

The Lorenz equations:
    dx/dt = σ(y − x)
    dy/dt = x(ρ − z) − y
    dz/dt = xy − βz

Controls:
    [r] Reset trajectory     [p] Cycle palettes
    [←/→] Adjust σ           [↑/↓] Adjust ρ
    [z/Z] Adjust β           [space] Pause/Resume
    [+/-] Speed               [q/ESC] Quit

Zero external dependencies. Pure Python + ANSI.
"""

import io
import math
import os
import random
import sys
import time

# ── UTF-8 fix for Windows terminals ────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
elif hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )

# ── Terminal ────────────────────────────────────────────────
HIDE  = "\033[?25l"
SHOW  = "\033[?25h"
HOME  = "\033[H"
RESET = "\033[0m"
BOLD  = "\033[1m"


def term_size():
    try:
        return os.get_terminal_size()
    except OSError:
        return os.terminal_size((80, 24))


# ── Palettes ────────────────────────────────────────────────
PALETTES = {
    "Plasma": lambda t: (
        int(255 * (0.5 + 0.5 * math.sin(2 * math.pi * (t + 0.0)))),
        int(255 * (0.5 + 0.5 * math.sin(2 * math.pi * (t + 0.33)))),
        int(255 * (0.5 + 0.5 * math.sin(2 * math.pi * (t + 0.67)))),
    ),
    "Lava": lambda t: (
        int(255 * min(1.0, t * 1.5)),
        int(255 * max(0.0, t * 1.5 - 0.7)),
        int(80 * max(0.0, t * 2.0 - 1.2)),
    ),
    "Ice": lambda t: (
        int(180 * max(0.0, t - 0.3)),
        int(200 * t),
        int(255 * (0.5 + 0.5 * t)),
    ),
    "Neon": lambda t: (
        int(255 * (0.5 + 0.5 * math.sin(6.28 * t + 0.0))),
        int(255 * max(0.0, math.sin(6.28 * t + 2.1) * 0.8)),
        int(255 * max(0.0, math.cos(6.28 * t + 4.2) * 0.9)),
    ),
    "Forest": lambda t: (
        int(60 * t),
        int(200 * (0.3 + 0.7 * t)),
        int(80 * (0.2 + 0.3 * t)),
    ),
    "Monochrome": lambda t: (
        int(255 * t),
        int(255 * t),
        int(255 * t),
    ),
}

DEPTH_CHARS = " .:-=+*#%@█"
DEPTH_LEN = len(DEPTH_CHARS)


# ── Lorenz System ───────────────────────────────────────────
class Lorenz:
    """Simulates the Lorenz attractor using RK4 integration."""

    def __init__(self, sigma=10.0, rho=28.0, beta=8 / 3, dt=0.005):
        self.sigma = sigma
        self.rho = rho
        self.beta = beta
        self.dt = dt
        self.reset()

    def reset(self):
        self.x = random.uniform(-1, 1)
        self.y = random.uniform(-1, 1)
        self.z = random.uniform(20, 30)
        self.trail = []
        self.max_trail = 1200

    def _deriv(self, x, y, z):
        return (
            self.sigma * (y - x),
            x * (self.rho - z) - y,
            x * y - self.beta * z,
        )

    def step(self, steps=10):
        """Advance the system by `steps` sub-steps."""
        for _ in range(steps):
            dx1, dy1, dz1 = self._deriv(self.x, self.y, self.z)
            x2 = self.x + 0.5 * self.dt * dx1
            y2 = self.y + 0.5 * self.dt * dy1
            z2 = self.z + 0.5 * self.dt * dz1

            dx2, dy2, dz2 = self._deriv(x2, y2, z2)
            x3 = self.x + 0.5 * self.dt * dx2
            y3 = self.y + 0.5 * self.dt * dy2
            z3 = self.z + 0.5 * self.dt * dz2

            dx3, dy3, dz3 = self._deriv(x3, y3, z3)
            x4 = self.x + self.dt * dx3
            y4 = self.y + self.dt * dy3
            z4 = self.z + self.dt * dz3

            dx4, dy4, dz4 = self._deriv(x4, y4, z4)

            self.x += self.dt / 6.0 * (dx1 + 2 * dx2 + 2 * dx3 + dx4)
            self.y += self.dt / 6.0 * (dy1 + 2 * dy2 + 2 * dy3 + dy4)
            self.z += self.dt / 6.0 * (dz1 + 2 * dz2 + 2 * dz3 + dz4)

        self.trail.append((self.x, self.y, self.z))
        if len(self.trail) > self.max_trail:
            self.trail.pop(0)


# ── 3D Renderer ─────────────────────────────────────────────
class Renderer:
    """Renders the Lorenz attractor in a terminal buffer."""

    def __init__(self):
        self.rot_x = 0.3      # initial rotation around X axis
        self.rot_z = 0.0      # rotation around Z axis
        self.auto_rotate = True
        self.rot_speed = 0.015
        self.scale = 4.5       # how much to scale the attractor
        self.focal = 200.0     # perspective focal length
        self.cam_dist = 60.0   # camera distance

    def _rotate(self, x, y, z):
        """Rotate point around Z then X axis."""
        cos_z, sin_z = math.cos(self.rot_z), math.sin(self.rot_z)
        x1 = x * cos_z - y * sin_z
        y1 = x * sin_z + y * cos_z
        z1 = z

        cos_x, sin_x = math.cos(self.rot_x), math.sin(self.rot_x)
        y2 = y1 * cos_x - z1 * sin_x
        z2 = y1 * sin_x + z1 * cos_x

        return x1, y2, z2

    def render(self, lorenz, palette_fn, cols, rows):
        """Render the full trail to a 2D buffer."""
        buf = [[" "] * cols for _ in range(rows)]
        colour_buf = [[(0, 0, 0)] * cols for _ in range(rows)]
        depth_buf = [[0.0] * cols for _ in range(rows)]

        # Centre of the Lorenz attractor is roughly (0, 0, 25)
        cx, cy, cz = 0, 0, 25

        # Screen mapping
        aspect = cols / max(rows, 1)
        fov = self.focal * self.scale

        for i, (px, py, pz) in enumerate(lorenz.trail):
            # Normalise around centre
            rx, ry, rz = px - cx, py - cy, pz - cz

            # Rotate
            sx, sy, sz = self._rotate(rx, ry, rz)

            # Translate camera
            sz += self.cam_dist

            if sz <= 1:
                continue

            # Project to 2D
            screen_x = int(sx * fov / (sz * aspect) + cols / 2)
            screen_y = int(sy * fov / sz + rows / 2)

            if 0 <= screen_x < cols and 0 <= screen_y < rows:
                depth = sz / (self.cam_dist + 30)
                t = i / max(len(lorenz.trail) - 1, 1)

                # Velocity-based colour intensity
                if i > 0:
                    ox, oy, oz = lorenz.trail[i - 1]
                    vel = math.sqrt(
                        (px - ox) ** 2 + (py - oy) ** 2 + (pz - oz) ** 2
                    )
                    intensity = min(1.0, vel / 1.5)
                else:
                    intensity = 0.5

                colour = palette_fn(t)
                # Modulate by intensity
                colour = tuple(int(c * (0.3 + 0.7 * intensity)) for c in colour)

                # Only draw if closer to camera (z-buffer)
                if depth < depth_buf[screen_y][screen_x] or depth_buf[screen_y][screen_x] == 0:
                    # Depth shading for ASCII
                    depth_idx = min(DEPTH_LEN - 1, int(depth * DEPTH_LEN * 0.8))
                    ch = DEPTH_CHARS[depth_idx]
                    buf[screen_y][screen_x] = ch
                    colour_buf[screen_y][screen_x] = colour
                    depth_buf[screen_y][screen_x] = depth

        return buf, colour_buf


# ── Input ───────────────────────────────────────────────────
def read_key():
    """Read a single keypress (non-blocking on Linux/macOS, blocking on Windows)."""
    if sys.platform == "win32":
        import msvcrt
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                ch2 = msvcrt.getwch()
                return ("arrow", ch2)
            return ("key", ch)
        return None
    else:
        import select
        if select.select([sys.stdin], [], [], 0)[0]:
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                if select.select([sys.stdin], [], [], 0)[0]:
                    ch2 = sys.stdin.read(1)
                    if ch2 == "[":
                        ch3 = sys.stdin.read(1)
                        return ("arrow", ch3)
                return ("key", "escape")
            return ("key", ch)
        return None


# ── Main Loop ───────────────────────────────────────────────
def main():
    lorenz = Lorenz()
    renderer = Renderer()

    palette_names = list(PALETTES.keys())
    palette_idx = 0

    paused = False
    speed = 1  # steps per frame
    fps = 30
    frame_time = 1.0 / fps

    # Raw mode for terminal input
    has_tty = False
    old_settings = None
    if sys.platform != "win32" and sys.stdin.isatty():
        import tty
        import termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        has_tty = True

        def restore_terminal():
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        import atexit
        atexit.register(restore_terminal)

    print(HIDE, end="", flush=True)
    print("\033[2J", end="", flush=True)  # clear screen

    try:
        while True:
            t_start = time.monotonic()

            # Input
            event = read_key()
            if event:
                kind, val = event
                if kind == "key":
                    if val in ("q", "escape"):
                        break
                    elif val == "p":
                        palette_idx = (palette_idx + 1) % len(palette_names)
                    elif val == "r":
                        lorenz.reset()
                    elif val == " ":
                        paused = not paused
                    elif val == "+":
                        speed = min(20, speed + 1)
                    elif val == "-":
                        speed = max(1, speed - 1)
                    elif val == "z":
                        lorenz.beta = max(0.5, lorenz.beta - 0.1)
                    elif val == "Z":
                        lorenz.beta = min(10.0, lorenz.beta + 0.1)
                elif kind == "arrow":
                    if val == "D":  # left
                        lorenz.sigma = max(1.0, lorenz.sigma - 0.5)
                    elif val == "C":  # right
                        lorenz.sigma = min(30.0, lorenz.sigma + 0.5)
                    elif val == "A":  # up
                        lorenz.rho = max(1.0, lorenz.rho - 1.0)
                    elif val == "B":  # down
                        lorenz.rho = min(50.0, lorenz.rho + 1.0)

            # Update
            if not paused:
                lorenz.step(steps=speed)

            # Auto-rotate
            if renderer.auto_rotate and not paused:
                renderer.rot_z += renderer.rot_speed

            # Render
            size = term_size()
            cols, rows = size.columns, size.lines - 1  # reserve line for HUD

            buf, colour_buf = renderer.render(
                lorenz, PALETTES[palette_names[palette_idx]], cols, rows
            )

            # Build output
            lines = []
            lines.append(HOME)

            for y in range(rows):
                row_parts = []
                for x in range(cols):
                    ch = buf[y][x]
                    if ch != " ":
                        r, g, b = colour_buf[y][x]
                        row_parts.append(f"\033[38;2;{r};{g};{b}m{ch}")
                    else:
                        row_parts.append(" ")
                lines.append("".join(row_parts) + RESET)

            # HUD line
            palette_name = palette_names[palette_idx]
            status = "⏸ PAUSED" if paused else "▶ RUNNING"
            hud = (
                f"{BOLD}\033[38;2;100;200;255m"
                f" Lorenz Attractor {RESET} "
                f"σ={lorenz.sigma:.1f} ρ={lorenz.rho:.1f} β={lorenz.beta:.2f} "
                f"│ {palette_name} │ {status} │ "
                f"[←→σ ↑↓ρ z/Zβ p:palette ±:speed r:reset q:quit]{RESET}"
            )
            lines.append(hud)

            print("\n".join(lines), end="", flush=True)

            # Frame pacing
            elapsed = time.monotonic() - t_start
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        pass
    finally:
        if has_tty and old_settings is not None:
            import termios
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print(SHOW + RESET, end="", flush=True)
        print("\033[2J\033[H", end="", flush=True)
        print(f"{BOLD}Lorenz Attractor{RESET} — Auf Wiedersehen! 🦋")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Raycaster — Terminal 3D First-Person Engine 🏰
===============================================

Wolfenstein 3D-style raycasting engine running entirely in the terminal.
Render a 3D view with ASCII shading, WASD movement, coloured walls, and a minimap.

Controls:
  W/A/S/D  — move forward/left/backward/right
  ←/→      — rotate left/right
  M        — toggle minimap
  Space    — toggle mouse-look smooth turning
  Q        — quit

No dependencies beyond the Python standard library.
"""

import os
import sys
import time
import math
import tty
import termios
import select
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

# ─── Helpers ─────────────────────────────────────────────────────────────

if sys.platform == "win32":
    import msvcrt

    def get_key() -> str:
        """Non-blocking key read on Windows."""
        if msvcrt.kbhit():
            b = msvcrt.getch()
            if b == b"\xe0":
                b2 = msvcrt.getch()
                mapping = {b"H": "UP", b"P": "DOWN", b"M": "RIGHT", b"K": "LEFT"}
                return mapping.get(b2, b2.decode("utf-8", errors="replace"))
            return b.decode("utf-8", errors="replace")
        return ""

    def setup_terminal():
        pass

    def reset_terminal():
        pass

else:
    def get_key() -> str:
        """Non-blocking key read on Unix (single char)."""
        if select.select([sys.stdin], [], [], 0)[0]:
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                # Check for escape sequences
                if select.select([sys.stdin], [], [], 0.05)[0]:
                    seq = sys.stdin.read(2)
                    if seq == "[A":
                        return "UP"
                    elif seq == "[B":
                        return "DOWN"
                    elif seq == "[C":
                        return "RIGHT"
                    elif seq == "[D":
                        return "LEFT"
                    elif seq == "[H":
                        return "HOME"
                    elif seq == "[F":
                        return "END"
                return "ESC"
            return ch
        return ""

    fd: int = 0

    def setup_terminal():
        global fd
        fd = sys.stdin.fileno()
        tty.setcbreak(fd)

    def reset_terminal():
        os.system("stty sane" if os.name == "posix" else "")


# ─── ANSI ────────────────────────────────────────────────────────────────

@dataclass
class ANSI:
    """Terminal control sequences."""
    CLEAR = "\033[2J"
    HOME = "\033[H"
    HIDE = "\033[?25l"
    SHOW = "\033[?25h"
    RESET = "\033[0m"

    @staticmethod
    def fg(r: int, g: int, b: int) -> str:
        return f"\033[38;2;{r};{g};{b}m"

    @staticmethod
    def bg(r: int, g: int, b: int) -> str:
        return f"\033[48;2;{r};{g};{b}m"

    # Wall colour palettes
    WALL_COLORS = {
        1: (200, 60, 60),     # Red brick
        2: (60, 180, 60),     # Green stone
        3: (60, 80, 200),     # Blue metal
        4: (200, 180, 60),    # Gold
        5: (180, 60, 180),    # Purple
        6: (200, 120, 60),    # Orange
    }

    CEILING = (30, 30, 60)
    FLOOR = (40, 30, 20)


# ─── Map ─────────────────────────────────────────────────────────────────

# Legend:
#   0 = empty, 1-6 = walls with different colours
SIMPLE_MAP = [
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 2, 2, 2, 0, 0, 0, 0, 3, 0, 3, 0, 0, 1],
    [1, 0, 0, 2, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 2, 0, 2, 0, 0, 0, 0, 4, 0, 4, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 5, 5, 5, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 6, 0, 0, 6, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 6, 0, 0, 6, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 6, 6, 6, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
]

# A larger, more interesting map
LABYRINTH_MAP = [
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 2, 2, 2, 2, 0, 0, 3, 0, 3, 0, 0, 4, 4, 0, 0, 0, 1],
    [1, 0, 0, 2, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 4, 0, 0, 0, 1],
    [1, 0, 0, 2, 0, 0, 2, 0, 0, 5, 0, 5, 0, 0, 0, 4, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 5, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 4, 0, 0, 0, 0, 0, 3, 3, 3, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 6, 6, 6, 6, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
]


# ─── Raycaster Engine ────────────────────────────────────────────────────

# ASCII shade ramp for walls — from closest (darkest) to farthest (brightest)
WALL_SHADES = "█▓▒░ "  # 5 levels: solid to empty-ish
# Alternative ramps:
# WALL_SHADES = "█▇▆▅▄▃▂▁ "
# WALL_SHADES = "@%#*+=-:. "


@dataclass
class Player:
    x: float = 2.5
    y: float = 2.5
    angle: float = 0.0
    fov: float = math.pi / 3  # 60 degrees


@dataclass
class Config:
    """Rendering configuration."""
    width: int = 100          # Number of rays / columns
    height: int = 40          # Terminal display height
    map_w: int = 0
    map_h: int = 0
    wall_height: float = 1.0  # Relative wall height
    move_speed: float = 3.0
    rot_speed: float = 2.5
    show_minimap: bool = True
    smooth_turn: bool = False
    minimap_size: int = 10     # Viewport radius in cells
    minimap_scale: int = 1     # Cells per character
    auto_rotate: float = 0.0   # Auto-rotation speed (0 = off)
    use_color: bool = True


class Raycaster:
    """The core rendering engine."""

    def __init__(self, game_map: List[List[int]], config: Config):
        self.map = game_map
        self.cfg = config
        self.cfg.map_h = len(game_map)
        self.cfg.map_w = len(game_map[0]) if game_map else 0
        self.player = Player()

        # Find first empty cell for player start
        for y in range(self.cfg.map_h):
            for x in range(self.cfg.map_w):
                if game_map[y][x] == 0:
                    self.player.x = x + 0.5
                    self.player.y = y + 0.5
                    self.player.angle = 0.0
                    break
            else:
                continue
            break

        self.frame_time = 0.016  # ~60fps default
        self.render_buf: List[str] = []
        self.zbuffer: List[float] = []

    def cast_ray(self, ray_angle: float) -> Tuple[float, int, int, float]:
        """
        DDA raycasting algorithm.
        Returns (distance, wall_x, wall_y, wall_side) where:
          - distance is perpendicular distance (fish-eye corrected)
          - wall_x, wall_y are the map coordinates of the wall hit
          - wall_side is 0 for x-side, 1 for y-side
        """
        # Direction vector
        dir_x = math.cos(ray_angle)
        dir_y = math.sin(ray_angle)

        # Which grid cell we're in
        map_x = int(self.player.x)
        map_y = int(self.player.y)

        # Length of ray from one x-side or y-side to the next
        delta_dist_x = abs(1.0 / dir_x) if dir_x != 0 else 1e30
        delta_dist_y = abs(1.0 / dir_y) if dir_y != 0 else 1e30

        # Step direction and initial side distances
        if dir_x < 0:
            step_x = -1
            side_dist_x = (self.player.x - map_x) * delta_dist_x
        else:
            step_x = 1
            side_dist_x = (map_x + 1.0 - self.player.x) * delta_dist_x

        if dir_y < 0:
            step_y = -1
            side_dist_y = (self.player.y - map_y) * delta_dist_y
        else:
            step_y = 1
            side_dist_y = (map_y + 1.0 - self.player.y) * delta_dist_y

        # DDA loop
        hit = False
        side = 0  # 0 = x-side, 1 = y-side
        max_steps = max(self.cfg.map_w, self.cfg.map_h) * 2

        for _ in range(max_steps):
            if side_dist_x < side_dist_y:
                side_dist_x += delta_dist_x
                map_x += step_x
                side = 0
            else:
                side_dist_y += delta_dist_y
                map_y += step_y
                side = 1

            if map_x < 0 or map_x >= self.cfg.map_w or map_y < 0 or map_y >= self.cfg.map_h:
                break

            if self.map[map_y][map_x] > 0:
                hit = True
                break

        if not hit:
            return 1e30, 0, 0, 0

        # Perpendicular distance (avoids fish-eye)
        if side == 0:
            perp_dist = (map_x - self.player.x + (1 - step_x) / 2) / dir_x
        else:
            perp_dist = (map_y - self.player.y + (1 - step_y) / 2) / dir_y

        return perp_dist, map_x, map_y, side

    def render_frame(self) -> None:
        """Render a single frame into render_buf."""
        cfg = self.cfg
        player = self.player
        half_height = cfg.height // 2
        render: List[str] = []

        self.zbuffer = []

        for col in range(cfg.width):
            # Calculate ray angle for this column
            fraction = col / cfg.width
            ray_angle = player.angle - player.fov / 2 + fraction * player.fov
            dist, wall_x, wall_y, side = self.cast_ray(ray_angle)

            self.zbuffer.append(dist)

            # Calculate wall height on screen
            if dist > 0.001:
                wall_screen_height = int(cfg.height / dist * cfg.wall_height)
            else:
                wall_screen_height = cfg.height

            if wall_screen_height > cfg.height:
                wall_screen_height = cfg.height

            # Wall top and bottom on screen
            wall_top = max(0, half_height - wall_screen_height // 2)
            wall_bottom = min(cfg.height - 1, half_height + wall_screen_height // 2)

            # Shade based on distance
            shade_idx = min(int(dist * 1.5), len(WALL_SHADES) - 1)
            shade_char = WALL_SHADES[shade_idx]

            # Get wall colour
            wall_type = 0
            if 0 <= wall_y < cfg.map_h and 0 <= wall_x < cfg.map_w:
                wall_type = self.map[wall_y][wall_x]

            wall_color = ANSI.WALL_COLORS.get(wall_type, (180, 180, 180))

            # Darken walls on y-side for depth cue
            if side == 1:
                wall_color = tuple(int(c * 0.7) for c in wall_color)

            # Build column string
            col_chars = []
            for row in range(cfg.height):
                if row < wall_top:
                    # Ceiling
                    if cfg.use_color:
                        ceil_shade = min(row, half_height) / max(half_height, 1)
                        c = tuple(int(ANSI.CEILING[i] * (0.5 + 0.5 * ceil_shade)) for i in range(3))
                        col_chars.append(f"{ANSI.bg(*c)} {ANSI.RESET}")
                    else:
                        col_chars.append(" ")
                elif row < wall_bottom:
                    # Wall
                    if cfg.use_color:
                        col_chars.append(f"{ANSI.fg(*wall_color)}{shade_char}{ANSI.RESET}")
                    else:
                        col_chars.append(shade_char)
                else:
                    # Floor
                    if cfg.use_color:
                        floor_shade = (row - wall_bottom) / max(cfg.height - wall_bottom, 1)
                        c = tuple(int(ANSI.FLOOR[i] * (0.5 + 0.5 * floor_shade)) for i in range(3))
                        col_chars.append(f"{ANSI.bg(*c)} {ANSI.RESET}")
                    else:
                        col_chars.append(" ")

            render.append("".join(col_chars))

        # Combine columns side by side
        lines = [""] * cfg.height
        for col_idx in range(cfg.width):
            col_data = render[col_idx]
            for row in range(cfg.height):
                lines[row] += col_data[row]

        # Overlay minimap
        if cfg.show_minimap:
            self._render_minimap(lines)

        self.render_buf = lines

    def _render_minimap(self, lines: List[str]) -> None:
        """Draw a minimap overlay in the top-left corner."""
        cfg = self.cfg
        px = int(self.player.x)
        py = int(self.player.y)

        # Minimap dimensions (in cells, centered on player)
        msize = cfg.minimap_size
        start_x = max(0, px - msize // 2)
        start_y = max(0, py - msize // 2)
        end_x = min(cfg.map_w, start_x + msize)
        end_y = min(cfg.map_h, start_y + msize)

        # Adjust start if we hit map edge
        if end_x - start_x < msize:
            start_x = max(0, end_x - msize)
        if end_y - start_y < msize:
            start_y = max(0, end_y - msize)

        map_lines: List[str] = []
        header = "╔" + "═" * (end_x - start_x) + "╗"
        footer = "╚" + "═" * (end_x - start_x) + "╝"
        map_lines.append(f"\033[38;2;150;150;150m{header}\033[0m")

        rel_px = px - start_x
        rel_py = py - start_y

        for my in range(start_y, end_y):
            row = "║"
            for mx in range(start_x, end_x):
                if mx == px and my == py:
                    # Player position
                    row += f"\033[38;2;255;255;0m@\033[38;2;150;150;150m"
                elif self.map[my][mx] > 0:
                    wc = ANSI.WALL_COLORS.get(self.map[my][mx], (150, 150, 150))
                    row += f"\033[38;2;{wc[0]};{wc[1]};{wc[2]}m█\033[38;2;150;150;150m"
                else:
                    row += "\033[38;2;60;60;60m.\033[38;2;150;150;150m"
            row += "║"
            map_lines.append(row)

        map_lines.append(footer)

        # Direction indicator
        dir_x = math.cos(self.player.angle)
        dir_y = math.sin(self.player.angle)
        dir_str = f"  {dir_x:+.2f},{dir_y:+.2f}"

        # Info line
        info = f" \033[38;2;100;200;100m♥\033[0m ({self.player.x:.1f}, {self.player.y:.1f}) ∠{self.player.angle * 180 / math.pi:.0f}°"

        # Overlay onto render buffer
        for i, ml in enumerate(map_lines):
            if i < cfg.height:
                # Add map on left side
                line = lines[i]
                prefix = ml + " "
                if len(prefix) < len(line):
                    lines[i] = prefix + line[len(prefix):]
                else:
                    lines[i] = prefix
            else:
                break

        # Add info line
        info_line = info + dir_str
        if len(map_lines) < cfg.height:
            lines[len(map_lines)] = info_line + lines[len(map_lines)][len(info_line):] if len(info_line) < len(lines[len(map_lines)]) else info_line

    def update(self, dt: float, keys_pressed: set) -> None:
        """Update player position and rotation based on input."""
        cfg = self.cfg
        player = self.player
        move = cfg.move_speed * dt
        rot = cfg.rot_speed * dt

        # Rotation
        if "LEFT" in keys_pressed:
            player.angle -= rot
        if "RIGHT" in keys_pressed:
            player.angle += rot
        if cfg.smooth_turn and cfg.auto_rotate == 0:
            player.angle += rot * 0.3  # gentle drift when smooth turn is on

        # Auto-rotation
        if cfg.auto_rotate != 0:
            player.angle += cfg.auto_rotate * dt

        # Normalize angle
        player.angle %= math.tau

        # Direction vector
        dir_x = math.cos(player.angle)
        dir_y = math.sin(player.angle)

        # Perpendicular direction for strafing
        perp_x = math.cos(player.angle + math.pi / 2)
        perp_y = math.sin(player.angle + math.pi / 2)

        # Movement
        move_x = 0.0
        move_y = 0.0

        if "w" in keys_pressed:
            move_x += dir_x * move
            move_y += dir_y * move
        if "s" in keys_pressed:
            move_x -= dir_x * move
            move_y -= dir_y * move
        if "a" in keys_pressed:
            move_x -= perp_x * move
            move_y -= perp_y * move
        if "d" in keys_pressed:
            move_x += perp_x * move
            move_y += perp_y * move

        # Collision detection (sliding along walls)
        new_x = player.x + move_x
        new_y = player.y + move_y

        # Check each axis separately for sliding
        if 0 < new_x < cfg.map_w - 1:
            if self.map[int(player.y)][int(new_x)] == 0:
                player.x = new_x
        if 0 < new_y < cfg.map_h - 1:
            if self.map[int(new_y)][int(player.x)] == 0:
                player.y = new_y

        # Keep within bounds
        player.x = max(0.5, min(cfg.map_w - 1.5, player.x))
        player.y = max(0.5, min(cfg.map_h - 1.5, player.y))


# ─── Main Loop ───────────────────────────────────────────────────────────

def main():
    # Terminal setup
    setup_terminal()

    # Print ANSI clear + hide cursor once
    sys.stdout.write(ANSI.CLEAR + ANSI.HIDE)
    sys.stdout.flush()

    # Detect terminal width/height for auto-config
    try:
        term_cols, term_rows = os.get_terminal_size()
    except (ValueError, OSError):
        term_cols, term_rows = 120, 40

    # Config — use full terminal width minus some margin
    cfg = Config()
    cfg.width = min(100, term_cols - 20)   # Leave room for minimap
    cfg.height = min(40, term_rows - 2)
    cfg.show_minimap = True

    # Use the labyrinth map (bigger, more interesting)
    game_map = LABYRINTH_MAP
    # game_map = SIMPLE_MAP  # toggle for simple map

    engine = Raycaster(game_map, cfg)

    # ── Instructions ──
    instructions = (
        f"\033[38;2;100;200;100m🏰 Raycaster\033[0m  "
        f"\033[38;2;150;150;150m"
        f"W/A/S/D:move  ←/→:rotate  M:map  Space:smooth  Q:quit"
        f"\033[0m"
    )

    # Show instructions once
    sys.stdout.write(f"\033[1;1H{ANSI.CLEAR}\033[1;1H{instructions}\n")

    running = True
    keys_pressed: set = set()
    prev_time = time.perf_counter()

    try:
        while running:
            now = time.perf_counter()
            dt = min(now - prev_time, 0.05)  # Cap at 20fps min
            prev_time = now

            # Handle input
            key = get_key()
            if key:
                if key.lower() == "q":
                    running = False
                    break
                elif key.lower() == "m":
                    cfg.show_minimap = not cfg.show_minimap
                elif key == " ":
                    cfg.smooth_turn = not cfg.smooth_turn
                elif key == "r":
                    cfg.auto_rotate = 1.0 if cfg.auto_rotate == 0 else 0.0
                elif key == "f":
                    cfg.use_color = not cfg.use_color
                elif key in ("w", "a", "s", "d", "LEFT", "RIGHT", "UP", "DOWN"):
                    keys_pressed.add(key)
                elif key == "ESC":
                    keys_pressed.clear()
            else:
                # No new key, gradually release keys
                # (keys are one-shot, so they clear themselves)
                keys_pressed.clear()

            # Also check held keys periodically via the one-shot nature
            # In real-time mode, we use a different approach:
            # Since get_key() is non-blocking, keys are tap-based, not held.

            # Update engine with any buffered key
            # For smooth movement, we re-read keys rapidly
            engine.update(dt, keys_pressed)

            # Clear keys after processing (tap-based movement)
            keys_pressed.clear()

            # Render
            engine.render_frame()

            # Build final output
            out_lines = []
            for i, line in enumerate(engine.render_buf):
                # Trim trailing spaces
                out_lines.append(line)

            fps = 1.0 / max(dt, 0.001)
            hud = f"\033[38;2;150;150;150m[{fps:5.1f} FPS] [{cfg.width}×{cfg.height}] "
            hud += f"∠{engine.player.angle * 180 / math.pi:3.0f}° "
            hud += f"\033[38;2;100;200;100m{'🔮' if cfg.smooth_turn else '   '}"
            hud += f"\033[38;2;150;150;150m"
            hud += f" {'📐' if cfg.auto_rotate else '   '}"
            hud += f"\033[0m"

            # Write frame
            sys.stdout.write(f"\033[2;1H")  # Move below instructions
            sys.stdout.write("\n".join(out_lines))
            sys.stdout.write(f"\n{hud}")
            sys.stdout.flush()

            # Frame rate control — target ~30fps
            elapsed = time.perf_counter() - now
            sleep_time = max(0, 1/30 - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        pass
    finally:
        reset_terminal()
        sys.stdout.write(ANSI.SHOW + ANSI.RESET + f"\033[{cfg.height + 3};1H")  # Move cursor below frame
        sys.stdout.write("\n👋 Até à próxima!\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()

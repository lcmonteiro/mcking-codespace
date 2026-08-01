#!/usr/bin/env python3
"""
donut.py — Terminal Donut 🍩
============================
Classic demoscene rotating 3D torus — the famous one-liner, grown up.

Three solid shapes (torus / sphere / cube) built as 3D meshes, rotated
around two axes every frame, perspective-projected, Lambert-shaded and
rendered to an ANSI truecolor terminal with the half-block trick (each
cell draws ▀ with fg = top sample, bg = bottom sample) for 2× vertical
resolution. A z-buffer hides the far side exactly like the original.

Usage:
    python donut.py            # interactive
    python donut.py --once     # render a single ASCII frame and exit (demos/tests)

Controls:
    q/ESC  — quit
    1-5    — palette presets
    c      — cycle palette continuously
    s      — next shape (torus → sphere → cube)
    w      — toggle wireframe mode
    f      — toggle ASCII ramp mode
    +/-    — rotation speed
    a      — pause rotation (shape keeps rendering)
    SPACE  — pause/resume animation
    r      — reset settings

Palettes:
    1 — Lava (red/orange/yellow)
    2 — Ocean (blue/cyan/teal)
    3 — Neon (magenta/pink/blue)
    4 — Forest (green/yellow/brown)
    5 — Ice (cyan/white/purple)

Zero external dependencies. Pure stdlib.
ANSI truecolor required (modern terminals only).

Author: Mcking (AI assistant do Luis Monteiro)
Data: 2026-08-01
"""

import math
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

# ASCII ramp for ramp mode (dark → bright)
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
# Each palette is a list of colour stops; brightness t ∈ [0,1] maps across them,
# dark in shadow → bright on lit surface.

Palette = List[Tuple[int, int, int]]

PALETTES: List[Tuple[str, Palette]] = [
    ("Lava", [
        (8, 0, 0),        # near-black
        (80, 12, 0),      # dark red
        (220, 40, 0),     # red
        (255, 120, 0),    # orange
        (255, 200, 60),   # yellow
        (255, 250, 210),  # white-hot
    ]),
    ("Ocean", [
        (0, 4, 20),       # deep blue-black
        (0, 35, 90),      # dark blue
        (0, 90, 185),     # blue
        (0, 165, 230),    # cyan-blue
        (55, 220, 210),   # teal
        (215, 250, 255),  # foam white
    ]),
    ("Neon", [
        (12, 0, 22),      # dark purple
        (85, 0, 125),     # purple
        (205, 0, 160),    # magenta
        (255, 55, 215),   # pink
        (115, 210, 255),  # cyan
        (240, 240, 255),  # cold white
    ]),
    ("Forest", [
        (4, 10, 0),       # dark green-black
        (14, 50, 10),     # deep green
        (32, 105, 24),    # forest green
        (85, 170, 45),    # green
        (185, 210, 70),   # yellow-green
        (240, 250, 200),  # pale
    ]),
    ("Ice", [
        (4, 9, 24),       # midnight
        (18, 38, 78),     # dark blue
        (58, 118, 190),   # steel blue
        (138, 198, 240),  # ice blue
        (218, 245, 255),  # pale cyan
        (255, 255, 255),  # white
    ]),
]

AMBIENT   = 0.16   # shadow-side brightness floor
LIGHT     = (-0.45, 0.75, 0.80)   # light direction (normalised below)
CAM_DIST  = 5.0    # camera distance in object units


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


# ── Meshes ─────────────────────────────────────────────────────────────────────────────────────────
# Each mesh is a list of vertices (x, y, z, nx, ny, nz, edge) in object space.
# `edge` marks vertices that lie on a wireframe iso-line.

Vec = Tuple[float, float, float]


def _normalize(v: Vec) -> Vec:
    l = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / l, v[1] / l, v[2] / l)


def mesh_torus(R: float = 1.0, r: float = 0.42, nu: int = 64, nv: int = 32) -> List[Tuple[float, float, float, float, float, float, bool]]:
    """Torus: major radius R, minor radius r. Grid nu × nv."""
    verts = []
    for i in range(nu):
        u = 2.0 * math.pi * i / nu
        cu, su = math.cos(u), math.sin(u)
        for j in range(nv):
            v = 2.0 * math.pi * j / nv
            cv, sv = math.cos(v), math.sin(v)
            x = (R + r * cv) * cu
            y = (R + r * cv) * su
            z = r * sv
            # normal of the tube surface
            nx, ny, nz = _normalize((cv * cu, cv * su, sv))
            edge = (i % 8 == 0) or (j % 4 == 0)
            verts.append((x, y, z, nx, ny, nz, edge))
    return verts


def mesh_sphere(radius: float = 1.25, nu: int = 56, nv: int = 28) -> List[Tuple[float, float, float, float, float, float, bool]]:
    """Sphere by latitude/longitude. Normal = position."""
    verts = []
    for i in range(nu):
        u = 2.0 * math.pi * i / nu
        cu, su = math.cos(u), math.sin(u)
        for j in range(1, nv):          # skip poles for even spacing
            v = math.pi * j / nv
            cv, sv = math.cos(v), math.sin(v)
            x = radius * cv * cu
            y = radius * cv * su
            z = radius * sv
            verts.append((x, y, z, x / radius, y / radius, z / radius,
                          (i % 7 == 0) or (j % 3 == 0)))
    return verts


def mesh_cube(half: float = 1.05, sub: int = 11) -> List[Tuple[float, float, float, float, float, float, bool]]:
    """Cube: 6 faces subdivided into (sub+1)² points, per-face normals."""
    verts = []
    faces = [  # (axis index, sign, tangent A, tangent B)
        (0,  1, 1, 2),   # +x
        (0, -1, 1, 2),   # -x
        (1,  1, 0, 2),   # +y
        (1, -1, 0, 2),   # -y
        (2,  1, 0, 1),   # +z
        (2, -1, 0, 1),   # -z
    ]
    for axis, sign, ta, tb in faces:
        for i in range(sub + 1):
            for j in range(sub + 1):
                t, s = -half + 2 * half * i / sub, -half + 2 * half * j / sub
                p = [0.0, 0.0, 0.0]
                p[axis] = half * sign
                p[ta] = t
                p[tb] = s
                n = [0.0, 0.0, 0.0]
                n[axis] = float(sign)
                edge = (i == 0 or i == sub or j == 0 or j == sub)
                verts.append((p[0], p[1], p[2], n[0], n[1], n[2], edge))
    return verts


SHAPES = [
    ("torus",  mesh_torus(),  (0.9, 0.5)),   # name, mesh, spin speeds (x, y)
    ("sphere", mesh_sphere(), (0.4, 0.9)),
    ("cube",   mesh_cube(),   (0.6, 0.8)),
]


# ── Donut ──────────────────────────────────────────────────────────────────────────────────────────

class Donut:
    """Interactive terminal 3D-shape effect."""

    def __init__(self) -> None:
        self.w, self.h = self._get_size()
        self.shape_idx : int = 0
        self.palette_idx : int = 0
        self.time      : float = 0.0
        self.paused    : bool = False
        self.rot_paused: bool = False
        self.auto_cycle: bool = False
        self.wireframe : bool = False
        self.ramp_mode : bool = False
        self.speed     : float = 1.0
        self.cycle_timer : float = 0.0
        self.running   : bool = True
        self.last_fps  : float = 60.0
        self.angle_x   : float = 0.0
        self.angle_y   : float = 0.0
        self.light     = _normalize(LIGHT)

    # === Setup =====================================================================================

    @staticmethod
    def _get_size() -> Tuple[int, int]:
        """Get terminal size, fallback 80x24."""
        try:
            import shutil
            w, h = shutil.get_terminal_size((80, 24))
            return w, max(h - 1, 10)          # leave one row for the status bar
        except Exception:
            return 80, 24

    # === Input =====================================================================================

    def _read_key(self) -> Optional[str]:
        """Read one keypress without blocking. Returns None if no key."""
        try:
            if sys.platform == "win32":
                import msvcrt
                if msvcrt.kbhit():
                    k = msvcrt.getwch()
                    if k == '\xe0':
                        msvcrt.getwch()       # arrow keys, ignore
                        return None
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
                                if rest:
                                    return None  # arrow/escape sequence
                                return 'q'       # ESC key = quit
                            return ch
                        finally:
                            termios.tcsetattr(fd, termios.TCSADRAIN, old)
                    except termios.error:
                        return None             # not a TTY
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
        elif key == 'a' or key == 'A':
            self.rot_paused = not self.rot_paused
        elif key == '+':
            self.speed = min(self.speed * 1.25, 8.0)
        elif key == '-':
            self.speed = max(self.speed / 1.25, 0.125)
        elif key == 's' or key == 'S':
            self.shape_idx = (self.shape_idx + 1) % len(SHAPES)
        elif key == 'w' or key == 'W':
            self.wireframe = not self.wireframe
        elif key == 'f' or key == 'F':
            self.ramp_mode = not self.ramp_mode
        elif key == 'r' or key == 'R':
            self.wireframe = False
            self.ramp_mode = False
            self.auto_cycle = False
            self.rot_paused = False
            self.speed = 1.0
            self.paused = False
        elif key == 'c' or key == 'C':
            self.auto_cycle = not self.auto_cycle
        elif key in '12345':
            self.palette_idx = int(key) - 1
            self.auto_cycle = False

    # === Rendering =================================================================================

    def _render(self) -> str:
        """Build the full ANSI frame string."""
        w, h = self.w, self.h
        sh = h * 2                       # sample space (2 samples per cell, vertical)
        palette = PALETTES[self.palette_idx][1]
        name, mesh, (sx, sy) = SHAPES[self.shape_idx]

        cx, cy = w / 2.0, h             # sample-space centre
        focal = w * 0.95
        ca, sa = math.cos(self.angle_x), math.sin(self.angle_x)
        cb, sb = math.cos(self.angle_y), math.sin(self.angle_y)
        lx, ly, lz = self.light

        # ── pass 1: transform + project + shade into z-buffered samples ──
        zbuf = [1e9] * (w * sh)
        vals = [0.0] * (w * sh)
        for (x, y, z, nx, ny, nz, edge) in mesh:
            if self.wireframe and not edge:
                continue

            # rotate around X then Y
            y1 = y * ca - z * sa
            z1 = y * sa + z * ca
            x2 = x * cb + z1 * sb
            z2 = -x * sb + z1 * cb
            y2 = y1

            depth = CAM_DIST - z2        # smaller = closer to camera
            if depth <= 0.25:
                continue
            proj = focal / depth
            px = int(cx + x2 * proj)
            py = int(cy - y2 * proj)     # sample row (0 = top)

            if px < 0 or px >= w or py < 0 or py >= sh:
                continue
            idx = py * w + px
            if depth >= zbuf[idx]:
                continue
            zbuf[idx] = depth

            # Lambert: n·L with an ambient floor
            d = nx * lx + ny * ly + nz * lz
            t = AMBIENT + (1.0 - AMBIENT) * max(0.0, d)
            if t > 1.0:
                t = 1.0
            vals[idx] = t

        # ── pass 2: combine top/bottom samples into half-block cells ──
        parts: List[str] = [HOME]
        if self.ramp_mode:
            ramp_n = len(RAMP) - 1
            for yi in range(h):
                for xi in range(w):
                    t_cell = (vals[(yi * 2) * w + xi] + vals[(yi * 2 + 1) * w + xi]) * 0.5
                    ch = RAMP[min(int(t_cell * ramp_n), ramp_n)]
                    cr, cg, cb_ = sample_palette(palette, t_cell)
                    parts.append(rgb_fg(cr, cg, cb_) + ch)
                parts.append(RESET)
                parts.append("\n")
        else:
            for yi in range(h):
                for xi in range(w):
                    t_t = vals[(yi * 2) * w + xi]
                    t_b = vals[(yi * 2 + 1) * w + xi]
                    if t_t <= 0.0 and t_b <= 0.0:
                        parts.append(" ")
                        continue
                    cr, cg, cb_ = sample_palette(palette, t_t)
                    dr, dg, db_ = sample_palette(palette, t_b)
                    parts.append(rgb_fg(cr, cg, cb_) + rgb_bg(dr, dg, db_) + "▀")
                parts.append(RESET)
                parts.append("\n")

        # ── status bar ──
        pal_name = PALETTES[self.palette_idx][0]
        mode = "wire" if self.wireframe else ("ramp" if self.ramp_mode else "solid")
        spin = "off" if self.rot_paused else f"{self.speed:.2f}×"
        parts.append(RESET + BOLD)
        parts.append(
            f"🍩 DONUT  {name}  {pal_name}  {mode}  spin {spin}  "
            f"{self.last_fps:4.0f} fps"
        )
        parts.append(RESET)
        parts.append(
            "  [1-5]pal [c]cycle [s]shape [w]wire [f]ramp [+/-]speed [a]spin [space]pause [r]reset [q]quit"
        )
        return "".join(parts)

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

            key = self._read_key()
            if key is not None:
                self.handle_key(key)

            if not self.paused:
                self.time += dt
                if not self.rot_paused:
                    _, _, (sx, sy) = SHAPES[self.shape_idx]
                    # gentle wobble keeps the motion organic
                    wob = 1.0 + 0.15 * math.sin(self.time * 0.7)
                    self.angle_x += sx * dt * self.speed * wob
                    self.angle_y += sy * dt * self.speed

            if self.auto_cycle:
                self.cycle_timer += dt
                if self.cycle_timer >= 5.0:
                    self.cycle_timer = 0.0
                    self.palette_idx = (self.palette_idx + 1) % len(PALETTES)

            sys.stdout.write(self._render())
            sys.stdout.flush()

            self.last_fps = 0.9 * self.last_fps + 0.1 * (1.0 / max(dt, 1e-4))
            elapsed = time.monotonic() - now
            if elapsed < frame_time:
                time.sleep(frame_time - elapsed)

        sys.stdout.write(SHOW + RESET + "\n")


def main() -> None:
    """Entry point."""
    if "--once" in sys.argv:
        # Single ASCII frame for demos/tests — no ANSI, no interactivity.
        import os
        os.environ.setdefault("COLUMNS", "80")
        os.environ.setdefault("LINES", "30")
        d = Donut()
        d.w, d.h = 80, 24
        d.angle_x, d.angle_y = 0.9, 1.3
        d.ramp_mode = True
        frame = d._render()
        # strip colour codes, keep the ramp characters
        import re
        plain = re.sub(r"\033\[[0-9;]*m", "", frame)
        print(plain)
        return
    try:
        Donut().run()
    except KeyboardInterrupt:
        sys.stdout.write(SHOW + RESET + "\n")


if __name__ == "__main__":
    main()

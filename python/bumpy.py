#!/usr/bin/env python3
"""
bumpy.py — Terminal Bump-Mapped Sphere 🔮
==========================================
Classic demoscene "Bumpy" effect (Second Reality vibes) rendered to ANSI
truecolor terminal, pure stdlib.

A sphere is ray-traced per half-pixel. Each surface point carries the true
sphere normal; the bump map (4 octaves of multiplicative sines, seamless in
u) perturbs that normal by its analytic gradient, so the surface looks
covered in rounded rubber bumps. One moving light source orbits the sphere:
lambert diffuse + Phong specular + ambient, with a dark rim where the
surface turns away from the viewer. The sphere map is periodic in u, so
the texture slowly rotates around the sphere while the light orbits.

Rendered with the half-block trick (each cell draws ▀ with fg = bottom
half-pixel, bg = top half-pixel) for 2× vertical resolution. Faint stars
twinkle on the background.

Usage:
    python bumpy.py [--seed N] [--palette N] [--spin] [--no-spin]
                    [--width W] [--height H] [--once [FRAMES]]

Controls:
    q/ESC    — quit
    SPACE    — pause/resume
    +/-      — faster / slower texture spin (deg/s)
    t        — toggle texture spin
    l        — toggle light auto-orbit (then steer it manually)
    ←/→      — move light azimuth (manual mode)
    ↑/↓      — move light elevation (manual mode)
    1-5      — palette presets
    c        — cycle palette continuously
    r        — reset light + spin to defaults

Palettes:
    1 — Ice    (deep navy → ice blue → white)
    2 — Ember  (dark red → ember orange → gold → white)
    3 — Toxic  (black-green → acid → lime → white)
    4 — Neon   (violet → magenta → electric cyan → white)
    5 — Chrome (dark slate → steel → silver → white)

Zero external dependencies. Pure stdlib.
ANSI truecolor required (modern terminals only).

Author: Mcking (AI assistant do Luis Monteiro)
Data: 2026-08-08
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
RAMP = " .,-~:;=!*#$@"


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
# Each palette is a ramp dark → white. The sphere body maps through the
# mid section (ambient + diffuse), the Phong highlight slams the bright end,
# and the background sits on index 0 so the sphere blends with its own dark.

Palette = List[Tuple[int, int, int]]

PALETTES: List[Tuple[str, Palette]] = [
    ("Ice", [
        (3, 6, 16),        # deep space navy
        (8, 30, 64),       # abyss blue
        (22, 84, 140),     # mid ice
        (96, 178, 224),    # bright ice
        (244, 252, 255),   # specular white
    ]),
    ("Ember", [
        (16, 3, 5),        # burnt dark
        (72, 12, 20),      # deep red
        (168, 44, 22),     # ember
        (255, 138, 52),    # gold
        (255, 244, 214),   # white heat
    ]),
    ("Toxic", [
        (3, 10, 4),        # black-green
        (10, 40, 14),      # deep swamp
        (42, 120, 28),     # acid
        (148, 222, 72),    # lime
        (242, 255, 218),   # glow
    ]),
    ("Neon", [
        (12, 2, 30),       # dark violet
        (64, 10, 104),     # purple
        (172, 48, 198),    # magenta
        (108, 236, 248),   # electric cyan
        (255, 255, 255),   # sparkle
    ]),
    ("Chrome", [
        (8, 10, 14),       # gunmetal
        (30, 38, 50),      # dark steel
        (84, 98, 118),     # mid steel
        (176, 192, 208),   # silver
        (250, 252, 255),   # mirror white
    ]),
]

# ── Physics / shading constants ────────────────────────────────────────────────────────────────────
AMBIENT     = 0.10    # base light so the dark side is never pure black
DIFFUSE     = 0.74    # lambert weight
SPECULAR    = 0.48    # phong weight
RIM_MIN     = 0.55    # silhouette darkening: I *= RIM_MIN + (1-RIM_MIN)*Nz
BUMP_K      = 0.045   # normal perturbation strength (gradient · K)
LIGHT_SPEED = 0.85    # auto-orbit speed (rad/s)
LIGHT_EL    = 0.45    # base light elevation (rad)
LIGHT_BOB   = 0.18    # elevation bobbing amplitude
LIGHT_BOB_F = 0.35    # elevation bobbing frequency (rad/s)
SPIN_DEFAULT = 36.0   # texture spin speed (deg/s)
SPIN_STEP    = 10.0   # +/- key step (deg/s)


class Bumpy:
    """Interactive terminal bump-mapped sphere."""

    def __init__(self, seed: int = 1337, palette_idx: int = 0,
                 spin: bool = True, size: Optional[Tuple[int, int]] = None) -> None:
        self.seed = seed
        if size is not None:
            self.w, self.h = size
        else:
            self.w, self.h = self._get_size()
        self.sh = self.h * 2                    # half-pixel rows

        self.palette_idx = palette_idx
        self.time        = 0.0
        self.paused      = False
        self.running     = True
        self.auto_cycle  = False
        self.cycle_timer = 0.0

        self.spin        = spin
        self.spin_speed  = SPIN_DEFAULT         # deg/s
        self.light_auto  = True
        self.az          = 0.6                  # light azimuth (rad)
        self.el          = LIGHT_EL             # light elevation (rad)

        self.last_fps    = 60.0

        self.rng = random.Random(seed)
        self._build_octaves()
        self._build_sphere()
        self._build_stars()
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

    def _build_octaves(self) -> None:
        """Bump field: h(u,v) = Σ Aᵢ·sin(2π·fᵢ·u + pᵢ)·sin(2π·fᵢ·v + qᵢ).

        Multiplicative sines give the classic rounded-bumps look. The field is
        periodic in u (seamless texture spin) and its gradient is analytic,
        so the normal perturbation is exact and cheap."""
        f = (3, 5, 8, 13)
        a = (0.55, 0.28, 0.13, 0.06)
        self.octaves = [
            (fi, ai,
             self.rng.uniform(0.0, 2.0 * math.pi),
             self.rng.uniform(0.0, 2.0 * math.pi))
            for fi, ai in zip(f, a)
        ]
        # Per-octave amplitude baked into the v-side coefficients, with the
        # 2π·f factor from differentiating sin(2π·f·u).
        self.coeff = [(2.0 * math.pi * fi * ai) for fi, ai, _, _ in self.octaves]

    def _build_sphere(self) -> None:
        """Ray-trace the sphere per half-pixel and precompute everything that
        is static: base normals, sphere-map u/v, rim factor, and the per-pixel
        per-octave sin/cos terms of the bump field (spin shifts only the
        phase, which we fold into a per-frame rotation of these terms)."""
        R = 0.46 * min(self.w, self.sh)
        if R < 2.0:
            R = 2.0
        cx = (self.w - 1) / 2.0
        cy = (self.sh - 1) / 2.0
        two_pi = 2.0 * math.pi
        n = self.w * self.sh

        # Per-pixel: packed static terms.
        #  su[o], cu[o] : sin/cos(2π·fᵢ·u + pᵢ)
        #  sv[o], cv[o] : coeffᵢ · sin/cos(2π·fᵢ·v + qᵢ)
        self.px_nx: List[float] = []
        self.px_ny: List[float] = []
        self.px_nz: List[float] = []
        self.px_rim: List[float] = []
        self.px_su: List[List[float]] = []
        self.px_cu: List[List[float]] = []
        self.px_sv: List[List[float]] = []
        self.px_cv: List[List[float]] = []
        self.px_inside = bytearray(n)
        self.px_id: List[int] = []          # pixel index → packed index (-1 = outside)

        for py in range(self.sh):
            for px in range(self.w):
                dx = (px - cx) / R
                dy = (py - cy) / R
                r2 = dx * dx + dy * dy
                if r2 >= 1.0:
                    self.px_id.append(-1)
                    continue
                nz = math.sqrt(1.0 - r2)
                u = 0.5 + math.atan2(nz, dx) / two_pi   # wraps; periodic field → no seam
                v = 0.5 - math.asin(dy) / math.pi       # pole-pinched, fine

                idx = len(self.px_nx)
                self.px_id.append(idx)
                self.px_nx.append(dx)
                self.px_ny.append(dy)
                self.px_nz.append(nz)
                self.px_rim.append(RIM_MIN + (1.0 - RIM_MIN) * nz)
                su_l: List[float] = []
                cu_l: List[float] = []
                sv_l: List[float] = []
                cv_l: List[float] = []
                for (fi, ai, p, q), ci in zip(self.octaves, self.coeff):
                    a = two_pi * fi * u + p
                    b = two_pi * fi * v + q
                    su_l.append(math.sin(a))
                    cu_l.append(math.cos(a))
                    sv_l.append(ci * math.sin(b))
                    cv_l.append(ci * math.cos(b))
                self.px_su.append(su_l)
                self.px_cu.append(cu_l)
                self.px_sv.append(sv_l)
                self.px_cv.append(cv_l)

    def _build_stars(self) -> None:
        """A handful of faint background stars (cell-space), twinkling."""
        self.stars = []
        for _ in range(38):
            self.stars.append({
                "x": self.rng.randrange(self.w),
                "y": self.rng.randrange(self.h),
                "ph": self.rng.uniform(0.0, 2.0 * math.pi),
                "sp": self.rng.uniform(0.6, 2.2),
            })
        self.star_cells = {s["y"] * self.w + s["x"]: i for i, s in enumerate(self.stars)}

    def _build_lut(self) -> None:
        """Precompute per-brightness colour escape codes for the active palette."""
        self.palette_name = PALETTES[self.palette_idx][0]
        palette = PALETTES[self.palette_idx][1]
        self.FG: List[str] = []
        self.BG: List[str] = []
        for v in range(256):
            t = (v / 255.0) ** 1.25   # mild gamma: keep midtones rich, highlights white
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
            self.paused = not self.paused
        elif key == '+' or key == '=':
            self.spin_speed = min(360.0, self.spin_speed + SPIN_STEP)
        elif key == '-':
            self.spin_speed = max(0.0, self.spin_speed - SPIN_STEP)
        elif key in ('t', 'T'):
            self.spin = not self.spin
        elif key in ('l', 'L'):
            self.light_auto = not self.light_auto
        elif key == 'LEFT':
            self.az -= 0.25
        elif key == 'RIGHT':
            self.az += 0.25
        elif key == 'UP':
            self.el = min(1.45, self.el + 0.12)
        elif key == 'DOWN':
            self.el = max(-1.45, self.el - 0.12)
        elif key in ('r', 'R'):
            self.az = 0.6
            self.el = LIGHT_EL
            self.spin_speed = SPIN_DEFAULT
            self.spin = True
            self.light_auto = True
            self.auto_cycle = False
        elif key in ('p', 'P'):
            self.paused = not self.paused
        elif key in ('c', 'C'):
            self.auto_cycle = not self.auto_cycle
        elif key in '12345':
            self.palette_idx = int(key) - 1
            self.auto_cycle = False
            self._build_lut()

    # === Update ====================================================================================

    def _update(self, dt: float) -> None:
        """Advance time, light orbit and palette cycling."""
        if self.paused:
            return
        self.time += dt
        if self.light_auto:
            self.az += LIGHT_SPEED * dt
            self.el = LIGHT_EL + LIGHT_BOB * math.sin(self.time * LIGHT_BOB_F)
        if self.auto_cycle:
            self.cycle_timer += dt
            if self.cycle_timer >= 6.0:
                self.cycle_timer = 0.0
                self.palette_idx = (self.palette_idx + 1) % len(PALETTES)
                self._build_lut()

    # === Rendering =================================================================================

    def _shade_pixel(self, idx: int, L: Tuple[float, float, float],
                     H: Tuple[float, float, float], spin_off: float) -> int:
        """Shade one sphere half-pixel → palette index 0..255.

        The bump gradient is recomputed analytically from the per-pixel
        octave terms rotated by the spin phase:  sin(a+φ) = su·cosφ + cu·sinφ,
        cos(a+φ) = cu·cosφ − su·sinφ.  The perturbed normal is renormalised
        (its length varies with the spin phase), then lit by lambert + phong."""
        su_l = self.px_su[idx]
        cu_l = self.px_cu[idx]
        sv_l = self.px_sv[idx]
        cv_l = self.px_cv[idx]

        if spin_off == 0.0:
            # Static case: gradient is fixed, skip the trig rotation.
            gu = 0.0
            gv = 0.0
            for su, cu, sv, cv in zip(su_l, cu_l, sv_l, cv_l):
                gu += cu * sv
                gv += su * cv
        else:
            # Rotate u-phases by the spin offset φ = 2π·f·off.
            cos_p = [math.cos(2.0 * math.pi * fi * spin_off) for fi, _, _, _ in self.octaves]
            sin_p = [math.sin(2.0 * math.pi * fi * spin_off) for fi, _, _, _ in self.octaves]
            gu = 0.0
            gv = 0.0
            for su, cu, sv, cv, cp, sp in zip(su_l, cu_l, sv_l, cv_l, cos_p, sin_p):
                su_r = su * cp + cu * sp
                cu_r = cu * cp - su * sp
                gu += cu_r * sv
                gv += su_r * cv

        nx = self.px_nx[idx] + BUMP_K * gu
        ny = self.px_ny[idx] + BUMP_K * gv
        nz = self.px_nz[idx]
        inv = 1.0 / math.sqrt(nx * nx + ny * ny + nz * nz)
        nx *= inv
        ny *= inv
        nz *= inv

        Lx, Ly, Lz = L
        d = nx * Lx + ny * Ly + nz * Lz
        if d < 0.0:
            d = 0.0
        Hx, Hy, Hz = H
        s = nx * Hx + ny * Hy + nz * Hz
        if s < 0.0:
            s = 0.0
        p = s * s          # s^2
        p *= p             # s^4
        p *= p             # s^8
        p *= p             # s^16
        p *= p             # s^32  (tight specular)

        i = (AMBIENT + DIFFUSE * d + SPECULAR * p) * self.px_rim[idx]
        if i <= 0.0:
            return 0
        if i >= 1.0:
            return 255
        return int(i * 255.0)

    def _render(self) -> str:
        """Build the full frame (sphere + stars + status bar)."""
        w, h, sh = self.w, self.h, self.sh
        px_id = self.px_id
        FG, BG = self.FG, self.BG
        bg_code = BG[0] + FG[0]          # solid dark background cell

        # Light: auto-orbit handled in _update; H = half-vector viewer (0,0,1).
        ce = math.cos(self.el)
        L = (math.cos(self.az) * ce, math.sin(self.el), math.sin(self.az) * ce)
        lx, ly, lz = L
        hl = 1.0 / math.sqrt((lx * lx + ly * ly + (lz + 1.0) ** 2))
        H = (lx * hl, ly * hl, (lz + 1.0) * hl)

        spin_off = (self.time * self.spin_speed / 360.0) % 1.0 if self.spin else 0.0

        # Star brightnesses for this frame (twinkle: sharp peaks).
        star_colors: List[str] = []
        for s in self.stars:
            tw = math.sin(self.time * s["sp"] + s["ph"]) ** 4
            v = int(90 + 165 * tw)
            star_colors.append(rgb_fg(v, v, min(255, v + 18)))

        rows: List[str] = []
        for sy in range(h):
            cells: List[str] = []
            base_top = sy * 2 * w
            base_bot = base_top + w
            for sx in range(w):
                cell = sy * w + sx
                if cell in self.star_cells:
                    # Background cell with a star → bright fg over dark bg.
                    cells.append(bg_code)
                    cells.append(star_colors[self.star_cells[cell]])
                    cells.append('▀')
                    continue
                t_top = px_id[base_top + sx]
                t_bot = px_id[base_bot + sx]
                if t_top < 0 and t_bot < 0:
                    cells.append(bg_code)
                    cells.append(bg_code)
                    cells.append('▀')
                elif t_top < 0:
                    cells.append(bg_code)
                    cells.append(FG[self._shade_pixel(t_bot, L, H, spin_off)])
                    cells.append('▀')
                elif t_bot < 0:
                    cells.append(BG[self._shade_pixel(t_top, L, H, spin_off)])
                    cells.append(bg_code)
                    cells.append('▀')
                else:
                    cells.append(BG[self._shade_pixel(t_top, L, H, spin_off)])
                    cells.append(FG[self._shade_pixel(t_bot, L, H, spin_off)])
                    cells.append('▀')
            rows.append(''.join(cells))

        parts = [RESET, CLEAR, HOME]
        parts.extend(rows)
        parts.append(RESET)
        parts.append(
            f"\r\n{BOLD}🔮 {self.palette_name} | {self.last_fps:5.0f} fps | "
            f"spin {'ON ' if self.spin else 'OFF'} {self.spin_speed:3.0f}°/s | "
            f"light {'auto' if self.light_auto else 'man '} | 🗺 {self.seed}{RESET}  "
            f"1-5 pal · c cycle · t spin · +/- speed · l light · "
            f"arrows steer · space pause · r reset · q quit"
        )
        return ''.join(parts)

    def render_ascii(self) -> str:
        """Static ASCII dump of the current frame (for --once / tests)."""
        w, h, sh = self.w, self.h, self.sh
        px_id = self.px_id
        n = len(RAMP) - 1

        ce = math.cos(self.el)
        L = (math.cos(self.az) * ce, math.sin(self.el), math.sin(self.az) * ce)
        lx, ly, lz = L
        hl = 1.0 / math.sqrt((lx * lx + ly * ly + (lz + 1.0) ** 2))
        H = (lx * hl, ly * hl, (lz + 1.0) * hl)
        spin_off = (self.time * self.spin_speed / 360.0) % 1.0 if self.spin else 0.0

        lines = []
        for py in range(sh):
            row = []
            base = py * w
            for px in range(w):
                idx = px_id[base + px]
                if idx < 0:
                    row.append(' ')
                    continue
                i = self._shade_pixel(idx, L, H, spin_off) / 255.0
                row.append(RAMP[int(i * n)])
            lines.append("".join(row))
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
                    self.sh = h * 2
                    self._build_sphere()
                    self._build_stars()
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
        description="Terminal Bump-Mapped Sphere 🔮 — classic demoscene Bumpy effect")
    parser.add_argument("--seed", type=int, default=1337, help="world seed (0..2^32)")
    parser.add_argument("--palette", type=int, default=1, choices=range(1, len(PALETTES) + 1),
                        help="palette preset (1-5)")
    parser.add_argument("--spin", dest="spin", action="store_true", default=True,
                        help="texture spin on (default)")
    parser.add_argument("--no-spin", dest="spin", action="store_false",
                        help="static bump texture")
    parser.add_argument("--width", type=int, default=100, help="width for --once mode")
    parser.add_argument("--height", type=int, default=30, help="height for --once mode")
    parser.add_argument("--once", nargs="?", const=40, type=int, metavar="FRAMES",
                        help="run FRAMES frames, dump ASCII frame, exit (for demos/tests)")
    args = parser.parse_args()

    bumpy = Bumpy(seed=args.seed, palette_idx=args.palette - 1, spin=args.spin,
                  size=(args.width, args.height) if args.once is not None else None)

    if args.once is not None:
        # Non-interactive: let the light orbit, then dump a static ASCII
        # frame. The full update+render loop is timed so headless/CI runs
        # catch performance regressions; stats go to stderr, stdout stays
        # pure ASCII.
        t0 = time.monotonic()
        out = ""
        for _ in range(args.once):
            bumpy._update(1.0 / 30.0)
            out = bumpy.render_ascii()   # full render, like the interactive loop
        dt = max(time.monotonic() - t0, 1e-9)
        print(out)
        print(f"[bench] {args.once} frames in {dt:.2f}s "
              f"\u2192 {args.once / dt:.0f} fps ({bumpy.w}x{bumpy.sh} half-pixels, "
              f"seed {args.seed}, palette {args.palette}, spin {args.spin})",
              file=sys.stderr)
        return

    try:
        bumpy.run()
    except KeyboardInterrupt:
        sys.stdout.write(SHOW + RESET + "\n")


if __name__ == "__main__":
    main()

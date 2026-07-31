#!/usr/bin/env python3
"""
tunnel.py — Terminal Tunnel 🌀
================================
Classic demoscene texture-mapped tunnel rendered to an ANSI truecolor
terminal. A procedural texture is wrapped around the tunnel walls with
polar coordinates (angle → u, 1/distance → v); the camera flies forward
through the tube while you steer with the arrow keys.

Rendered with the half-block trick (each cell draws ▀ with fg = top
sample, bg = bottom sample) for 2× vertical resolution, with distance
fog fading the far end of the tunnel.

Usage:
    python tunnel.py

Controls:
    q/ESC      — quit
    arrows     — steer the camera (look around)
    +/-        — speed up / slow down
    1-5        — palette presets
    t          — cycle texture (checker / rings / stripes / noise / stars)
    f          — toggle warp wobble
    c          — cycle palette continuously
    SPACE      — pause/resume
    r          — reset camera, speed and modes

Palettes:
    1 — Lava (red/orange/yellow)
    2 — Ocean (blue/cyan/teal)
    3 — Neon (magenta/pink/blue)
    4 — Forest (green/yellow/brown)
    5 — Ice (cyan/white/purple)

Zero external dependencies. Pure stdlib.
ANSI truecolor required (modern terminals only).

Author: Mcking (AI assistant do Luis Monteiro)
Data: 2026-07-31
"""

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
# dark at the fogged far end → bright on the near walls.

Palette = List[Tuple[int, int, int]]

PALETTES: List[Tuple[str, Palette]] = [
    ("Lava", [
        (8, 0, 0),        # near-black
        (90, 10, 0),      # dark red
        (255, 40, 0),     # red
        (255, 130, 0),    # orange
        (255, 210, 60),   # yellow
        (255, 250, 200),  # white-hot
    ]),
    ("Ocean", [
        (0, 4, 20),       # deep blue-black
        (0, 40, 100),     # dark blue
        (0, 90, 190),     # blue
        (0, 170, 230),    # cyan-blue
        (60, 220, 210),   # teal
        (220, 250, 255),  # foam white
    ]),
    ("Neon", [
        (12, 0, 22),      # dark purple
        (90, 0, 130),     # purple
        (210, 0, 160),    # magenta
        (255, 60, 210),   # pink
        (120, 210, 255),  # cyan
        (240, 240, 255),  # cold white
    ]),
    ("Forest", [
        (4, 10, 0),       # dark green-black
        (15, 55, 10),     # deep green
        (35, 110, 25),    # forest green
        (90, 170, 45),    # green
        (190, 210, 70),   # yellow-green
        (240, 250, 200),  # pale
    ]),
    ("Ice", [
        (4, 8, 22),       # midnight
        (20, 40, 80),     # dark blue
        (60, 120, 190),   # steel blue
        (140, 200, 240),  # ice blue
        (220, 245, 255),  # pale cyan
        (255, 255, 255),  # white
    ]),
]

# ── Texture constants ──────────────────────────────────────────────────────────────────────────────
TW       = 256    # texture width  (power of two → & mask)
TH       = 256    # texture height (power of two → & mask)
TEX_MASK = TW - 1
K        = 4.0    # tunnel perspective: v = TH * K / dist
FOG      = 9.0    # distance-fog falloff in screen units (smaller = foggier)
WOB_AMOUNT = 0.10 # warp wobble amplitude (radians)
WOB_SCALE  = 0.35 # warp wobble spatial frequency
WOB_SPEED  = 2.2  # warp wobble temporal frequency


def _make_checker() -> List[float]:
    """Soft sine checkerboard — the classic tunnel texture."""
    tex = [0.0] * (TW * TH)
    for v in range(TH):
        vv = v / TH * math.tau
        for u in range(TW):
            uu = u / TW * math.tau
            tex[v * TW + u] = 0.5 + 0.5 * math.sin(uu * 2) * math.sin(vv * 2)
    return tex


def _make_rings() -> List[float]:
    """Horizontal bands in the texture → concentric rings around the tunnel."""
    tex = [0.0] * (TW * TH)
    for v in range(TH):
        vv = v / TH * math.tau
        s = 0.5 + 0.5 * math.sin(vv * 5)
        tex[v * TW:(v + 1) * TW] = [s] * TW
    return tex


def _make_stripes() -> List[float]:
    """Diagonal stripes wrapping around the tube."""
    tex = [0.0] * (TW * TH)
    for v in range(TH):
        vv = v / TH
        for u in range(TW):
            tex[v * TW + u] = 0.5 + 0.5 * math.sin((u / TW + vv) * math.tau * 7)
    return tex


def _make_noise() -> List[float]:
    """Smooth value noise (32×32 lattice, smoothstep bilinear)."""
    N = 32
    rng = random.Random(1337)
    grid = [[rng.random() for _ in range(N + 1)] for _ in range(N + 1)]

    def smooth(x: float) -> float:
        return x * x * (3.0 - 2.0 * x)

    tex = [0.0] * (TW * TH)
    for v in range(TH):
        vv = v / TH * N
        v0 = int(vv)
        vf = vv - v0
        sv = smooth(vf)
        for u in range(TW):
            uu = u / TW * N
            u0 = int(uu)
            uf = uu - u0
            su = smooth(uf)
            a = grid[v0][u0] + (grid[v0][u0 + 1] - grid[v0][u0]) * su
            b = grid[v0 + 1][u0] + (grid[v0 + 1][u0 + 1] - grid[v0 + 1][u0]) * su
            tex[v * TW + u] = a + (b - a) * sv
    return tex


def _make_stars() -> List[float]:
    """Sparse starfield — flying through it looks like a hyperspace vortex."""
    rng = random.Random(2026)
    tex = [0.0] * (TW * TH)
    # faint dust
    for i in range(TW * TH):
        if rng.random() < 0.012:
            tex[i] = rng.uniform(0.25, 0.6)
    # bright stars with a soft glow
    for _ in range(60):
        u = rng.randrange(TW)
        v = rng.randrange(TH)
        r = rng.choice([1, 1, 1, 2])
        br = rng.uniform(0.8, 1.0)
        for dv in range(-r, r + 1):
            for du in range(-r, r + 1):
                dd = du * du + dv * dv
                if dd <= r * r:
                    idx = ((v + dv) & TEX_MASK) * TW + ((u + du) & TEX_MASK)
                    tex[idx] = max(tex[idx], br * (1.0 - dd / (r * r + 1)))
    return tex


TEXTURES: List[Tuple[str, List[float]]] = [
    ("Checker", _make_checker()),
    ("Rings",   _make_rings()),
    ("Stripes", _make_stripes()),
    ("Noise",   _make_noise()),
    ("Stars",   _make_stars()),
]


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


# ── Tunnel ─────────────────────────────────────────────────────────────────────────────────────────

class Tunnel:
    """Interactive terminal texture-mapped tunnel."""

    def __init__(self) -> None:
        self.w, self.h = self._get_size()
        self.sh         : int    = self.h * 2   # sample rows (2 per cell)
        self.palette_idx: int    = 0
        self.tex_idx    : int    = 0
        self.time       : float  = 0.0
        self.zoff       : float  = 0.0          # flight progress along the tube
        self.speed      : float  = 140.0        # tunnel units per second
        self.ox, self.oy= 0.0, 0.0              # camera offset (steering)
        self.tx, self.ty= 0.0, 0.0              # steering targets
        self.paused     : bool   = False
        self.auto_cycle : bool   = False
        self.wobble     : bool   = False
        self.running    : bool   = True
        self.last_fps   : float  = 60.0
        self.cycle_timer: float  = 0.0
        self.texels     : List[float] = TEXTURES[0][1]
        self.px: List[float] = []
        self.py: List[float] = []
        self._precompute()

    # === Setup =====================================================================================

    @staticmethod
    def _get_size() -> Tuple[int, int]:
        """Get terminal size, fallback 80x24."""
        try:
            import shutil
            w, h = shutil.get_terminal_size((80, 24))
            # Leave one row for the status bar
            return w, max(h - 1, 10)
        except Exception:
            return 80, 24

    def _precompute(self) -> None:
        """Per-sample offsets from the screen centre (sample space is square)."""
        w, sh = self.w, self.sh
        cx, cy = w / 2.0, sh / 2.0
        self.px = [xi - cx for yi in range(sh) for xi in range(w)]
        self.py = [yi - cy for yi in range(sh) for xi in range(w)]

    def _reset(self) -> None:
        """Reset camera, speed and modes."""
        self.ox = self.oy = 0.0
        self.tx = self.ty = 0.0
        self.speed = 140.0
        self.zoff = 0.0
        self.wobble = False
        self.auto_cycle = False
        self.paused = False
        self.palette_idx = 0
        self.tex_idx = 0
        self.texels = TEXTURES[0][1]

    # === Input =====================================================================================

    def _read_key(self) -> Optional[str]:
        """Read one keypress without blocking. Returns None if no key.

        Arrow keys are decoded to 'UP'/'DOWN'/'LEFT'/'RIGHT'; a bare ESC
        quits. Any other escape sequence is ignored."""
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
                                rest = ''
                                while len(rest) < 3 and select.select([fd], [], [], 0.01)[0]:
                                    rest += sys.stdin.read(1)
                                if len(rest) >= 2 and rest[0] in '[O' and rest[1] in 'ABCD':
                                    return {'A': 'UP', 'B': 'DOWN', 'C': 'RIGHT', 'D': 'LEFT'}[rest[1]]
                                if rest == '':
                                    return 'q'  # bare ESC = quit
                                return None    # other escape sequence, ignore
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
        elif key == 'UP':
            self.ty -= 4.0
        elif key == 'DOWN':
            self.ty += 4.0
        elif key == 'LEFT':
            self.tx -= 4.0
        elif key == 'RIGHT':
            self.tx += 4.0
        elif key == '+' or key == '=':
            self.speed = min(3000.0, self.speed * 1.3)
        elif key == '-' or key == '_':
            self.speed = max(5.0, self.speed / 1.3)
        elif key == 'r' or key == 'R':
            self._reset()
        elif key == 'c' or key == 'C':
            self.auto_cycle = not self.auto_cycle
        elif key == 't' or key == 'T':
            self.tex_idx = (self.tex_idx + 1) % len(TEXTURES)
            self.texels = TEXTURES[self.tex_idx][1]
        elif key == 'f' or key == 'F':
            self.wobble = not self.wobble
        elif key in '12345':
            self.palette_idx = int(key) - 1
            self.auto_cycle = False

    # === Rendering =================================================================================

    def _step(self, dt: float) -> None:
        """Advance flight by *dt* seconds."""
        self.time += dt
        if not self.paused:
            # smooth steering easing
            k = min(1.0, dt * 6.0)
            self.ox += (self.tx - self.ox) * k
            self.oy += (self.ty - self.oy) * k
            self.zoff += self.speed * dt

    def _render(self) -> str:
        """Build the full ANSI frame string."""
        w, h, sh = self.w, self.h, self.sh
        tex = self.texels
        palette = PALETTES[self.palette_idx][1]
        px, py = self.px, self.py
        ox, oy = self.ox, self.oy
        zoff = self.zoff
        wob = self.wobble
        t = self.time
        ang_scale = TW / math.tau

        parts: List[str] = [HOME]
        for yi in range(h):
            base_t = (yi * 2) * w
            base_b = base_t + w
            for xi in range(w):
                # ── top sample ──
                idx = base_t + xi
                rx = px[idx] - ox
                ry = py[idx] - oy
                d = math.sqrt(rx * rx + ry * ry) + 1e-4
                ang = math.atan2(ry, rx)
                if wob:
                    ang += WOB_AMOUNT * math.sin(d * WOB_SCALE + t * WOB_SPEED)
                tu = int(ang * ang_scale) & TEX_MASK
                tv = int(TH * K / d + zoff) & TEX_MASK
                bright_t = tex[tv * TW + tu] * (1.0 - math.exp(-d / FOG))

                # ── bottom sample ──
                idx = base_b + xi
                rx = px[idx] - ox
                ry = py[idx] - oy
                d = math.sqrt(rx * rx + ry * ry) + 1e-4
                ang = math.atan2(ry, rx)
                if wob:
                    ang += WOB_AMOUNT * math.sin(d * WOB_SCALE + t * WOB_SPEED)
                tu = int(ang * ang_scale) & TEX_MASK
                tv = int(TH * K / d + zoff) & TEX_MASK
                bright_b = tex[tv * TW + tu] * (1.0 - math.exp(-d / FOG))

                cr, cg, cb = sample_palette(palette, bright_t)
                dr, dg, db = sample_palette(palette, bright_b)
                parts.append(rgb_fg(cr, cg, cb) + rgb_bg(dr, dg, db) + "▀")
            parts.append(RESET)
            parts.append("\n")

        # ── status bar ──
        pal_name = PALETTES[self.palette_idx][0]
        tex_name = TEXTURES[self.tex_idx][0]
        wob_state = "on" if self.wobble else "off"
        parts.append(RESET + BOLD)
        parts.append(
            f"🌀 TUNNEL  {pal_name}  {tex_name}  speed {self.speed:5.0f}  "
            f"steer {self.ox:+5.0f},{self.oy:+5.0f}  wobble:{wob_state}  "
            f"{self.last_fps:4.0f} fps"
        )
        parts.append(RESET)
        parts.append(
            "  [1-5]pal [t]tex [f]wobble [c]cycle [+/-]speed [arrows]steer "
            "[space]pause [r]reset [q]quit"
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
                self.sh = self.h * 2
                self._precompute()

            key = self._read_key()
            if key is not None:
                self.handle_key(key)

            self._step(dt)

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
    try:
        Tunnel().run()
    except KeyboardInterrupt:
        sys.stdout.write(SHOW + RESET + "\n")


if __name__ == "__main__":
    main()

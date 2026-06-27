#!/usr/bin/env python3
"""
Mandelbrot Explorer — Terminal Interactive Fractal Viewer
==========================================================
Pan, zoom, and explore the Mandelbrot set in ANSI truecolor.

Controls:
  Arrow keys / WASD  — pan
  + / -              — zoom in/out
  [ / ]              — increase/decrease max iterations
  c                  — cycle color palette
  r                  — reset to default view
  q / ESC            — quit
  h                  — toggle HUD

Zero external dependencies. Pure Python + ANSI escape codes.
"""

import io
import logging
import math
import sys
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ====================================================================================================
# ANSI Helpers
# ====================================================================================================

# Windows UTF-8 fix
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
elif hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

HIDE    : str = "\033[?25l"
SHOW    : str = "\033[?25h"
HOME    : str = "\033[H"
RESET   : str = "\033[0m"
BOLD    : str = "\033[1m"
SAVE    : str = "\033[s"
RESTORE : str = "\033[u"
CLEAR   : str = "\033[2J"


def fg(r: int, g: int, b: int) -> str:
    """Return ANSI truecolor foreground escape code."""
    return f"\033[38;2;{r};{g};{b}m"


def bg(r: int, g: int, b: int) -> str:
    """Return ANSI truecolor background escape code."""
    return f"\033[48;2;{r};{g};{b}m"


# ====================================================================================================
# Config
# ====================================================================================================

FPS     : int = 30
FRAME_S : float = 1.0 / FPS


@dataclass
class View:
    """Mandelbrot viewport parameters."""
    cx : float = -0.5         # center x (real)
    cy : float = 0.0           # center y (imaginary)
    zoom : float = 1.0         # zoom level (1 = full view)
    max_iter : int = 100
    palette_idx : int = 0

    @property
    def width(self) -> float:
        return 3.5 / self.zoom

    @property
    def height(self) -> float:
        return 2.5 / self.zoom


# ====================================================================================================
# Color Palettes
# ====================================================================================================

PaletteFunc = Callable[[float], Tuple[int, int, int]]


def palette_fire(t: float) -> Tuple[int, int, int]:
    """Fire/heat palette."""
    r = min(255, int(t * 255))
    g = min(255, max(0, int((t - 0.33) * 3 * 255)))
    b = min(255, max(0, int((t - 0.66) * 3 * 255)))
    return (r, g, b)


def palette_ocean(t: float) -> Tuple[int, int, int]:
    """Deep blue to cyan."""
    r = int(t * 30)
    g = int(t * 120)
    b = int(t * 255)
    return (r, g, b)


def palette_neon(t: float) -> Tuple[int, int, int]:
    """Neon purple to pink to cyan."""
    r = int((math.sin(t * 2 * math.pi) * 0.5 + 0.5) * 255)
    g = int((math.sin(t * 2 * math.pi + 2.09) * 0.5 + 0.5) * 255)
    b = int((math.sin(t * 2 * math.pi + 4.19) * 0.5 + 0.5) * 255)
    return (r, g, b)


def palette_spectrum(t: float) -> Tuple[int, int, int]:
    """Full rainbow HSV-like."""
    return palette_neon(t)  # same math, different semantic


def palette_ice(t: float) -> Tuple[int, int, int]:
    """Cold ice blue."""
    r = int(max(0, t * 50 - 20))
    g = int(max(0, t * 150 - 30))
    b = int(min(255, t * 220 + 35))
    return (r, g, b)


def palette_forest(t: float) -> Tuple[int, int, int]:
    """Earth/forest tones."""
    r = int(t * 80 + 40)
    g = int(t * 160 + 20)
    b = int(t * 40 + 10)
    return (r, g, b)


def palette_galaxy(t: float) -> Tuple[int, int, int]:
    """Deep space purple-blue."""
    r = int(t * 100)
    g = int(t * 50 + 10)
    b = int(t * 200 + 55)
    return (r, g, b)


def palette_lava(t: float) -> Tuple[int, int, int]:
    """Lava glow: black → red → orange → yellow → white."""
    if t < 0.25:
        s = t / 0.25
        return (int(s * 80), 0, 0)
    elif t < 0.5:
        s = (t - 0.25) / 0.25
        return (80 + int(s * 175), int(s * 40), 0)
    elif t < 0.75:
        s = (t - 0.5) / 0.25
        return (255, 40 + int(s * 215), int(s * 20))
    else:
        s = (t - 0.75) / 0.25
        return (255, 255, 20 + int(s * 235))


PALETTES: List[Tuple[str, PaletteFunc]] = [
    ("🔥 Fire",       palette_fire),
    ("🌊 Ocean",      palette_ocean),
    ("💜 Neon",       palette_neon),
    ("🌈 Spectrum",   palette_spectrum),
    ("❄️ Ice",        palette_ice),
    ("🌲 Forest",     palette_forest),
    ("🌌 Galaxy",     palette_galaxy),
    ("🌋 Lava",       palette_lava),
]


# ====================================================================================================
# Mandelbrot Computation
# ====================================================================================================


def mandelbrot(px: int, py: int, w: int, h: int, view: View) -> Tuple[int, float]:
    """
    Compute Mandelbrot at terminal pixel (*px*, *py*).

    Args:
        px : Pixel x-coordinate.
        py : Pixel y-coordinate.
        w : Screen width in pixels.
        h : Screen height in pixels.
        view : Current viewport parameters.

    Returns:
        Tuple of (iterations, smooth_value).  ``iterations == view.max_iter``
        means the point is inside the set.
    """
    x0 = view.cx - view.width / 2 + (px / w) * view.width
    y0 = view.cy - view.height / 2 + (py / h) * view.height

    x, y = 0.0, 0.0
    x2, y2 = 0.0, 0.0
    iteration = 0
    max_iter = view.max_iter

    while iteration < max_iter and x2 + y2 <= 4.0:
        y = 2 * x * y + y0
        x = x2 - y2 + x0
        x2 = x * x
        y2 = y * y
        iteration += 1

    if iteration == max_iter:
        return (max_iter, 0.0)

    # Smooth iteration count (normalized)
    log_zn = math.log2(x2 + y2) / 2.0
    nu = math.log2(log_zn) if log_zn > 0 else 0.0
    smooth = iteration + 1 - nu
    t = smooth / max_iter

    return (iteration, t)


# ====================================================================================================
# Terminal Helpers
# ====================================================================================================


def get_terminal_size() -> Tuple[int, int]:
    """Return terminal (columns, lines), falling back to 80x24."""
    try:
        import shutil
        w, h = shutil.get_terminal_size((80, 24))
        return w, h
    except Exception:
        return 80, 24


# ====================================================================================================
# Rendering
# ====================================================================================================


def render_frame(w: int, h: int, view: View) -> str:
    """Render entire Mandelbrot frame to ANSI string."""
    _, pal_func = PALETTES[view.palette_idx % len(PALETTES)]
    plot_chars = " .:-=+*#%@"
    lines: List[str] = []

    screen: List[List[str]] = [["" for _ in range(w)] for _ in range(h)]

    for py in range(h):
        for px in range(w):
            iters, t = mandelbrot(px, py, w, h, view)
            if iters == view.max_iter:
                screen[py][px] = bg(0, 0, 0) + fg(10, 10, 15) + "." + RESET
            else:
                r, g, b = pal_func(t)
                ci = int(t * (len(plot_chars) - 1))
                ci = max(0, min(ci, len(plot_chars) - 1))
                ch = plot_chars[ci]
                screen[py][px] = (
                    fg(min(255, r + 40), min(255, g + 40), min(255, b + 40)) + ch + RESET
                )

    for y in range(h):
        lines.append("".join(screen[y]))

    return HOME + "\n".join(lines)


def render_overlay(
    w: int,
    h: int,
    view: View,
    palette_name: str,
    now: float,
) -> str:
    """HUD overlay lines."""
    lines: List[str] = [
        f"  🌀 Mandelbrot Explorer",
        f"  Zoom: {view.zoom:.1f}x  |  Iter: {view.max_iter}  |  "
        f"Pos: ({view.cx:.6f}, {view.cy:.6f})",
        f"  Palette: {palette_name}  |  FPS: {FPS}",
        f"  [WASD/Arrows] Pan  [+/-] Zoom  [[]] Iter  [C] Pal  "
        f"[R] Reset  [H] Hide  [Q] Quit",
    ]
    return "\n".join(lines)


# ====================================================================================================
# Keyboard Input (Non-Blocking, Cross-Platform)
# ====================================================================================================


def get_key() -> Optional[str]:
    """Read a single keypress without blocking.  Returns ``None`` if no key."""
    import select
    if sys.platform == "win32":
        return _get_key_windows()
    else:
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
    return None


def _get_key_windows() -> Optional[str]:
    """Windows msvcrt-based non-blocking key read."""
    import msvcrt
    if msvcrt.kbhit():
        ch = msvcrt.getwch()
        if ch == '\xe0':  # Arrow keys prefix
            ch2 = msvcrt.getwch()
            mapping = {
                'H': 'KEY_UP',
                'P': 'KEY_DOWN',
                'M': 'KEY_RIGHT',
                'K': 'KEY_LEFT',
            }
            return mapping.get(ch2, ch2)
        return ch
    return None


# ====================================================================================================
# Key Processing
# ====================================================================================================


def process_key(key: Optional[str], view: View) -> bool:
    """Process a keypress and update *view*.  Returns ``False`` if should quit."""
    if key is None:
        return True

    pan_speed = view.width * 0.1

    if key in ('q', 'Q', '\x1b'):
        return False
    elif key in ('KEY_LEFT', 'a', 'A'):
        view.cx -= pan_speed
    elif key in ('KEY_RIGHT', 'd', 'D'):
        view.cx += pan_speed
    elif key in ('KEY_UP', 'w', 'W'):
        view.cy -= pan_speed
    elif key in ('KEY_DOWN', 's', 'S'):
        view.cy += pan_speed
    elif key in ('+', '='):
        view.zoom *= 1.5
    elif key in ('-', '_'):
        view.zoom /= 1.5
        if view.zoom < 1e-12:
            view.zoom = 1e-12
    elif key == '[':
        view.max_iter = max(20, view.max_iter - 25)
    elif key == ']':
        view.max_iter = min(10000, view.max_iter + 50)
    elif key in ('c', 'C'):
        view.palette_idx = (view.palette_idx + 1) % len(PALETTES)
    elif key in ('r', 'R'):
        view.cx = -0.5
        view.cy = 0.0
        view.zoom = 1.0
        view.max_iter = 100
        view.palette_idx = 0

    return True


# ====================================================================================================
# Main
# ====================================================================================================


def main() -> None:
    """Run the interactive Mandelbrot explorer."""
    view = View()
    show_hud = True
    running = True

    sys.stdout.write(CLEAR + HOME + HIDE)
    sys.stdout.flush()

    w, h = get_terminal_size()
    last_time = time.perf_counter()

    try:
        while running:
            now = time.perf_counter()
            last_time = now

            # Handle resize
            new_w, new_h = get_terminal_size()
            if new_w != w or new_h != h:
                w, h = new_w, new_h

            # Process queued keys
            key = get_key()
            while key is not None:
                if key == 'h' or key == 'H':
                    show_hud = not show_hud
                else:
                    running = process_key(key, view)
                    if not running:
                        break
                key = get_key()
                if key is None:
                    break

            if w < 60 or h < 20:
                sys.stdout.write(CLEAR + HOME)
                sys.stdout.write(fg(255, 100, 100) + "Terminal too small! "
                                "Need at least 60x20" + RESET)
                sys.stdout.flush()
                time.sleep(0.5)
                continue

            # Render
            frame = render_frame(w, h - (3 if show_hud else 0), view)

            if show_hud:
                palette_name = PALETTES[view.palette_idx % len(PALETTES)][0]
                hud = render_overlay(w, h, view, palette_name, now)
                frame += "\n" + RESET + fg(150, 180, 200) + hud + RESET

            sys.stdout.write(frame)
            sys.stdout.flush()

            sleep_time = FRAME_S - (time.perf_counter() - now)
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(SHOW + CLEAR + HOME + RESET)
        sys.stdout.flush()
        print(f"{fg(100, 200, 255)}🌀 Mandelbrot Explorer — até à próxima!{RESET}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()

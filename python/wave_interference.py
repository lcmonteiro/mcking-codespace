#!/usr/bin/env python3
"""
Wave Interference — Terminal Wave Superposition Simulator 🌊
=============================================================
Visualises the interference patterns created by multiple wave sources
in a 2D medium. Each source emits circular waves; the superposition
of all waves at every point creates beautiful constructive and
destructive interference patterns.

Physics:
    Each source i at position (sx, sy) emits:
        ψᵢ(r, t) = Aᵢ · sin(kᵢ · r − ωᵢ · t + φᵢ) · e^(−αᵢ · r)
    where r is distance from source, k is wavenumber, ω is angular
    frequency, φ is phase, α is attenuation.

    Total wavefield:  ψ_total = Σ ψᵢ

Features:
    • Multiple interactive wave sources
    • Real-time interference pattern rendering
    • Several preset configurations (double slit, standing waves, etc.)
    • Truecolor ANSI rendering with smooth gradients
    • Fully interactive controls

Controls:
    [1-9]     Toggle wave source on/off
    [a/A]     Cycle all sources' amplitude
    [f/F]     Cycle all sources' frequency
    [p]       Cycle colour palettes
    [r]       Reset to current preset
    [n]       Next preset
    [h]       Toggle HUD
    [Space]   Pause/Resume
    [+/-]     Speed up/down
    [q/ESC]   Quit

Pure Python, zero dependencies. ANSI truecolor.
"""

import io
import math
import os
import random
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

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
DIM   = "\033[2m"


def term_size():
    try:
        return os.get_terminal_size()
    except OSError:
        return os.terminal_size((80, 24))


# ── ANSI Helpers ────────────────────────────────────────────
def fg(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"

def bg(r: int, g: int, b: int) -> str:
    return f"\033[48;2;{r};{g};{b}m"


# ── Data Structures ─────────────────────────────────────────
@dataclass
class WaveSource:
    """A single wave source with position and wave parameters."""
    x: float          # normalised 0-1
    y: float          # normalised 0-1
    amplitude: float  # wave amplitude
    frequency: float  # spatial frequency (wavenumber)
    angular_freq: float  # temporal frequency
    phase: float      # initial phase offset
    attenuation: float   # decay over distance
    active: bool = True


# ── Palettes ────────────────────────────────────────────────
PALETTES = {
    "Ocean": lambda v: (
        int(max(0, min(255, 10 + 30 * v))),
        int(max(0, min(255, 20 + 80 * v + 120 * v * v))),
        int(max(0, min(255, 40 + 160 * v + 60 * v * v))),
    ),
    "Heat": lambda v: (
        int(max(0, min(255, 20 + 235 * v * v))),
        int(max(0, min(255, 10 + 120 * v - 80 * v * v))),
        int(max(0, min(255, 5 + 40 * v * (1 - v)))),
    ),
    "Plasma": lambda v: (
        int(max(0, min(255, 60 + 195 * (0.5 + 0.5 * math.sin(6.28 * v + 0.0))))),
        int(max(0, min(255, 30 + 180 * max(0, math.sin(6.28 * v + 2.1) * 0.9)))),
        int(max(0, min(255, 20 + 220 * max(0, math.cos(6.28 * v + 4.2) * 0.8)))),
    ),
    "Viridis": lambda v: (
        int(max(0, min(255, 20 + 80 * v + 155 * v * v))),
        int(max(0, min(255, 20 + 160 * v - 60 * v * v))),
        int(max(0, min(255, 80 + 100 * v - 120 * v * v))),
    ),
    "Aurora": lambda v: (
        int(max(0, min(255, 20 + 60 * v))),
        int(max(0, min(255, 40 + 180 * v + 40 * math.sin(3.14 * v)))),
        int(max(0, min(255, 30 + 100 * v + 125 * v * v))),
    ),
    "Magma": lambda v: (
        int(max(0, min(255, 15 + 240 * v * v))),
        int(max(0, min(255, 8 + 60 * v * v + 80 * v * v * v))),
        int(max(0, min(255, 10 + 180 * v - 100 * v * v))),
    ),
    "Ice": lambda v: (
        int(max(0, min(255, 10 + 140 * v * v))),
        int(max(0, min(255, 20 + 160 * v))),
        int(max(0, min(255, 50 + 200 * v + 55 * v * v))),
    ),
    "Mono": lambda v: (
        int(max(0, min(255, 10 + 245 * v))),
        int(max(0, min(255, 10 + 245 * v))),
        int(max(0, min(255, 10 + 245 * v))),
    ),
}


# ── Presets ─────────────────────────────────────────────────
PRESETS = {
    "Double Slit": [
        WaveSource(0.35, 0.5, 1.0, 12.0, 3.0, 0.0, 0.002),
        WaveSource(0.65, 0.5, 1.0, 12.0, 3.0, 0.0, 0.002),
    ],
    "Quad": [
        WaveSource(0.25, 0.25, 0.8, 15.0, 2.5, 0.0, 0.001),
        WaveSource(0.75, 0.25, 0.8, 15.0, 2.5, 1.57, 0.001),
        WaveSource(0.25, 0.75, 0.8, 15.0, 2.5, 3.14, 0.001),
        WaveSource(0.75, 0.75, 0.8, 15.0, 2.5, 4.71, 0.001),
    ],
    "Standing Wave": [
        WaveSource(0.1, 0.5, 1.0, 10.0, 4.0, 0.0, 0.001),
        WaveSource(0.9, 0.5, 1.0, 10.0, 4.0, 3.14, 0.001),
    ],
    "Raindrop": [
        WaveSource(0.5, 0.3, 1.2, 8.0, 5.0, 0.0, 0.003),
        WaveSource(0.3, 0.6, 0.9, 12.0, 3.5, 1.0, 0.003),
        WaveSource(0.7, 0.7, 0.7, 16.0, 6.0, 2.0, 0.003),
    ],
    "Diffraction Grating": [
        WaveSource(0.20, 0.5, 0.8, 18.0, 3.0, 0.0, 0.001),
        WaveSource(0.40, 0.5, 0.8, 18.0, 3.0, 0.0, 0.001),
        WaveSource(0.60, 0.5, 0.8, 18.0, 3.0, 0.0, 0.001),
        WaveSource(0.80, 0.5, 0.8, 18.0, 3.0, 0.0, 0.001),
    ],
    "Chaos": [
        WaveSource(0.2, 0.3, 1.0, 7.0, 2.0, 0.0, 0.002),
        WaveSource(0.8, 0.2, 1.2, 11.0, 3.5, 1.2, 0.001),
        WaveSource(0.5, 0.8, 0.9, 14.0, 5.0, 2.4, 0.001),
        WaveSource(0.1, 0.7, 0.7, 20.0, 1.5, 3.6, 0.002),
        WaveSource(0.9, 0.6, 1.1, 9.0, 4.0, 4.8, 0.001),
    ],
    "Spiral": [
        WaveSource(0.5, 0.5, 1.0, 10.0, 3.0, 0.0, 0.002),
    ],
}


# ── Input ───────────────────────────────────────────────────
def read_key():
    """Read a single keypress (non-blocking)."""
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


# ── Wave Field Computation ──────────────────────────────────
def compute_field(
    sources: List[WaveSource],
    cols: int,
    rows: int,
    t: float,
) -> List[List[float]]:
    """
    Compute the wavefield amplitude at every character cell.

    Returns a 2D list of normalised amplitude values in [-1, 1].
    Uses vectorised-style computation per row for performance.
    """
    field = [[0.0] * cols for _ in range(rows)]

    for y in range(rows):
        ny = y / max(rows - 1, 1)
        for x in range(cols):
            nx = x / max(cols - 1, 1)

            total = 0.0
            for src in sources:
                if not src.active:
                    continue

                dx = nx - src.x
                dy = ny - src.y
                # Aspect ratio correction (terminal chars ~2:1)
                dx *= 2.0
                dist = math.sqrt(dx * dx + dy * dy)

                # Wave equation: A * sin(k*r - ω*t + φ) * e^(-α*r)
                k = src.frequency * math.pi * 2
                val = src.amplitude * math.sin(
                    k * dist - src.angular_freq * t + src.phase
                ) * math.exp(-src.attenuation * dist * 100)

                total += val

            # Normalise to [-1, 1] range
            field[y][x] = max(-1.0, min(1.0, total))

    return field


# ── Rendering ───────────────────────────────────────────────
def render_frame(
    field: List[List[float]],
    palette_fn,
    sources: List[WaveSource],
    cols: int,
    rows: int,
    show_hud: bool,
) -> str:
    """Render the wavefield as ANSI-coloured characters."""
    # Characters to represent amplitude
    # Negative → "valley" chars, Positive → "peak" chars
    CHARS = " ·░▒▓█▓▒░· "

    lines = []

    for y in range(rows):
        parts = []
        for x in range(cols):
            val = field[y][x]

            # Map [-1, 1] to [0, 1] for colour
            v = (val + 1.0) * 0.5

            # Choose character based on absolute amplitude
            abs_val = abs(val)
            char_idx = int(abs_val * (len(CHARS) - 1))
            char_idx = min(char_idx, len(CHARS) - 1)

            if abs_val < 0.02:
                ch = " "  # calm water
            else:
                ch = CHARS[char_idx]

            # Color: use palette with amplitude modulation
            r, g, b = palette_fn(v)

            # Add subtle depth: dim quieter regions
            brightness = 0.3 + 0.7 * abs_val
            r = int(r * brightness)
            g = int(g * brightness)
            b = int(b * brightness)

            parts.append(fg(r, g, b) + ch)

        line = "".join(parts) + RESET

        # Source indicators overlay
        if show_hud:
            for i, src in enumerate(sources):
                if not src.active:
                    continue
                sx = int(src.x * (cols - 1))
                sy = int(src.y * (rows - 1))
                if sy == y and 0 <= sx < cols:
                    indicator = f"{BOLD}{fg(255, 255, 100)}◉{RESET}"
                    # Replace character at source position
                    idx = sx * len(fg(0, 0, 0)) + len(fg(0, 0, 0))
                    # Simple approach: rebuild that position
                    char_idx = min(
                        int(abs(field[y][sx]) * (len(CHARS) - 1)),
                        len(CHARS) - 1,
                    )
                    line = (
                        line[:sx * (len(fg(0, 0, 0)) + 1)]
                        + indicator
                        + line[(sx + 1) * (len(fg(0, 0, 0)) + 1):]
                    )

        lines.append(line)

    return "\n".join(lines)


def render_hud(
    sources: List[WaveSource],
    palette_name: str,
    preset_name: str,
    paused: bool,
    speed: int,
    t: float,
) -> str:
    """Render the heads-up display line."""
    active = sum(1 for s in sources if s.active)
    total = len(sources)

    status = "⏸ PAUSED" if paused else "▶ PLAYING"
    src_str = "".join(
        f"{'◉' if s.active else '○'}" for s in sources
    )

    hud = (
        f"{BOLD}{fg(120, 200, 255)}"
        f"🌊 Wave Interference {RESET} │ "
        f"{src_str} ({active}/{total}) │ "
        f"{palette_name} │ {preset_name} │ "
        f"t={t:.1f}s │ {speed}× │ {status}{RESET}"
    )
    return hud


def render_controls() -> str:
    """Render the control help line."""
    return (
        f"{DIM}"
        f"[1-{min(9, 9)}]sources [p]palette [n]preset [r]reset "
        f"[a]amp [f]freq [h]HUD [Space]pause [+/-]speed [q]quit"
        f"{RESET}"
    )


# ── Main Loop ───────────────────────────────────────────────
def main():
    # Seed for reproducible presets
    random.seed(42)

    # Initial setup
    preset_names = list(PRESETS.keys())
    preset_idx = 0
    sources = list(PRESETS[preset_names[preset_idx]])

    palette_names = list(PALETTES.keys())
    palette_idx = 0

    show_hud = True
    paused = False
    speed = 1
    t = 0.0
    fps = 20
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

    print(HOME, end="", flush=True)
    print("\033[2J", end="", flush=True)  # clear screen
    print(HIDE, end="", flush=True)

    try:
        while True:
            t_start = time.monotonic()

            # ── Input ───────────────────────────────────
            event = read_key()
            if event:
                kind, val = event
                if kind == "key":
                    if val in ("q", "escape"):
                        break
                    elif val == "p":
                        palette_idx = (palette_idx + 1) % len(palette_names)
                    elif val == "r":
                        sources = list(PRESETS[preset_names[preset_idx]])
                        t = 0.0
                    elif val == "n":
                        preset_idx = (preset_idx + 1) % len(preset_names)
                        sources = list(PRESETS[preset_names[preset_idx]])
                        t = 0.0
                    elif val == " ":
                        paused = not paused
                    elif val == "+":
                        speed = min(10, speed + 1)
                    elif val == "-":
                        speed = max(1, speed - 1)
                    elif val == "h":
                        show_hud = not show_hud
                    elif val == "a":
                        # Scale amplitude of all sources
                        for s in sources:
                            s.amplitude = s.amplitude * 1.2 if s.amplitude < 3.0 else 0.3
                    elif val == "f":
                        # Scale frequency of all sources
                        for s in sources:
                            s.frequency = (
                                s.frequency * 1.3
                                if s.frequency < 30.0
                                else 5.0
                            )
                    elif val in ("1", "2", "3", "4", "5", "6", "7", "8", "9"):
                        idx = int(val) - 1
                        if idx < len(sources):
                            sources[idx].active = not sources[idx].active

            # ── Update ──────────────────────────────────
            if not paused:
                t += frame_time * speed

            # ── Compute wavefield ────────────────────────
            size = term_size()
            cols = size.columns
            rows = size.lines - 2  # reserve lines for HUD + controls

            field = compute_field(sources, cols, rows, t)

            # ── Render ──────────────────────────────────
            palette_name = palette_names[palette_idx]
            preset_name = preset_names[preset_idx]

            frame = render_frame(
                field,
                PALETTES[palette_name],
                sources,
                cols,
                rows,
                show_hud,
            )

            # Build full output
            output_lines = [HOME]
            output_lines.append(frame)

            if show_hud:
                output_lines.append(
                    render_hud(
                        sources, palette_name, preset_name,
                        paused, speed, t,
                    )
                )
                output_lines.append(render_controls())

            print("\n".join(output_lines), end="", flush=True)

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
        print(f"{BOLD}🌊 Wave Interference{RESET} — Adeus! 🌊")


if __name__ == "__main__":
    main()

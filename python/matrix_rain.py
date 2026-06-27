#!/usr/bin/env python3
"""
Matrix Digital Rain — Terminal ANSI Effect
============================================
Inspired by The Matrix (1999).

Green katakana characters cascade down the terminal,
fading trails, occasional brighter "head" characters.

Zero external dependencies. Press 'q' or ESC to exit.
"""

import io
import logging
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Ensure UTF-8 for Windows terminal
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
elif hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logger = logging.getLogger(__name__)

# ====================================================================================================
# Constants
# ====================================================================================================

FPS     : int = 30
FRAME_S : float = 1.0 / FPS

HIDE  : str = "\033[?25l"
SHOW  : str = "\033[?25h"
HOME  : str = "\033[H"
RESET : str = "\033[0m"
BOLD  : str = "\033[1m"

KATAKANA: str = (
    "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜｦﾝ"
    "ﾞﾟ･ｰ｡｢｣､"
    "アイウエオカキクケコサシスセソ"
    "タチツテトナニヌネノハヒフヘホ"
    "マミムメモヤユヨラリルレロワヲン"
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
)

# ====================================================================================================
# Dataclasses
# ====================================================================================================


@dataclass
class Drop:
    """A single falling katakana column."""
    x : int
    y : float          # float for smooth movement
    speed : float       # chars per second
    length : int        # trail length
    head_bright : int   # 0-255 brightness for the head char
    fade : float        # how quickly the trail fades (0-1 per char)
    chars : List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        n = self.length + 5  # extra buffer
        self.chars = [random.choice(KATAKANA) for _ in range(n)]

    def new_char(self) -> str:
        """Return a random katakana character."""
        return random.choice(KATAKANA)


@dataclass
class Scene:
    """The full digital rain scene."""
    W : int = 80
    H : int = 24
    drops : List[Drop] = field(default_factory=list)
    density : float = 0.08  # fraction of columns with a drop
    bg_color : Tuple[int, int, int] = (0, 5, 0)  # very dark green
    time : float = 0.0


# ====================================================================================================
# Terminal Helpers
# ====================================================================================================


def fg(r: int, g: int, b: int) -> str:
    """Return ANSI truecolor foreground escape code."""
    return f"\033[38;2;{r};{g};{b}m"


def green_bright(b: int) -> str:
    """Green foreground at brightness *b* (0-255)."""
    g = max(0, min(255, b))
    return fg(0, g, 10 + g // 6)


def get_terminal_size() -> Tuple[int, int]:
    """Return terminal (columns, lines), falling back to 80x24."""
    try:
        import shutil
        w, h = shutil.get_terminal_size((80, 24))
        return w, h
    except Exception:
        return 80, 24


# ====================================================================================================
# Keyboard Input (Non-Blocking)
# ====================================================================================================


def get_key() -> Optional[str]:
    """Read a single keypress without blocking. Returns ``None`` if no key."""
    if sys.platform == "win32":
        import msvcrt
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch == '\xe0':
                _ = msvcrt.getwch()  # consume arrow
                return None
            return ch
    else:
        import select
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
    return None


# ====================================================================================================
# Rain Logic
# ====================================================================================================


def init_scene() -> Scene:
    """Create a new Scene matching the current terminal size."""
    w, h = get_terminal_size()
    return Scene(W=w, H=h)


def spawn_drop(scene: Scene) -> Drop:
    """Create a new Drop at a random column."""
    x = random.randint(0, scene.W - 1)
    speed = 3 + random.random() * 8
    length = random.randint(5, 20)
    head_bright = random.randint(180, 255)
    fade = 0.4 + random.random() * 0.4
    return Drop(
        x=x, y=0.0,
        speed=speed,
        length=length,
        head_bright=head_bright,
        fade=fade,
    )


def update_scene(scene: Scene, dt: float) -> None:
    """Advance the rain simulation by *dt* seconds."""
    scene.time += dt

    # Spawn new drops
    target_count = int(scene.W * scene.density)
    while len(scene.drops) < target_count:
        if random.random() < dt * 3:
            scene.drops.append(spawn_drop(scene))

    # Update existing drops
    new_drops = []
    for drop in scene.drops:
        drop.y += drop.speed * dt
        # Random character flicker while falling
        if random.random() < dt * 10:
            idx = random.randint(0, min(len(drop.chars) - 1, drop.length + 2))
            drop.chars[idx] = drop.new_char()
        # Keep if still on screen
        if drop.y - drop.length < scene.H:
            new_drops.append(drop)
        else:
            # Chance to respawn at top instead of disappearing
            if random.random() < 0.3:
                drop.y = 0.0
                drop.x = random.randint(0, scene.W - 1)
                drop.speed = 3 + random.random() * 8
                drop.length = random.randint(5, 20)
                drop.head_bright = random.randint(180, 255)
                new_drops.append(drop)

    scene.drops = new_drops


# ====================================================================================================
# Rendering
# ====================================================================================================

# Column-indexed cache of drops for faster rendering (global, rebuilt per frame)
drop_scan_cache: Dict[int, List[Drop]] = {}


def build_drop_cache(scene: Scene) -> Dict[int, List[Drop]]:
    """Build a column-indexed cache of drops for faster rendering."""
    cache: Dict[int, List[Drop]] = {}
    for drop in scene.drops:
        cache.setdefault(drop.x, []).append(drop)
    return cache


# ====================================================================================================
# Main
# ====================================================================================================


def main() -> None:
    """Run the Matrix rain animation."""
    sys.stdout.write(HIDE)
    sys.stdout.flush()

    scene = init_scene()
    last_time = time.perf_counter()
    running = True
    try:
        while running:
            now = time.perf_counter()
            dt = min(now - last_time, 0.1)
            last_time = now

            # Handle resize
            new_w, new_h = get_terminal_size()
            if new_w != scene.W or new_h != scene.H:
                scene.W = new_w
                scene.H = new_h

            # Check for quit key
            key = get_key()
            while key is not None:
                if key in ('q', 'Q', '\x1b'):
                    running = False
                key = get_key()

            if not running:
                break

            update_scene(scene, dt)

            # Build frame from row_parts
            row_parts: Dict[Tuple[int, int], Tuple[str, int]] = {}
            for drop in scene.drops:
                head_y = int(drop.y)
                if head_y < 0 or drop.x < 0 or drop.x >= scene.W:
                    continue
                for i in range(drop.length + 1):
                    ty = head_y - i
                    if ty < 0 or ty >= scene.H:
                        continue
                    if i == 0:
                        brightness = drop.head_bright
                    else:
                        brightness = int(drop.head_bright * ((1 - drop.fade) ** i))
                    if brightness < 10:
                        break
                    ci = min(i, len(drop.chars) - 1)
                    ch = drop.chars[ci]
                    # Keep the brightest char for each cell
                    if brightness > row_parts.get((ty, drop.x), (None, 0))[1]:
                        row_parts[(ty, drop.x)] = (ch, brightness)

            frame_rows: List[str] = []
            for y in range(scene.H):
                row = ""
                for x in range(scene.W):
                    key = (y, x)
                    if key in row_parts:
                        ch, b = row_parts[key]
                        if b > 200:
                            row += fg(180, 255, 180) + BOLD + ch + RESET
                        else:
                            row += green_bright(b) + ch + RESET
                    else:
                        row += "\033[48;2;0;5;0m " + RESET
                frame_rows.append(row)

            frame = HOME + "\n".join(frame_rows)
            sys.stdout.write(frame)
            sys.stdout.flush()

            sleep_time = (1.0 / 30) - (time.perf_counter() - now)
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(SHOW + RESET + "\n")
        sys.stdout.flush()
        print(f"{fg(0, 200, 0)}Matrix Rain — desconectado.{RESET}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()

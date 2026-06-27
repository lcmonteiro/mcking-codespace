#!/usr/bin/env python3
"""
lifelike.py — Artificial Life Simulator 🌱🧬
==============================================
Evolutionary cellular automata in the terminal.
Conway's Game of Life + custom rules + species + gliders.

Features:
  - Multiple rule sets (Conway, Seeds, Life Without Death, Day & Night)
  - Glider gun & pattern loader
  - Species mode: cells coloured by generation/lineage
  - Pause, step, reset, speed controls
  - Pure Python, stdlib only, ANSI truecolor

Controls:
  Space : pause/resume   R : random fill    C : clear
  S     : step (when paused)   Q : quit
  +/-   : speed up/down   G : toggle glider gun
  T     : toggle species colours   H : help
  Enter : next rule set
"""

import io
import logging
import math
import os
import random
import shutil
import sys
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ====================================================================================================
# ANSI Helpers
# ====================================================================================================


def csi(*seq: int) -> str:
    """Return CSI escape sequence."""
    return f"\033[{';'.join(str(s) for s in seq)}m"


def rgb(r: int, g: int, b: int) -> str:
    """ANSI truecolor foreground."""
    return csi(38, 2, r, g, b)


def bg_rgb(r: int, g: int, b: int) -> str:
    """ANSI truecolor background."""
    return csi(48, 2, r, g, b)


SAVE  : str = csi()
HOME  : str = "\033[H"
HIDE  : str = "\033[?25l"
SHOW  : str = "\033[?25h"
CLEAR : str = "\033[2J"


# ====================================================================================================
# Rule Definitions
# ====================================================================================================


@dataclass
class Rule:
    """A cellular automaton rule set."""
    name : str
    survive : Set[int]     # neighbour counts for survival
    birth : Set[int]       # neighbour counts for birth
    description : str = ""


RULES: List[Rule] = [
    Rule("Conway", {2, 3}, {3}, "Classic Game of Life"),
    Rule("HighLife", {2, 3}, {3, 6}, "Like Conway but 6 makes birth"),
    Rule("Seeds", set(), {2}, "Birth only — cells die next frame"),
    Rule("Life Without Death", set(range(9)), {3}, "Cells never die, only born"),
    Rule("Day & Night", {3, 4, 6, 7, 8}, {3, 6, 7, 8}, "Symmetric day/night pattern"),
    Rule("Maze", {1, 2, 3, 4, 5}, {3}, "Grows maze-like structures"),
    Rule("Coral", {2, 3, 5, 6, 7}, {4, 5, 7, 8}, "Seashell coral growth"),
    Rule("Anneal", set(range(9)), {4, 6, 7, 8}, "Fills with chaotic patterns"),
    Rule("Assimilation", {4, 5, 6, 7}, {3, 4, 5}, "Cells spread and assimilate"),
    Rule("2x2", {1, 2, 5}, {3, 6}, "Replicator-friendly"),
]


# ====================================================================================================
# Glider Patterns
# ====================================================================================================

GLIDER_GUN: str = """\
.....................................
**...............................**.
*.*.............................**.
.*...........**.................**.
............*.*....................
..............*....................
...........**.*....**..............
............***....*.*.............
.....................*.............
....................**.............
.....................................
.....................................
.....................................
.....................................
.....................................
.....................................
.....................................
"""

PULSAR: str = """\
...............
.....###.......
...............
..#.....#......
..#.....#......
..#.....#......
..###.###......
...............
..###.###......
..#.....#......
..#.....#......
..#.....#......
...............
.....###.......
...............
"""


def parse_pattern(pattern: str, offset_x: int, offset_y: int) -> Set[Tuple[int, int]]:
    """Parse an ASCII pattern and return a set of (x, y) live cells."""
    cells: Set[Tuple[int, int]] = set()
    for y, line in enumerate(pattern.strip("\n").split("\n")):
        for x, ch in enumerate(line):
            if ch == '*':
                cells.add((x + offset_x, y + offset_y))
    return cells


# ====================================================================================================
# Colour Palettes
# ====================================================================================================

PALETTES: Dict[str, List[Tuple[int, int, int]]] = {
    "viridis": [
        (68, 1, 84), (59, 82, 139), (33, 145, 140),
        (94, 201, 98), (158, 218, 57), (253, 231, 37),
    ],
    "plasma": [
        (13, 8, 135), (126, 3, 168), (204, 71, 120),
        (248, 149, 64), (255, 215, 0), (240, 249, 33),
    ],
    "fire": [
        (80, 0, 0), (180, 30, 0), (255, 80, 0),
        (255, 160, 0), (255, 220, 80), (255, 255, 200),
    ],
    "ocean": [
        (0, 10, 50), (0, 50, 120), (0, 100, 180),
        (0, 150, 200), (100, 200, 220), (180, 240, 255),
    ],
    "matrix": [
        (0, 50, 0), (0, 80, 0), (0, 120, 0),
        (0, 180, 0), (100, 220, 100), (200, 255, 200),
    ],
    "neon": [
        (255, 0, 128), (255, 128, 0), (255, 255, 0),
        (0, 255, 128), (0, 128, 255), (128, 0, 255),
    ],
}

PALETTE_NAMES: List[str] = list(PALETTES.keys())

# Global tracker for `render_hud` and `main`
current_palette: int = 0


# ====================================================================================================
# Cellular Automaton Engine
# ====================================================================================================


class CellState(Enum):
    """State of a single cell."""
    DEAD = 0
    ALIVE = 1


@dataclass
class Cell:
    """A single cell in the automaton grid."""
    state : CellState = CellState.DEAD
    age : int = 0
    species_id : int = 0
    birth_gen : int = 0


class LifeEngine:
    """The cellular automaton engine."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.grid: List[List[Cell]] = [
            [Cell() for _ in range(width)] for _ in range(height)
        ]
        self.rule_index = 0
        self.rule = RULES[self.rule_index]
        self.generation = 0
        self.population = 0
        self.next_species_id = 1
        self.species_mode = True
        self.show_grid_lines = False

    # ── Rule switching ───────────────────────────────────────────────────

    def get_rule(self) -> Rule:
        """Return the current rule."""
        return self.rule

    def next_rule(self) -> None:
        """Advance to the next rule set."""
        self.rule_index = (self.rule_index + 1) % len(RULES)
        self.rule = RULES[self.rule_index]

    def prev_rule(self) -> None:
        """Go back to the previous rule set."""
        self.rule_index = (self.rule_index - 1) % len(RULES)
        self.rule = RULES[self.rule_index]

    # ── Neighbour computation ───────────────────────────────────────────

    def count_neighbours(self, x: int, y: int) -> int:
        """Count living neighbours with wrapping (toroidal surface)."""
        count = 0
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx = (x + dx) % self.width
                ny = (y + dy) % self.height
                if self.grid[ny][nx].state == CellState.ALIVE:
                    count += 1
        return count

    # ── Generation step ─────────────────────────────────────────────────

    def step(self) -> int:
        """Advance one generation.  Returns population after step."""
        rule = self.rule
        changes: List[Tuple[int, int, bool]] = []

        for y in range(self.height):
            row = self.grid[y]
            for x in range(self.width):
                cell = row[x]
                n = self.count_neighbours(x, y)
                alive = cell.state == CellState.ALIVE

                if alive:
                    if n not in rule.survive:
                        changes.append((x, y, False))
                else:
                    if n in rule.birth:
                        changes.append((x, y, True))

        pop = 0
        for x, y, become_alive in changes:
            cell = self.grid[y][x]
            if become_alive:
                cell.state = CellState.ALIVE
                if self.species_mode:
                    neighbours: List[int] = []
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            if dx == 0 and dy == 0:
                                continue
                            nx = (x + dx) % self.width
                            ny = (y + dy) % self.height
                            nc = self.grid[ny][nx]
                            if nc.state == CellState.ALIVE:
                                neighbours.append(nc.species_id)
                    if neighbours:
                        cell.species_id = max(set(neighbours), key=neighbours.count)
                    else:
                        cell.species_id = self.next_species_id
                        self.next_species_id += 1
                    cell.birth_gen = self.generation
                cell.age = 0
            else:
                cell.state = CellState.DEAD
                cell.age = 0

        for y in range(self.height):
            for x in range(self.width):
                cell = self.grid[y][x]
                if cell.state == CellState.ALIVE:
                    cell.age += 1
                    pop += 1

        self.population = pop
        self.generation += 1
        return pop

    # ── Grid operations ─────────────────────────────────────────────────

    def clear(self) -> None:
        """Clear the grid."""
        for y in range(self.height):
            for x in range(self.width):
                c = self.grid[y][x]
                c.state = CellState.DEAD
                c.age = 0
                c.species_id = 0
                c.birth_gen = 0
        self.generation = 0
        self.population = 0
        self.next_species_id = 1

    def random_fill(self, density: float = 0.35) -> None:
        """Fill grid randomly with given *density*."""
        for y in range(self.height):
            for x in range(self.width):
                cell = self.grid[y][x]
                if random.random() < density:
                    cell.state = CellState.ALIVE
                    cell.age = 0
                    if self.species_mode:
                        cell.species_id = self.next_species_id
                        self.next_species_id += 1
                    else:
                        cell.species_id = 0
                else:
                    cell.state = CellState.DEAD
        self.population = sum(
            1 for row in self.grid for c in row if c.state == CellState.ALIVE
        )

    def place_pattern(self, cells: Set[Tuple[int, int]],
                      offset_x: int = 0, offset_y: int = 0) -> None:
        """Place a pattern of live cells on the grid."""
        for x, y in cells:
            gx, gy = (x + offset_x) % self.width, (y + offset_y) % self.height
            cell = self.grid[gy][gx]
            cell.state = CellState.ALIVE
            cell.age = 0
            if self.species_mode:
                cell.species_id = self.next_species_id
                self.next_species_id += 1
        self.population = sum(
            1 for row in self.grid for c in row if c.state == CellState.ALIVE
        )

    # ── Colour ──────────────────────────────────────────────────────────

    def get_cell_colour(self, x: int, y: int,
                        palette_idx: int = 0) -> Tuple[int, int, int]:
        """Return the colour for cell at (*x*, *y*)."""
        cell = self.grid[y][x]
        if cell.state != CellState.ALIVE:
            return (0, 0, 0)

        palette = PALETTES[PALETTE_NAMES[palette_idx % len(PALETTES)]]

        if self.species_mode and cell.species_id > 0:
            idx = (cell.species_id * 7 + cell.age * 3) % len(palette)
            r, g, b = palette[idx]
            factor = min(1.0, 0.3 + cell.age * 0.02)
            r = min(255, int(r * factor))
            g = min(255, int(g * factor))
            b = min(255, int(b * factor))
            return (r, g, b)
        else:
            t = min(1.0, cell.age / 30)
            idx = min(len(palette) - 1, int(t * (len(palette) - 1)))
            return palette[idx]


# ====================================================================================================
# Terminal Renderer
# ====================================================================================================

DENSITY_CHARS: List[str] = ["·", "·", "·", "·", ".", "·", "+", "*", "◆", "★"]


@dataclass
class Screen:
    """Off-screen buffer for composing a frame before flush."""
    width : int
    height : int
    chars : List[List[str]] = field(init=False)
    colours : List[List[Tuple[int, int, int]]] = field(init=False)

    def __post_init__(self) -> None:
        self.chars = [[" "] * self.width for _ in range(self.height)]
        self.colours = [[(0, 0, 0)] * self.width for _ in range(self.height)]

    def clear(self) -> None:
        """Reset the buffer to empty."""
        for y in range(self.height):
            for x in range(self.width):
                self.chars[y][x] = " "
                self.colours[y][x] = (0, 0, 0)

    def set(self, x: int, y: int, ch: str,
            colour: Tuple[int, int, int]) -> None:
        """Place a character with colour at (*x*, *y*)."""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.chars[y][x] = ch
            self.colours[y][x] = colour

    def render(self) -> str:
        """Render the buffer to an ANSI-escaped string."""
        out: List[str] = [HOME]
        last_r, last_g, last_b = -1, -1, -1
        for y in range(self.height):
            for x in range(self.width):
                r, g, b = self.colours[y][x]
                ch = self.chars[y][x]
                if r != last_r or g != last_g or b != last_b:
                    out.append(rgb(r, g, b))
                    last_r, last_g, last_b = r, g, b
                out.append(ch)
            out.append("\n")
            last_r, last_g, last_b = -1, -1, -1
        out.append(SAVE)
        return "".join(out)


# ====================================================================================================
# HUD
# ====================================================================================================


def render_hud(screen: Screen, engine: LifeEngine,
               fps: float, paused: bool, glider_active: bool) -> None:
    """Draw the HUD info bar at the bottom of the screen."""
    rule = engine.get_rule()
    w, h = screen.width, screen.height

    bar_y = h - 1
    rule_text = f" 🧬 {rule.name} — {rule.description} "
    pop_text = f" Pop: {engine.population:>5} "
    gen_text = f" Gen: {engine.generation:>5} "
    fps_text = f" {fps:.0f} fps "
    paused_text = " ⏸ PAUSED " if paused else " ▶ "

    info = f"{paused_text}{rule_text}{pop_text}{gen_text}{fps_text}"
    if glider_active:
        info += " 🛸 Glider Gun "

    for x in range(w):
        screen.set(x, bar_y, " ", (15, 15, 25))

    for x, ch in enumerate(info):
        if x < w:
            screen.set(x, bar_y, ch, (180, 220, 255))

    leg_y = 0
    pal_name = PALETTE_NAMES[current_palette]
    species_text = " 🧬 Species" if engine.species_mode else " 🌱 Age"
    leg = f" [{pal_name}] {species_text}  [Space=⏯  F1=Help] "

    for x in range(len(leg)):
        if x < w:
            screen.set(x, leg_y, leg[x], (140, 180, 220))


# ====================================================================================================
# Help Screen
# ====================================================================================================


def show_help(screen: Screen) -> None:
    """Overlay the help screen onto *screen*."""
    help_lines: List[str] = [
        "╔══════════════════════════════════════════════╗",
        "║        🧬 LifeLike — Controls               ║",
        "╠══════════════════════════════════════════════╣",
        "║  Space  Pause / Resume                      ║",
        "║  R      Random fill (35%)                   ║",
        "║  C      Clear grid                          ║",
        "║  S      Step one frame (when paused)        ║",
        "║  +/-    Speed up / down                     ║",
        "║  Enter  Next rule set                       ║",
        "║  B      Previous rule set                   ║",
        "║  G      Toggle Glider Gun                   ║",
        "║  T      Toggle species colours              ║",
        "║  P      Cycle colour palette                ║",
        "║  Q      Quit                                ║",
        "╚══════════════════════════════════════════════╝",
    ]
    start_y = max(0, (screen.height // 2) - 8)
    start_x = max(0, (screen.width // 2) - 22)
    for i, line in enumerate(help_lines):
        y = start_y + i
        if y < screen.height:
            for x, ch in enumerate(line):
                sx = start_x + x
                if 0 <= sx < screen.width:
                    colour = (100, 200, 255) if i == 1 else (180, 180, 200)
                    if i in (0, 5):
                        colour = (80, 80, 100)
                    screen.set(sx, y, ch, colour)


# ====================================================================================================
# Main Loop
# ====================================================================================================


def main() -> None:
    """Entry point with error handling."""
    try:
        _main()
    except KeyboardInterrupt:
        pass
    finally:
        print(SHOW, end="", flush=True)


def _main() -> None:
    """Run the interactive Life simulator."""
    global current_palette
    ts = shutil.get_terminal_size()
    W = ts.columns - 1
    H = ts.lines

    grid_h = H - 2
    grid_w = W

    engine = LifeEngine(grid_w, grid_h)
    screen = Screen(W, H)

    engine.random_fill(0.3)

    paused = False
    running = True
    speed = 8
    glider_active = False
    glider_pos = (5, 5)
    current_palette = 0

    frame_time = 1.0 / speed
    last_frame = time.monotonic()
    fps = speed
    fps_counter = 0
    fps_timer = time.monotonic()

    help_visible = False

    if sys.platform == "win32":
        import msvcrt

    def get_key() -> Optional[str]:
        """Read a keypress without blocking (Windows msvcrt)."""
        if sys.platform == "win32":
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch == '\xe0':
                    ch2 = msvcrt.getwch()
                    return {
                        'H': 'KEY_UP', 'P': 'KEY_DOWN',
                        'K': 'KEY_LEFT', 'M': 'KEY_RIGHT',
                    }.get(ch2, None)
                return ch
        return None

    print(HIDE + CLEAR + HOME, end="", flush=True)

    while running:
        now = time.monotonic()

        while True:
            key = get_key()
            if key is None:
                break

            if key == 'q' or key == 'Q':
                running = False
            elif key == ' ':
                paused = not paused
                help_visible = False
            elif key == 'r' or key == 'R':
                engine.random_fill(0.35)
                help_visible = False
            elif key == 'c' or key == 'C':
                engine.clear()
                help_visible = False
            elif key == 's' or key == 'S':
                if paused:
                    engine.step()
                help_visible = False
            elif key == '+':
                speed = min(60, speed + 2)
                frame_time = 1.0 / speed
                help_visible = False
            elif key == '-':
                speed = max(1, speed - 1)
                frame_time = 1.0 / speed
                help_visible = False
            elif key == '\r' or key == '\n':
                engine.next_rule()
                help_visible = False
            elif key == 'b' or key == 'B':
                engine.prev_rule()
                help_visible = False
            elif key == 'g' or key == 'G':
                glider_active = not glider_active
                if glider_active:
                    cells = parse_pattern(GLIDER_GUN, glider_pos[0], glider_pos[1])
                    engine.place_pattern(cells)
                help_visible = False
            elif key == 't' or key == 'T':
                engine.species_mode = not engine.species_mode
                help_visible = False
            elif key == 'p' or key == 'P':
                current_palette = (current_palette + 1) % len(PALETTE_NAMES)
                help_visible = False
            elif key == 'h' or key == 'H':
                help_visible = not help_visible

        if not paused and now - last_frame >= frame_time:
            engine.step()
            last_frame = now

            if glider_active and engine.population < 20:
                cells = parse_pattern(GLIDER_GUN,
                    random.randint(0, W - 40),
                    random.randint(0, grid_h - 10))
                engine.place_pattern(cells)

        fps_counter += 1
        if now - fps_timer >= 1.0:
            fps = fps_counter / (now - fps_timer)
            fps_counter = 0
            fps_timer = now

        screen.clear()

        if not help_visible:
            for y in range(grid_h):
                for x in range(grid_w):
                    cell = engine.grid[y][x]
                    if cell.state == CellState.ALIVE:
                        colour = engine.get_cell_colour(x, y, current_palette)
                        age_idx = min(len(DENSITY_CHARS) - 1, cell.age // 3)
                        ch = DENSITY_CHARS[age_idx]
                        screen.set(x, y, ch, colour)

            render_hud(screen, engine, fps, paused, glider_active)
        else:
            show_help(screen)

        sys.stdout.write(screen.render())
        sys.stdout.flush()

        remaining = frame_time - (time.monotonic() - last_frame)
        if remaining > 0.005 and not paused:
            time.sleep(min(remaining, 0.05))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()

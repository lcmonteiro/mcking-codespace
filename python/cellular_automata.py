#!/usr/bin/env python3
"""
🌀 Cellular Automata Playground
================================
Interactive terminal visualizer for 2D cellular automata rules:

- Conway's Game of Life
- Wireworld (digital logic)
- Brian's Brain
- Seeds
- Day & Night
- HighLife

Controls:
  SPACE  — pause/resume
  R      — randomize
  C      — clear
  +/-    — speed up / slow down
  TAB    — cycle rule set
  arrows — move cursor
  click/spawn with cursor + ENTER
  1-6    — quick select rule
  Q      — quit
"""

import argparse
import logging
import os
import random
import sys
import time
from typing import Callable, List, Set, Tuple

logger = logging.getLogger(__name__)

# ====================================================================================================
# Constants
# ====================================================================================================

BLOCK   : str = " "  # use background color for fill
RESET   : str = "\033[0m"


# ====================================================================================================
# Rulesets
# ====================================================================================================


class Ruleset:
    """Defines a cellular automaton: name, survival bits, birth bits, optional special behavior."""

    def __init__(
        self,
        name: str,
        survive: Set[int],
        birth: Set[int],
        special: str = None,
        colors: dict = None,
    ) -> None:
        self.name = name
        self.survive = survive
        self.birth = birth
        self.special = special  # "wireworld" etc
        self.colors = colors or {
            0: (0, 0, 0),          # dead
            1: (200, 200, 100),    # alive
        }

    def next(self, alive: bool, neighbors: int) -> int:
        """Compute next state: 0 = dead, 1 = alive."""
        if self.special == "wireworld":
            return 0  # placeholder, handled in update_grid
        if alive:
            return 1 if neighbors in self.survive else 0
        else:
            return 1 if neighbors in self.birth else 0


RULES: List[Ruleset] = [
    Ruleset("Conway's Life", {2, 3}, {3}),
    Ruleset("HighLife",      {2, 3}, {3, 6}),
    Ruleset("Seeds",         set(),  {2}),
    Ruleset("Brian's Brain", set(),  {2}, special="briansbrain"),
    Ruleset("Day & Night",   {3, 4, 6, 7, 8}, {3, 6, 7, 8}),
    Ruleset("Wireworld",     set(),  set(), special="wireworld",
            colors={0: (10, 10, 20), 1: (255, 255, 100), 2: (200, 100, 50), 3: (100, 100, 255)}),
]


# ====================================================================================================
# ANSI Helpers
# ====================================================================================================


def ansi_fg(r: int, g: int, b: int) -> str:
    """Return ANSI truecolor foreground escape sequence."""
    return f"\033[38;2;{r};{g};{b}m"


def ansi_bg(r: int, g: int, b: int) -> str:
    """Return ANSI truecolor background escape sequence."""
    return f"\033[48;2;{r};{g};{b}m"


def color_block(r: int, g: int, b: int) -> str:
    """Return an ANSI-colored block character."""
    return f"{ansi_bg(r, g, b)}{BLOCK}{RESET}"


def gradient(t: float) -> Tuple[int, int, int]:
    """Map *t* in [0,1] to a nice color gradient (Blue → Cyan → Green → Yellow → Red)."""
    if t < 0.25:
        return (0, int(t * 4 * 255), 255)
    elif t < 0.5:
        return (0, 255, int((1 - (t - 0.25) * 4) * 255))
    elif t < 0.75:
        return (int((t - 0.5) * 4 * 255), 255, 0)
    else:
        return (255, int((1 - (t - 0.75) * 4) * 255), 0)


# ====================================================================================================
# Terminal Helpers
# ====================================================================================================


def get_terminal_size() -> Tuple[int, int]:
    """Return terminal (columns, lines), falling back to 80x24."""
    try:
        import shutil
        w, h = shutil.get_terminal_size()
        return w, h
    except Exception:
        return 80, 24


def clear_screen() -> None:
    """Clear the terminal screen."""
    os.system("cls" if sys.platform == "win32" else "clear")


def set_cursor(y: int, x: int) -> None:
    """Move cursor to (*y*, *x*)."""
    print(f"\033[{y};{x}H", end="")


def hide_cursor() -> None:
    """Hide terminal cursor."""
    print("\033[?25l", end="")


def show_cursor() -> None:
    """Show terminal cursor."""
    print("\033[?25h", end="")


# ====================================================================================================
# Grid
# ====================================================================================================


class Grid:
    """2D cellular automaton grid of cells."""

    def __init__(self, width: int, height: int) -> None:
        self.w = width
        self.h = height
        self.cells: List[int] = [0] * (width * height)
        self.wireworld_buffer: List[int] = [0] * (width * height)

    def index(self, x: int, y: int) -> int:
        """Return flat array index for (*x*, *y*)."""
        return y * self.w + x

    def get(self, x: int, y: int) -> int:
        """Get cell value at (*x*, *y*)."""
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.cells[self.index(x, y)]
        return 0

    def get_ww(self, x: int, y: int) -> int:
        """Get Wireworld state (0-3) at (*x*, *y*)."""
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.wireworld_buffer[self.index(x, y)]
        return 0

    def set(self, x: int, y: int, val: int) -> None:
        """Set cell value at (*x*, *y*)."""
        if 0 <= x < self.w and 0 <= y < self.h:
            self.cells[self.index(x, y)] = val

    def set_ww(self, x: int, y: int, val: int) -> None:
        """Set Wireworld state at (*x*, *y*)."""
        if 0 <= x < self.w and 0 <= y < self.h:
            self.wireworld_buffer[self.index(x, y)] = val

    def randomize(self, density: float = 0.3) -> None:
        """Fill grid randomly with given *density*."""
        for i in range(len(self.cells)):
            self.cells[i] = 1 if random.random() < density else 0
        for i in range(len(self.wireworld_buffer)):
            if self.cells[i]:
                self.wireworld_buffer[i] = 3  # conductor
            else:
                self.wireworld_buffer[i] = 0

    def clear(self) -> None:
        """Clear all cells to dead."""
        for i in range(len(self.cells)):
            self.cells[i] = 0
            self.wireworld_buffer[i] = 0

    def glider(self, x: int, y: int) -> None:
        """Place a Gosper glider at (*x*, *y*)."""
        pattern = [
            (1, 0), (2, 1), (0, 2), (1, 2), (2, 2)
        ]
        for dx, dy in pattern:
            self.set(x + dx, y + dy, 1)

    def count_neighbors(self, x: int, y: int) -> int:
        """Count living neighbours of (*x*, *y*)."""
        n = 0
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                if self.get(x + dx, y + dy):
                    n += 1
        return n

    def count_neighbors_ww(self, x: int, y: int) -> int:
        """Count Wireworld head neighbours only, at (*x*, *y*)."""
        n = 0
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                if self.get_ww(x + dx, y + dy) == 1:  # heads
                    n += 1
        return n

    def step(self, rule: Ruleset) -> None:
        """Advance one generation according to the *rule*."""
        if rule.special == "wireworld":
            self._step_wireworld()
            return
        if rule.special == "briansbrain":
            self._step_briansbrain()
            return

        w, h = self.w, self.h
        new: List[int] = [0] * (w * h)
        for y in range(h):
            for x in range(w):
                alive = self.cells[y * w + x]
                n = self.count_neighbors(x, y)
                new[y * w + x] = rule.next(alive, n)
        self.cells = new

    def _step_wireworld(self) -> None:
        """Advance one generation of Wireworld."""
        w, h = self.w, self.h
        new = self.wireworld_buffer[:]
        for y in range(h):
            for x in range(w):
                idx = y * w + x
                state = self.wireworld_buffer[idx]
                if state == 1:       # head -> tail
                    new[idx] = 2
                elif state == 2:     # tail -> conductor
                    new[idx] = 3
                elif state == 3:     # conductor
                    heads = self.count_neighbors_ww(x, y)
                    new[idx] = 1 if 1 <= heads <= 2 else 3
                else:
                    new[idx] = 0
        self.wireworld_buffer = new
        for i in range(w * h):
            self.cells[i] = 1 if self.wireworld_buffer[i] else 0

    def _step_briansbrain(self) -> None:
        """Advance one generation of Brian's Brain."""
        w, h = self.w, self.h
        new: List[int] = [0] * (w * h)
        for y in range(h):
            for x in range(w):
                state = self.cells[y * w + x]
                n = self.count_neighbors(x, y)
                if state == 0 and n == 2:
                    new[y * w + x] = 1    # firing
                elif state == 1:
                    new[y * w + x] = 2    # refractory
                elif state == 2:
                    new[y * w + x] = 0    # resting
        self.cells = new

    def render(self, rule: Ruleset) -> List[str]:
        """Render grid to a list of ANSI-colored strings."""
        lines: List[str] = []
        w, h = self.w, self.h
        alive_color = rule.colors.get(1, (200, 200, 100))

        if rule.special == "wireworld":
            for y in range(h):
                line = ""
                for x in range(w):
                    state = self.get_ww(x, y)
                    if state == 0:
                        line += color_block(*rule.colors[0])
                    elif state == 1:
                        line += color_block(*rule.colors[1])
                    elif state == 2:
                        line += color_block(*rule.colors[2])
                    else:
                        line += color_block(*rule.colors[3])
                lines.append(line)
        elif rule.special == "briansbrain":
            for y in range(h):
                line = ""
                for x in range(w):
                    val = self.cells[y * w + x]
                    if val == 0:
                        line += color_block(5, 5, 10)
                    elif val == 1:
                        line += color_block(255, 255, 100)  # firing
                    else:
                        line += color_block(80, 40, 120)    # refractory
                lines.append(line)
        else:
            for y in range(h):
                line = ""
                for x in range(w):
                    val = self.cells[y * w + x]
                    if val:
                        line += color_block(*alive_color)
                    else:
                        line += color_block(5, 5, 10)
                lines.append(line)
        return lines


# ====================================================================================================
# Batch Mode
# ====================================================================================================


def run_batch(generations: int = 100) -> None:
    """Run simulation in headless batch mode, print stats at the end."""
    tw, th = get_terminal_size()
    grid_w = min(tw, 100)
    grid_h = min(th - 3, 40)
    if grid_w < 20 or grid_h < 20:
        grid_w, grid_h = 60, 25

    grid = Grid(grid_w, grid_h)
    grid.randomize(0.25)
    rule = RULES[0]

    start = time.time()
    for _ in range(generations):
        grid.step(rule)
    elapsed = time.time() - start

    live = sum(grid.cells)
    print(f"🌀 Cellular Automata — Batch Run")
    print(f"  Rule: {rule.name}")
    print(f"  Grid: {grid_w}x{grid_h}")
    print(f"  Generations: {generations}")
    print(f"  Time: {elapsed:.3f}s ({generations/elapsed:.0f} gen/s)")
    print(f"  Alive: {live}/{grid_w*grid_h} ({100*live/(grid_w*grid_h):.1f}%)")


# ====================================================================================================
# Interactive Main Loop
# ====================================================================================================


def main() -> None:
    """Run the interactive cellular automata playground."""
    hide_cursor()

    tw, th = get_terminal_size()
    grid_w = min(tw, 100)
    grid_h = min(th - 3, 40)

    if grid_w < 20 or grid_h < 20:
        grid_w, grid_h = 60, 25

    grid = Grid(grid_w, grid_h)
    grid.randomize(0.25)

    rule_idx = 0
    rule = RULES[rule_idx]

    paused = False
    speed = 0.1
    generation = 0

    cursor_x, cursor_y = grid_w // 2, grid_h // 2

    try:
        import msvcrt
        kb = "msvcrt"
    except ImportError:
        try:
            import termios, tty, select  # noqa: F401
            kb = "unix"
        except ImportError:
            kb = "none"

    def get_key() -> str:
        """Read a single keypress (blocking)."""
        if kb == "msvcrt":
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch == b'\xe0':
                    ch2 = msvcrt.getch()
                    mapping = {b'H': 'UP', b'P': 'DOWN', b'K': 'LEFT', b'M': 'RIGHT'}
                    return mapping.get(ch2, '')
                try:
                    return ch.decode('utf-8', errors='replace')
                except Exception:
                    return ''
        return ''

    while True:
        key = get_key()
        if key == 'q' or key == 'Q':
            break
        elif key == ' ':
            paused = not paused
        elif key == 'r' or key == 'R':
            grid.randomize(0.25)
            generation = 0
        elif key == 'c' or key == 'C':
            grid.clear()
            generation = 0
        elif key == '+' or key == '=':
            speed = max(0.01, speed * 0.7)
        elif key == '-' or key == '_':
            speed = min(2.0, speed / 0.7)
        elif key == '\t':
            rule_idx = (rule_idx + 1) % len(RULES)
            rule = RULES[rule_idx]
            if rule.special == "wireworld":
                grid.randomize(0.2)
        elif key == 'UP' and cursor_y > 0:
            cursor_y -= 1
        elif key == 'DOWN' and cursor_y < grid_h - 1:
            cursor_y += 1
        elif key == 'LEFT' and cursor_x > 0:
            cursor_x -= 1
        elif key == 'RIGHT' and cursor_x < grid_w - 1:
            cursor_x += 1
        elif key == '\r':
            if rule.special == "wireworld":
                current = grid.get_ww(cursor_x, cursor_y)
                grid.set_ww(cursor_x, cursor_y, 3 if current != 3 else 0)
                grid.set(cursor_x, cursor_y, 1 if current != 3 else 0)
            elif rule.special == "briansbrain":
                grid.set(cursor_x, cursor_y, 1 - grid.get(cursor_x, cursor_y))
            else:
                grid.set(cursor_x, cursor_y, 1 - grid.get(cursor_x, cursor_y))
        elif key.isdigit() and 1 <= int(key) <= 6:
            rule_idx = int(key) - 1
            rule = RULES[rule_idx]
            if rule.special == "wireworld":
                grid.randomize(0.2)

        if not paused:
            grid.step(rule)
            generation += 1

        clear_screen()
        rendered = grid.render(rule)

        for line in rendered:
            print(line)

        live = sum(grid.cells)
        bar_color = "\033[38;2;100;180;100m"
        dim = "\033[38;2;80;80;80m"
        bright = "\033[38;2;200;200;200m"
        gen_tag = f"{bar_color}⏱ gen {generation}{RESET}"
        live_tag = f"{bar_color}🧬 {live} live{RESET}"
        speed_tag = f"{bar_color}⚡ {1/speed:.0f} fps{RESET}"
        pause_tag = f"{bright}{'⏸ PAUSED' if paused else ' ▶ '}{RESET}"
        cursor_tag = f"{dim}📍({cursor_x},{cursor_y}){RESET}"

        ui_line = f"  {pause_tag}  {gen_tag}  {live_tag}  {speed_tag}  {cursor_tag}  {dim}{rule.name}{RESET}"
        print()
        print(ui_line)
        print(f"{dim}  [SPC]pause [R]and [C]lear [+/-]speed [TAB]cycle "
              f"[↑↓←→]cursor [↵]toggle [1-6]rules [Q]uit{RESET}")

        set_cursor(cursor_y + 1, cursor_x + 1)
        print(f"\033[38;2;255;255;255m╳{RESET}", end="")
        set_cursor(grid_h + 3, 1)

        time.sleep(speed)

    show_cursor()
    clear_screen()
    print("🌀 Cellular Automata — thanks for watching!\n")
    print(f"  Rule: {rule.name}")
    print(f"  Generations: {generation}")
    print(f"  Grid: {grid_w}x{grid_h}")
    print()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Cellular Automata Playground")
    parser.add_argument("--batch", type=int, nargs="?", const=200, default=None,
                        help="Run N generations in headless batch mode (default: 200)")
    args = parser.parse_args()
    if args.batch is not None:
        run_batch(args.batch)
    else:
        main()

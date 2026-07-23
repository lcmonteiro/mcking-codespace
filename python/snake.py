#!/usr/bin/env python3
"""
Terminal Snake Game
━━━━━━━━━━━━━━━━━
Classic snake with curses — smooth movement, growing snake, score tracking,
speed scaling, and colorful terminal rendering.

Controls:
  Arrow keys / WASD — move
  P — pause
  Q / Esc — quit

Run:
  python3 python/snake.py
"""

import curses
import random
import time
from collections import deque
from enum import Enum

# ── Constants ──────────────────────────────────────────────────────────

TITLE = "🐍 SNAKE"
INITIAL_SPEED = 120   # ms per tick (lower = faster)
MIN_SPEED = 45
SPEED_STEP = 3        # ms faster per food eaten

# ── Direction vectors ──────────────────────────────────────────────────

class Dir(Enum):
    UP    = (0, -1)
    DOWN  = (0, 1)
    LEFT  = (-1, 0)
    RIGHT = (1, 0)

OPPOSITE = {
    Dir.UP: Dir.DOWN, Dir.DOWN: Dir.UP,
    Dir.LEFT: Dir.RIGHT, Dir.RIGHT: Dir.LEFT,
}

# ── Game colors ────────────────────────────────────────────────────────

class Color:
    BORDER    = 1
    SNAKE_H   = 2   # head
    SNAKE_B   = 3   # body
    FOOD      = 4
    FOOD_GLOW = 5   # pulsing ring
    SCORE     = 6
    GAMEOVER  = 7
    PAUSED    = 8
    TITLE     = 9
    WALL_DECOR = 10

def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(Color.BORDER,    curses.COLOR_WHITE,   -1)
    curses.init_pair(Color.SNAKE_H,   curses.COLOR_GREEN,   -1)
    curses.init_pair(Color.SNAKE_B,   curses.COLOR_CYAN,    -1)
    curses.init_pair(Color.FOOD,      curses.COLOR_RED,     -1)
    curses.init_pair(Color.FOOD_GLOW, curses.COLOR_YELLOW,  -1)
    curses.init_pair(Color.SCORE,     curses.COLOR_YELLOW,  -1)
    curses.init_pair(Color.GAMEOVER,  curses.COLOR_RED,     -1)
    curses.init_pair(Color.PAUSED,    curses.COLOR_MAGENTA, -1)
    curses.init_pair(Color.TITLE,     curses.COLOR_GREEN,   -1)
    curses.init_pair(Color.WALL_DECOR,curses.COLOR_WHITE,   -1)

# ── Game State ─────────────────────────────────────────────────────────

class State(Enum):
    PLAYING  = "playing"
    PAUSED   = "paused"
    DEAD     = "dead"

class SnakeGame:
    def __init__(self, stdscr):
        self.scr = stdscr
        curses.curs_set(0)
        self.scr.nodelay(True)
        self.scr.timeout(INITIAL_SPEED)
        init_colors()

        # Screen dimensions
        self.max_y, self.max_x = self.scr.getmaxyx()
        # Playfield inside border (1 cell border all around)
        self.field_w = max(self.max_x - 2, 10)
        self.field_h = max(self.max_y - 4, 5)  # leave room for header + score

        self.reset()

    def reset(self):
        # Center snake
        cx, cy = self.field_w // 2, self.field_h // 2
        self.snake = deque([(cx, cy), (cx - 1, cy), (cx - 2, cy)])
        self.direction = Dir.RIGHT
        self.next_dir = Dir.RIGHT
        self.state = State.PLAYING
        self.score = 0
        self.high_score = getattr(self, 'high_score', 0)
        self.speed = INITIAL_SPEED
        self.tick = 0
        self.food = None
        self.spawn_food()

    def spawn_food(self):
        occupied = set(self.snake)
        free = [
            (x, y)
            for y in range(self.field_h)
            for x in range(self.field_w)
            if (x, y) not in occupied
        ]
        if free:
            self.food = random.choice(free)

    # ── Input ──────────────────────────────────────────────────────

    def handle_input(self):
        key = self.scr.getch()
        if key == -1:
            return

        key_map = {
            curses.KEY_UP: Dir.UP, ord('k'): Dir.UP,
            curses.KEY_DOWN: Dir.DOWN, ord('j'): Dir.DOWN,
            curses.KEY_LEFT: Dir.LEFT, ord('h'): Dir.LEFT,
            curses.KEY_RIGHT: Dir.RIGHT, ord('l'): Dir.RIGHT,
            ord('w'): Dir.UP, ord('a'): Dir.LEFT,
            ord('s'): Dir.DOWN, ord('d'): Dir.RIGHT,
        }

        if key in (ord('q'), 27):  # q or Esc
            raise SystemExit

        if key in (ord('p'), ord(' ')):
            if self.state == State.PLAYING:
                self.state = State.PAUSED
            elif self.state == State.PAUSED:
                self.state = State.PLAYING
            return

        if key in (ord('r'),) and self.state == State.DEAD:
            self.reset()
            return

        new_dir = key_map.get(key)
        if new_dir and self.state == State.PLAYING:
            if new_dir != OPPOSITE.get(self.direction):
                self.next_dir = new_dir

    # ── Update ─────────────────────────────────────────────────────

    def update(self):
        if self.state != State.PLAYING:
            return

        self.direction = self.next_dir
        self.tick += 1

        # Move head
        head_x, head_y = self.snake[0]
        dx, dy = self.direction.value
        new_head = (head_x + dx, head_y + dy)

        # Wall collision
        nx, ny = new_head
        if nx < 0 or nx >= self.field_w or ny < 0 or ny >= self.field_h:
            self.die()
            return

        # Self collision
        if new_head in set(list(self.snake)[:-1]):
            self.die()
            return

        self.snake.appendleft(new_head)

        # Eat food
        if self.food and new_head == self.food:
            self.score += 10
            self.speed = max(MIN_SPEED, INITIAL_SPEED - (self.score // 10) * SPEED_STEP)
            self.scr.timeout(self.speed)
            self.spawn_food()
        else:
            self.snake.pop()

    def die(self):
        self.state = State.DEAD
        self.high_score = max(self.high_score, self.score)

    # ── Render ─────────────────────────────────────────────────────

    def safe_addstr(self, y, x, text, attr=0):
        """Write string safely, clamping to screen bounds."""
        h, w = self.scr.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w:
            return
        max_len = w - x
        self.scr.addnstr(y, x, text, max_len, attr)

    def draw_border(self):
        h, w = self.scr.getmaxyx()
        attr = curses.color_pair(Color.BORDER)
        # Top & bottom
        for x in range(1, min(w - 1, self.field_w + 2)):
            self.safe_addstr(1, x, "─", attr)
            self.safe_addstr(self.field_h + 2, x, "─", attr)
        # Sides
        for y in range(1, self.field_h + 3):
            self.safe_addstr(y, 0, "│", attr)
            self.safe_addstr(y, min(self.field_w + 1, w - 1), "│", attr)
        # Corners
        self.safe_addstr(1, 0, "┌", attr)
        self.safe_addstr(1, min(self.field_w + 1, w - 1), "┐", attr)
        self.safe_addstr(self.field_h + 2, 0, "└", attr)
        self.safe_addstr(self.field_h + 2, min(self.field_w + 1, w - 1), "┘", attr)

    def draw_snake(self):
        snake_set = set(self.snake)
        for i, (x, y) in enumerate(self.snake):
            draw_x, draw_y = x + 1, y + 2  # offset for border + header
            if i == 0:
                # Head — special chars by direction
                head_chars = {
                    Dir.UP: "◆", Dir.DOWN: "◆",
                    Dir.LEFT: "◆", Dir.RIGHT: "◆",
                }
                self.safe_addstr(draw_y, draw_x,
                    head_chars[self.direction],
                    curses.color_pair(Color.SNAKE_H) | curses.A_BOLD)
            else:
                self.safe_addstr(draw_y, draw_x, "●",
                    curses.color_pair(Color.SNAKE_B))

    def draw_food(self):
        if not self.food:
            return
        fx, fy = self.food
        draw_x, draw_y = fx + 1, fy + 2
        # Pulsing glow every 4 ticks
        if self.tick % 8 < 4:
            self.safe_addstr(draw_y, draw_x, "✦",
                curses.color_pair(Color.FOOD_GLOW) | curses.A_BOLD)
        else:
            self.safe_addstr(draw_y, draw_x, "●",
                curses.color_pair(Color.FOOD) | curses.A_BOLD)

    def draw_header(self):
        title_attr = curses.color_pair(Color.TITLE) | curses.A_BOLD
        self.safe_addstr(0, 1, f" {TITLE} ", title_attr)

    def draw_score(self):
        score_text = f" Score: {self.score}  │  Best: {self.high_score}  │  Speed: {INITIAL_SPEED - self.speed} "
        attr = curses.color_pair(Color.SCORE)
        self.safe_addstr(self.field_h + 3, 1, score_text, attr)

    def draw_game_over(self):
        if self.state != State.DEAD:
            return
        cy = self.field_h // 2 + 2
        cx = self.field_w // 2 - 6
        msg = "╔══ GAME OVER ══╗"
        self.safe_addstr(cy, cx + 1, msg,
            curses.color_pair(Color.GAMEOVER) | curses.A_BOLD)
        self.safe_addstr(cy + 1, cx + 3, f"Score: {self.score}",
            curses.color_pair(Color.GAMEOVER))
        self.safe_addstr(cy + 2, cx + 1, "  Press R to retry  ",
            curses.color_pair(Color.GAMEOVER))

    def draw_paused(self):
        if self.state != State.PAUSED:
            return
        cy = self.field_h // 2 + 2
        cx = self.field_w // 2 - 5
        self.safe_addstr(cy, cx + 1, "╔══ PAUSED ══╗",
            curses.color_pair(Color.PAUSED) | curses.A_BOLD)
        self.safe_addstr(cy + 1, cx + 3, "P to resume",
            curses.color_pair(Color.PAUSED))

    def draw_controls(self):
        controls = " ←↑↓→ Move  │  P Pause  │  Q Quit "
        self.safe_addstr(self.field_h + 4, 1, controls,
            curses.color_pair(Color.BORDER))

    def render(self):
        self.scr.erase()
        self.draw_header()
        self.draw_border()
        self.draw_snake()
        self.draw_food()
        self.draw_score()
        self.draw_controls()
        self.draw_game_over()
        self.draw_paused()
        self.scr.refresh()

    # ── Main Loop ──────────────────────────────────────────────────

    def run(self):
        while True:
            self.handle_input()
            self.update()
            self.render()
            if self.state == State.PLAYING:
                self.scr.timeout(self.speed)


def main(stdscr):
    game = SnakeGame(stdscr)
    try:
        game.run()
    except SystemExit:
        pass


if __name__ == "__main__":
    curses.wrapper(main)

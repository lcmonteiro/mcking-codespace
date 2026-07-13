#!/usr/bin/env python3
"""
Hyperspace — Terminal Starfield with Warp Drive
================================================
Pure Python, zero dependencies.
Keys: [Space] toggle warp | [r] reset | [c] cycle colors | [q] quit
"""

import random
import math
import sys
import time
import os

# ── Terminal ────────────────────────────────────────────────
def term_size():
    try:
        return os.get_terminal_size()
    except OSError:
        return os.terminal_size((80, 24))

SIZE = term_size()
COLS = SIZE.columns
ROWS = SIZE.lines

# ── Stars ───────────────────────────────────────────────────
class Star:
    MAX_DEPTH = 64

    def __init__(self):
        self.reset()

    def reset(self):
        self.x = random.uniform(-1, 1)
        self.y = random.uniform(-1, 1)
        self.z = random.uniform(0, self.MAX_DEPTH)

    def update(self, warp):
        speed = 0.5 if not warp else 2.5
        drag = 0.98 if not warp else 0.92
        self.z -= speed
        self.z *= drag
        if self.z <= 0:
            self.reset()
            self.z = self.MAX_DEPTH

    def project(self):
        fov = COLS * 0.35
        px = int(self.x * fov / (self.z + 1) + COLS // 2)
        py = int(self.y * fov / (self.z + 1) + ROWS // 2)
        return px, py

    @property
    def brightness(self):
        b = (1 - self.z / self.MAX_DEPTH) * 2.5
        return max(0, min(1, b))

    @property
    def char(self):
        b = self.brightness
        if b < 0.25:
            return '·'
        if b < 0.5:
            return '•'
        if b < 0.75:
            return '✦'
        return '★'

# ── Palette cycling ─────────────────────────────────────────
PALETTES = [
    { 'fg': None, 'tail': 17 },        # classic white
    { 'fg': 39,  'tail': 20 },         # blue
    { 'fg': 198, 'tail': 53 },         # neon pink
    { 'fg': 82,  'tail': 22 },         # green
    { 'fg': 226, 'tail': 58 },         # gold
    { 'fg': 51,  'tail': 24 },         # cyan
    { 'fg': 201, 'tail': 55 },         # purple
    { 'fg': 208, 'tail': 52 },         # orange
]

def ansi_fg(code):
    return f'\033[38;5;{code}m'

def ansi_bg(code):
    return f'\033[48;5;{code}m'

RESET = '\033[0m'
CLEAR = '\033[2J'
HIDE  = '\033[?25l'
SHOW  = '\033[?25h'
HOME  = '\033[H'
SAVE  = '\033[?47h'
REST  = '\033[?47l'

# ── Trail buffer (for warp streaks) ─────────────────────────
def main():
    global COLS, ROWS
    SIZE = term_size()
    COLS, ROWS = SIZE.columns, SIZE.lines

    stars = [Star() for _ in range(150)]
    warp = False
    palette_idx = 0
    running = True
    frame = 0
    frame_count = 0
    fps_timer = time.time()
    fps = 0

    sys.stdout.write(SAVE + HIDE + CLEAR + HOME)
    sys.stdout.flush()

    running = True

    def cleanup():
        sys.stdout.write(SHOW + REST + '\n')
        sys.stdout.flush()

    def draw():
        nonlocal frame
        palette = PALETTES[palette_idx]
        fg_code = palette['fg']

        # Build frame buffer
        buf = [[' ' for _ in range(COLS)] for _ in range(ROWS)]

        # Update and draw each star
        for star in stars:
            star.update(warp)
            px, py = star.project()
            if 0 <= px < COLS and 0 <= py < ROWS:
                ch = star.char
                if warp and star.brightness > 0.3:
                    ch = '▸' if star.x >= 0 else '◂'
                buf[py][px] = ch

        # HUD line
        warp_label = 'WARP' if warp else 'CRUISE'
        palette_name = ['White','Blue','Pink','Green','Gold','Cyan','Purple','Orange'][palette_idx]
        hud = f'  [{warp_label}]  [{palette_name}]  [{fps}fps]  [Space]warp [c]color [r]reset [q]quit'
        hud = hud[:COLS-1]
        if fg_code:
            hud = ansi_fg(fg_code) + '\033[7m' + hud + RESET
        else:
            hud = '\033[7m' + hud + RESET

        # Render
        out = []
        for ri, row in enumerate(buf):
            line = ''.join(row).rstrip()
            if fg_code:
                out.append(ansi_fg(fg_code) + line + RESET)
            else:
                out.append(line)
        if ROWS > 1:
            out[-1] = hud  # overlay HUD on last line
        sys.stdout.write(HOME + '\n'.join(out))
        sys.stdout.flush()
        frame += 1

        # FPS counter
        frame_count += 1
        if time.time() - fps_timer >= 1:
            fps = frame_count
            frame_count = 0
            fps_timer = time.time()

    # Keyboard reader (non-blocking)
    def kb_hit():
        import select
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
        return None

    try:
        import tty, termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        tty.setcbreak(fd)

        while running:
            t_now = time.time()
            key = kb_hit()
            if key:
                if key == ' ':
                    warp = not warp
                elif key == 'r':
                    for s in stars:
                        s.reset()
                elif key == 'c':
                    palette_idx = (palette_idx + 1) % len(PALETTES)
                elif key == 'q':
                    running = False
                    cleanup()
                    return

            draw()

            # Adaptive sleep
            elapsed = time.time() - t_now
            sleep = max(0.008, 0.033 - elapsed)
            time.sleep(sleep)

    except KeyboardInterrupt:
        cleanup()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

if __name__ == '__main__':
    main()

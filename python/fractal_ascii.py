#!/usr/bin/env python3
"""
🎨 Fractal ASCII Art Generator
Interactive fractal explorer in terminal

Controls:
  WASD / Arrow Keys - Move around
  + / - - Zoom in/out
  p - Change palette (8 available)
  f - Change fractal type (Mandelbrot, Julia, Burning Ship, etc.)
  q - Quit
  ? - Show this help

Author: Mcking (AI Assistant)
Date: 2026-07-03
"""

import sys
import math
import time
import os
import msvcrt
from typing import Tuple, Callable, List

# =============================================================================
# UTF-8 Setup for Windows Terminal
# =============================================================================
if sys.platform == "win32":
    try:
        import sys
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

# =============================================================================
# Fractal Definitions
# =============================================================================

def mandelbrot(c: complex, max_iter: int) -> Tuple[int, float]:
    """Calculate Mandelbrot iteration count with smooth coloring."""
    z = 0j
    for n in range(max_iter):
        if abs(z) > 2.0:
            # Smooth coloring
            log_zn = math.log(abs(z)) / 2.0
            nu = math.log(log_zn) / math.log(2) if log_zn > 0 else 0.0
            smooth = n + 1 - nu
            return n, smooth / max_iter
        z = z * z + c
    return max_iter, 1.0

def julia(z: complex, c: complex, max_iter: int) -> Tuple[int, float]:
    """Calculate Julia set iteration count."""
    for n in range(max_iter):
        if abs(z) > 2.0:
            log_zn = math.log(abs(z)) / 2.0
            nu = math.log(log_zn) / math.log(2) if log_zn > 0 else 0.0
            smooth = n + 1 - nu
            return n, smooth / max_iter
        z = z * z + c
    return max_iter, 1.0

def burning_ship(c: complex, max_iter: int) -> Tuple[int, float]:
    """Burning Ship fractal - uses absolute value of real and imaginary parts."""
    z = 0j
    for n in range(max_iter):
        if abs(z) > 2.0:
            log_zn = math.log(abs(z)) / 2.0
            nu = math.log(log_zn) / math.log(2) if log_zn > 0 else 0.0
            smooth = n + 1 - nu
            return n, smooth / max_iter
        z = (complex(abs(z.real), abs(z.imag))) ** 2 + c
    return max_iter, 1.0

def multicorn(c: complex, max_iter: int, power: int = 3) -> Tuple[int, float]:
    """Multicorn fractal - z^n + c."""
    z = 0j
    for n in range(max_iter):
        if abs(z) > 2.0:
            log_zn = math.log(abs(z)) / 2.0
            nu = math.log(log_zn) / math.log(2) if log_zn > 0 else 0.0
            smooth = n + 1 - nu
            return n, smooth / max_iter
        z = z ** power + c
    return max_iter, 1.0

# =============================================================================
# Palette Definitions
# =============================================================================

def palette_fire(t: float) -> Tuple[int, int, int]:
    """Fire palette: black -> red -> yellow -> white."""
    if t < 0.25:
        return (0, 0, 0)
    elif t < 0.5:
        r = int(255 * (t - 0.25) / 0.25)
        return (r, 0, 0)
    elif t < 0.75:
        r = 255
        g = int(255 * (t - 0.5) / 0.25)
        return (r, g, 0)
    else:
        r = 255
        g = 255
        b = int(255 * (t - 0.75) / 0.25)
        return (r, g, b)

def palette_ocean(t: float) -> Tuple[int, int, int]:
    """Ocean palette: deep blue -> cyan -> green -> yellow."""
    if t < 0.33:
        b = int(255 * (0.33 - t) / 0.33)
        g = int(255 * t / 0.33)
        return (0, g, b + 100)
    elif t < 0.66:
        g = 255
        b = int(255 * (0.66 - t) / 0.33)
        r = int(255 * (t - 0.33) / 0.33)
        return (r, g, b)
    else:
        r = 255
        g = int(255 * (1.0 - t) / 0.33)
        return (r, g, 0)

def palette_purple(t: float) -> Tuple[int, int, int]:
    """Purple palette."""
    r = int(128 + 127 * math.sin(t * math.pi))
    b = int(128 + 127 * math.cos(t * math.pi))
    g = int(128 + 127 * math.sin(t * math.pi * 2))
    return (r, g, b)

def palette_grayscale(t: float) -> Tuple[int, int, int]:
    """Simple grayscale."""
    v = int(255 * t)
    return (v, v, v)

def palette_rainbow(t: float) -> Tuple[int, int, int]:
    """Rainbow palette."""
    h = t * 5.0
    i = int(h)
    f = h - i
    q = 1.0 - f
    
    if i % 5 == 0:
        r, g, b = 1.0, f, 0.0
    elif i % 5 == 1:
        r, g, b = q, 1.0, 0.0
    elif i % 5 == 2:
        r, g, b = 0.0, 1.0, f
    elif i % 5 == 3:
        r, g, b = 0.0, q, 1.0
    else:
        r, g, b = f, 0.0, 1.0
    
    return (int(r * 255), int(g * 255), int(b * 255))

def palette_vintage(t: float) -> Tuple[int, int, int]:
    """Vintage/retro palette."""
    r = int(180 + 75 * math.sin(t * math.pi * 3))
    g = int(150 + 75 * math.cos(t * math.pi * 2))
    b = int(120 + 75 * math.sin(t * math.pi))
    return (r, g, b)

def palette_binary(t: float) -> Tuple[int, int, int]:
    """Binary: black or white based on threshold."""
    return (255, 255, 255) if t > 0.5 else (0, 0, 0)

def palette_neon(t: float) -> Tuple[int, int, int]:
    """Neon palette."""
    r = int(255 * (0.5 + 0.5 * math.sin(t * math.pi * 2)))
    g = int(255 * (0.5 + 0.5 * math.sin(t * math.pi * 3)))
    b = int(255 * (0.5 + 0.5 * math.cos(t * math.pi * 4)))
    return (r, g, b)

PALETTES = [
    ("Fire", palette_fire),
    ("Ocean", palette_ocean),
    ("Purple", palette_purple),
    ("Grayscale", palette_grayscale),
    ("Rainbow", palette_rainbow),
    ("Vintage", palette_vintage),
    ("Binary", palette_binary),
    ("Neon", palette_neon),
]

# =============================================================================
# Fractal Types
# =============================================================================

FRACTAL_TYPES = [
    ("Mandelbrot", lambda c, mi: mandelbrot(c, mi)),
    ("Julia", lambda c, mi: julia(c, complex(-0.7, 0.27), mi)),
    ("Burning Ship", lambda c, mi: burning_ship(c, mi)),
    ("Multicorn (z^3)", lambda c, mi: multicorn(c, mi, 3)),
    ("Multicorn (z^4)", lambda c, mi: multicorn(c, mi, 4)),
    ("Multicorn (z^5)", lambda c, mi: multicorn(c, mi, 5)),
]

# =============================================================================
# ASCII Character Density Map
# =============================================================================

# Characters ordered from lowest to highest density
ASCII_CHARS = " .:-=+*#%@"
# ASCII_CHARS = " .,-~:;=!*#$@"
# ASCII_CHARS = " .°oO0#"

# =============================================================================
# Terminal Utilities
# =============================================================================

def clear_screen():
    """Clear terminal screen."""
    if sys.platform == "win32":
        os.system('cls')
    else:
        os.system('clear')

def get_terminal_size() -> Tuple[int, int]:
    """Get terminal width and height."""
    if sys.platform == "win32":
        import ctypes
        h = ctypes.windll.kernel32.GetStdHandle(-12)
        csbi = ctypes.create_string_buffer(22)
        res = ctypes.windll.kernel32.GetConsoleScreenBufferInfo(h, csbi)
        if res:
            import struct
            (_, _, _, _, _, left, top, right, bottom, _, _) = struct.unpack("hhhhhhhhhhh", csbi.raw)
            width = right - left + 1
            height = bottom - top + 1
            return width, height
    else:
        try:
            import fcntl, termios, struct
            h, w = struct.unpack('HH', fcntl.ioctl(0, termios.TIOCGWINSZ, struct.pack('HH', 0, 0)))
            return w, h
        except:
            pass
    # Fallback
    return 80, 24

def rgb_to_ansi(r: int, g: int, b: int, bg: bool = False) -> str:
    """Convert RGB to ANSI escape code."""
    return f"\033[{'48' if bg else '38'};2;{r};{g};{b}m"

def ansi_reset() -> str:
    """ANSI reset code."""
    return "\033[0m"

# =============================================================================
# Fractal Renderer
# =============================================================================

class FractalRenderer:
    def __init__(self, width: int = 80, height: int = 24):
        self.width = width
        self.height = height
        self.center_x = -0.5
        self.center_y = 0.0
        self.zoom = 1.0
        self.max_iter = 64
        self.palette_idx = 0
        self.fractal_idx = 0
        self.julia_c = complex(-0.7, 0.27)
        
    def get_palette_func(self):
        return PALETTES[self.palette_idx][1]
    
    def get_fractal_func(self):
        return FRACTAL_TYPES[self.fractal_idx][1]
    
    def pixel_to_complex(self, x: int, y: int) -> complex:
        """Convert pixel coordinates to complex plane coordinates."""
        aspect_ratio = self.width / self.height
        
        # Calculate the range in complex plane
        range_x = 3.5 / self.zoom / aspect_ratio
        range_y = 3.5 / self.zoom
        
        real = self.center_x - range_x + (x / self.width) * (2 * range_x)
        imag = self.center_y - range_y + (y / self.height) * (2 * range_y)
        
        return complex(real, imag)
    
    def render_row(self, y: int, use_color: bool = True) -> str:
        """Render a single row of the fractal."""
        row = []
        palette_func = self.get_palette_func()
        fractal_func = self.get_fractal_func()
        
        for x in range(self.width):
            c = self.pixel_to_complex(x, y)
            iter_count, smooth = fractal_func(c, self.max_iter)
            
            if iter_count == self.max_iter:
                # Inside the set - black
                if use_color:
                    row.append(f"{rgb_to_ansi(0, 0, 0)}  {ansi_reset()}")
                else:
                    row.append(" ")
            else:
                # Outside the set - colored based on iteration count
                t = smooth
                r, g, b = palette_func(t)
                
                if use_color:
                    # Map to ASCII character based on smooth value
                    char_idx = int(smooth * (len(ASCII_CHARS) - 1))
                    char = ASCII_CHARS[char_idx]
                    row.append(f"{rgb_to_ansi(r, g, b)}{char}{ansi_reset()}")
                else:
                    char_idx = int(smooth * (len(ASCII_CHARS) - 1))
                    char = ASCII_CHARS[char_idx]
                    row.append(char)
        
        return "".join(row)
    
    def render_full(self, use_color: bool = True) -> List[str]:
        """Render the complete fractal."""
        lines = []
        for y in range(self.height):
            lines.append(self.render_row(y, use_color))
        return lines
    
    def move(self, dx: float, dy: float):
        """Move the view."""
        self.center_x += dx / self.zoom
        self.center_y += dy / self.zoom
    
    def zoom_in(self, factor: float = 1.5):
        """Zoom in."""
        self.zoom *= factor
        self.max_iter = min(self.max_iter + 32, 512)
    
    def zoom_out(self, factor: float = 1.5):
        """Zoom out."""
        self.zoom /= factor
        self.max_iter = max(self.max_iter - 32, 16)
    
    def next_palette(self):
        """Cycle to next palette."""
        self.palette_idx = (self.palette_idx + 1) % len(PALETTES)
    
    def next_fractal(self):
        """Cycle to next fractal type."""
        self.fractal_idx = (self.fractal_idx + 1) % len(FRACTAL_TYPES)
        # Reset zoom and position for new fractal
        self.center_x = -0.5
        self.center_y = 0.0
        self.zoom = 1.0
        self.max_iter = 64

# =============================================================================
# Main Application
# =============================================================================

def show_help():
    """Display help information."""
    clear_screen()
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                  🎨 FRACTAL ASCII ART EXPLORER                        ║
║                          by Mcking 🤖                                 ║
╠══════════════════════════════════════════════════════════════════════╣
║ CONTROLS:                                                        ║
║   WASD / Arrow Keys   - Move around the fractal                     ║
║   + / =              - Zoom in                                     ║
║   - / _              - Zoom out                                    ║
║   p                 - Change palette (8 available)                  ║
║   f                 - Change fractal type                          ║
║   h / ?             - Show this help                               ║
║   q / ESC           - Quit                                         ║
║                                                                       ║
║ FRACTAL TYPES:                                                    ║
║   1. Mandelbrot       2. Julia        3. Burning Ship               ║
║   4. Multicorn z^3   5. Multicorn z^4  6. Multicorn z^5            ║
║                                                                       ║
║ PALETTES:                                                         ║
║   Fire, Ocean, Purple, Grayscale, Rainbow, Vintage, Binary, Neon  ║
║                                                                       ║
╚══════════════════════════════════════════════════════════════════════╝
    """)
    input("Press Enter to continue...")

def main():
    """Main entry point."""
    print("🎨 Initializing Fractal ASCII Explorer...")
    
    # Get terminal size
    term_width, term_height = get_terminal_size()
    
    # Adjust for status bar
    render_height = term_height - 2
    if render_height < 10:
        render_height = 24
    
    renderer = FractalRenderer(width=term_width, height=render_height)
    
    # Detect if terminal supports ANSI colors
    use_color = True
    if sys.platform == "win32":
        try:
            import os
            os.system("")  # Enable ANSI on Windows 10+
        except:
            use_color = False
    
    print("✅ Ready! Press '?' for help, 'q' to quit")
    time.sleep(1)
    
    try:
        while True:
            clear_screen()
            
            # Render fractal
            lines = renderer.render_full(use_color=use_color)
            for line in lines:
                print(line)
            
            # Status bar
            fractal_name = FRACTAL_TYPES[renderer.fractal_idx][0]
            palette_name = PALETTES[renderer.palette_idx][0]
            status = f"[{fractal_name}] | Palette: {palette_name} | Zoom: {renderer.zoom:.2f}x | Iter: {renderer.max_iter} | Pos: ({renderer.center_x:.4f}, {renderer.center_y:.4f})"
            
            # Truncate status if too long
            if len(status) > term_width:
                status = status[:term_width-3] + "..."
            
            print()
            print(status)
            print("Controls: WASD/↑↓←→ move | +- zoom | p palette | f fractal | ? help | q quit")
            
            # Check for input without blocking
            if msvcrt.kbhit():
                key = msvcrt.getch()
                
                # Handle arrow keys and special keys
                if key == b'\xe0':
                    # Arrow key or function key
                    key2 = msvcrt.getch()
                    if key2 == b'H':  # Up arrow
                        renderer.move(0, -0.1)
                    elif key2 == b'P':  # Down arrow
                        renderer.move(0, 0.1)
                    elif key2 == b'K':  # Left arrow
                        renderer.move(-0.1, 0)
                    elif key2 == b'M':  # Right arrow
                        renderer.move(0.1, 0)
                elif key == b'w' or key == b'W':
                    renderer.move(0, -0.1)
                elif key == b's' or key == b'S':
                    renderer.move(0, 0.1)
                elif key == b'a' or key == b'A':
                    renderer.move(-0.1, 0)
                elif key == b'd' or key == b'D':
                    renderer.move(0.1, 0)
                elif key == b'+' or key == b'=':
                    renderer.zoom_in()
                elif key == b'-' or key == b'_':
                    renderer.zoom_out()
                elif key == b'p' or key == b'P':
                    renderer.next_palette()
                elif key == b'f' or key == b'F':
                    renderer.next_fractal()
                elif key == b'h' or key == b'H' or key == b'?':
                    show_help()
                elif key == b'q' or key == b'Q' or key == b'\x1b':  # ESC
                    clear_screen()
                    print("👋 Thanks for exploring fractals!")
                    break
                elif key == b' ':
                    # Space - toggle color
                    use_color = not use_color
                    time.sleep(0.1)
                
                # Small delay to prevent rapid key repeats
                time.sleep(0.05)
            else:
                # No input - small delay
                time.sleep(0.05)
    
    except KeyboardInterrupt:
        clear_screen()
        print("👋 Interrupted. Thanks for exploring!")
    except Exception as e:
        clear_screen()
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

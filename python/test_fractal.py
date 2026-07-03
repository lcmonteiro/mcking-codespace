#!/usr/bin/env python3
"""
Quick test for fractal_ascii.py
"""
import sys
sys.path.insert(0, '.')

from fractal_ascii import FractalRenderer, PALETTES, FRACTAL_TYPES

def test_renderer():
    print("Testing FractalRenderer...")
    
    renderer = FractalRenderer(width=40, height=20)
    
    print(f"Initial center: ({renderer.center_x}, {renderer.center_y})")
    print(f"Initial zoom: {renderer.zoom}")
    print(f"Max iterations: {renderer.max_iter}")
    
    # Test rendering
    lines = renderer.render_full(use_color=False)
    print(f"\nRendered {len(lines)} lines")
    print(f"First line length: {len(lines[0])}")
    
    # Print a small sample
    print("\nSample (ASCII only):")
    for i, line in enumerate(lines[:5]):
        print(line[:40])
    
    # Test palette cycling
    print(f"\nCurrent palette: {PALETTES[renderer.palette_idx][0]}")
    renderer.next_palette()
    print(f"Next palette: {PALETTES[renderer.palette_idx][0]}")
    
    # Test fractal cycling
    print(f"\nCurrent fractal: {FRACTAL_TYPES[renderer.fractal_idx][0]}")
    renderer.next_fractal()
    print(f"Next fractal: {FRACTAL_TYPES[renderer.fractal_idx][0]}")
    
    # Test movement
    renderer.move(0.1, 0.1)
    print(f"\nAfter move: ({renderer.center_x:.4f}, {renderer.center_y:.4f})")
    
    # Test zoom
    renderer.zoom_in()
    print(f"After zoom in: {renderer.zoom:.4f}")
    renderer.zoom_out()
    print(f"After zoom out: {renderer.zoom:.4f}")
    
    print("\n✅ All tests passed!")

if __name__ == "__main__":
    test_renderer()

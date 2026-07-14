# Fluid Simulation — Agent Context

## What

Web-based 2D fluid dynamics simulator using the Jos Stam stable fluids method.
Renders dye advection through a velocity field with vorticity confinement for
realistic swirling motion.

## Method

- **Solver**: Gauss-Seidel relaxation for diffusion + projection
- **Advection**: Semi-Lagrangian backtracing with bilinear interpolation
- **Projection**: Hodge decomposition for divergence-free flow → mass conservation
- **Vorticity confinement**: Small-scale vortex detail preservation
- **Implementation**: CPU-side with `Float32Array` on a fixed RES×RES grid
  (default RES=160), upscaled to canvas via pixel buffer

## Controls

- Click + drag to paint dye + push velocity
- Scroll wheel to adjust brush size
- Mode buttons: Rainbow, Fire, Smoke, Ink
- Sliders for viscosity, diffusion, brush, strength
- "Boom" button for particle explosion effect
- Keyboard: Space=pause, C=clear, 1-4=modes

## Implementation Details

- Single `index.html` — no dependencies
- Grid uses Stam's N+2 boundary convention (ghost cells)
- Timestep: dt = 0.1 (stable for most viscosity values)
- 20 Gauss-Seidel iterations per diffusion solve
- 150 density projection steps per frame

## Status

2026-07-14 — Initial implementation:
- Stable fluid solver with velocity advection + diffusion
- Dye transport in RGB
- Vorticity confinement for small-scale turbulence
- 4 visual modes: Rainbow, Fire (rising heat), Smoke (rising puffs), Ink
- Mouse/touch input with smooth interpolation
- Resize handling
- "Boom" explosion effect
- Performance: ~20-30 FPS at RES=160 on mid-range hardware

# Particle Life — Agent Context

## What

Web-based Particle Life simulation — emergent artificial life.
Colored particles of different "species" attract/repel each other via a force matrix,
creating organic, flowing patterns that look alive.

## Controls

- Click + drag to add a burst of particles
- Sliders adjust speed, radius, force intensity
- Preset buttons swap interaction matrices
- Toggle glow/bloom effect

## Implementation

- Single `index.html` — no dependencies
- Canvas 2D with offscreen buffer for trail fade
- Force calculation uses spatial hashing (grid) for O(n) instead of O(n²)
- Color blending via composite operations

## Status

2026-07-11 — Initial implementation:
- 4 particle species (red, cyan, green, magenta)
- 4x4 force matrix with attractive/repulsive values
- Spatial grid for efficient neighbor lookup
- 6 presets: Slime, Cells, Vortex, Spiral, Chaotic, Balanced
- Mouse interaction (spawn + attract/repel)
- Glow toggle, reset, speed/radius controls

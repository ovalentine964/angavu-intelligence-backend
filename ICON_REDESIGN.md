# Angavu Intelligence — Icon Redesign

## Problem

The previous icon used 18 small, indistinguishable nodes with thin 1px connections. The Africa continent shape was implied by node positions but never actually drawn — making it unreadable at small sizes and unclear even at large sizes.

## Solution: "Africa Neural Network"

**One bold continent shape + clear city nodes + thick gold connections.**

### Design Principles Applied

1. **Africa as primary element** — Bold filled SVG path with 3.5px stroke, instantly recognizable silhouette
2. **Fewer, larger nodes** — 8 city nodes (was 18), each 7-8px radius, clearly visible at all sizes
3. **Thick connections** — 2.5px lines from HQ hub, 1.8px regional lines (was 1px)
4. **Kenya HQ stands out** — 13px node (2x larger), bright gold #F0C060, white ring, radial glow
5. **High contrast** — Dark blue #0F2D42/#1B4965 background, gold #E8A838 elements, white text
6. **Progressive simplification** — Each smaller size removes detail while preserving the "Africa + network" concept

### City Nodes (8)

| City | Role | Position |
|------|------|----------|
| **Nairobi** 🇰🇪 | **HQ — 2x larger, gold glow** | East Africa |
| Cairo | North | Northeast |
| Lagos | West Africa | West |
| Casablanca | Northwest | Northwest |
| Addis Ababa | Horn | East |
| Dar es Salaam | East Coast | Southeast |
| Kinshasa | Central | Central-West |
| Johannesburg | Southern | South |
| Cape Town | Southern tip | South |

### Files Generated

| File | Size | Purpose |
|------|------|---------|
| `assets/angavu-icon-512.svg` | 512×512 | Full detail icon |
| `assets/angavu-icon-192.svg` | 192×192 | App icon / PWA |
| `assets/angavu-icon-48.svg` | 48×48 | Favicon-size, must read as "Africa network" |
| `assets/angavu-logo-192.svg` | 192×192 | Logo variant with text |
| `assets/angavu-logo-48.svg` | 48×48 | Small logo variant |
| `assets/favicon.svg` | 32×32 | Browser favicon — ultra minimal |
| `assets/angavu-banner.svg` | 1200×400 | GitHub hero banner |
| `docs/logo-banner.svg` | 1200×320 | README banner (compact) |
| `docs/logo-icon.svg` | 128×128 | README inline icon |

### Color Palette

- **Background**: `#0F2D42` → `#1B4965` (dark blue gradient)
- **Africa stroke**: `#E8A838` at 3.5px (bold gold)
- **Africa fill**: `#E8A838` at 8% opacity (subtle gold wash)
- **Connection lines**: `#E8A838` at 45-50% opacity
- **City nodes**: `#E8A838` (solid gold)
- **Nairobi HQ**: `#F0C060` with white 2.5px ring + radial glow
- **Text**: `#FFFFFF` (white), tagline in `#E8A838`

### Size Degradation Strategy

- **512px**: Full Africa path, Madagascar, 8 nodes, all connections, text labels
- **192px**: Simplified Africa path, 8 nodes, fewer connections, text
- **48px**: Ultra-simplified Africa blob, 8 nodes, hub connections only
- **32px (favicon)**: Minimal Africa shape, 6 nodes, Nairobi HQ prominent

### The 48px Test

> Can you tell this is Africa with connected nodes at 48px?
> **Yes** — bold continent outline + gold nodes + Nairobi HQ glow are unmistakable even at favicon size.

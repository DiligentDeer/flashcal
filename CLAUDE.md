# CLAUDE.md

## Overview

Quick Formula Calculator — a reactive marimo notebook for computing common DeFi formulas.
Three tabs: Leveraged Yield, Shock to LTV, and Incentive Dilution.

This is a **pure computation** tool with no external API calls or blockchain connections.

## Package Manager

**Always use `uv`** — never pip.

```bash
uv sync                              # Install dependencies
uv run marimo edit notebook.py       # Edit notebook (interactive)
uv run marimo run notebook.py        # Run as read-only app
```

## File Structure

```
quick_formula_marimo/
├── notebook.py          # Single marimo notebook (all logic + UI)
├── pyproject.toml       # Dependencies (no build-system, notebook-only project)
├── .python-version      # 3.11
├── .github/
│   └── workflows/
│       └── deploy.yml   # WASM export + GitHub Pages deploy
```

## Architecture

Single marimo notebook with ~16 cells organized into:
- **Shared**: imports, constants, `apply_style()` chart helper
- **Tab 1 (Leveraged Yield)**: inputs, computation, heatmap, line chart, assembly
- **Tab 2 (Shock to LTV)**: inputs, mode-based computation, assembly
- **Tab 3 (Incentive Dilution)**: inputs, solve-for computation, heatmap, assembly
- **Main**: title + `mo.ui.tabs()` with `lazy=True`

Cell dependency graph is linear within each tab, tabs are independent of each other.

## Key Formulas

### Leveraged Yield
```
Leverage = 1 / (1 - LTV)
LeveragedYield = (SupplyRate - BorrowRate * LTV) / (1 - LTV)
Heatmap inverse: LTV = (TargetYield - SupplyRate) / (TargetYield - BorrowRate)
```

### Shock to LTV
```
CollateralShock = (LTV1 - LTV0) / LTV1
DebtSpike = (LTV1 - LTV0) / LTV0
Reverse: LTV1 = LTV0 / (1 - shock)  or  LTV1 = LTV0 * (1 + spike)
```

### Incentive Dilution
```
Budget = Rate * TVL * Duration / 365
```
Same invariant as `standalone-projects/incentive_modeling/src/incentives_computation.py`.

## Deployment

WASM export to GitHub Pages:
```bash
uv run marimo export html-wasm notebook.py -o _site/ --mode run
```
GitHub Actions workflow in `.github/workflows/deploy.yml` automates this on push to main.

## Marimo Conventions

- Each global variable defined in exactly one cell
- `_` prefix for cell-local variables (not tracked by reactive graph)
- `debounce=True` on number inputs to prevent recompute while typing
- `lazy=True` on tabs to defer rendering of inactive tabs
- PEP 723 inline metadata at top of notebook.py for WASM dependency resolution

# Quick Formula Calculator

Reactive marimo notebook for computing common DeFi formulas: leveraged yield, price shocks to LTV, and incentive dilution.

## Quick Start

```bash
uv sync
uv run marimo edit notebook.py    # Interactive editing
uv run marimo run notebook.py     # Read-only app mode
```

## Tabs

### 1. Leveraged Yield

Compute leveraged yield from supply rate, borrow rate, and LTV. Includes:
- **Heatmap**: LTV required to achieve a target yield across supply/borrow rate combinations
- **Line chart**: Leveraged yield vs spread for different LTV levels

### 2. Shock to LTV

Calculate how collateral price drops or debt price spikes affect LTV. Three modes:
- Given LTV before/after, compute the shock percentages
- Given LTV before + collateral shock, compute LTV after
- Given LTV before + debt spike, compute LTV after

### 3. Incentive Dilution

Budget/Rate/TVL calculator based on `Budget = Rate * TVL * Duration / 365`. Solve for any one variable given the other two. Includes a heatmap of rate vs budget and TVL.

## Deployment

Exports to static WASM for GitHub Pages — see `.github/workflows/deploy.yml`.

```bash
uv run marimo export html-wasm notebook.py -o _site/ --mode run
```

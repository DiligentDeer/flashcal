# CLAUDE.md

## Overview

Quick Formula Calculator — a reactive marimo notebook for computing common DeFi formulas.
Eight tabs: Leveraged Yield, Shock to LTV, Incentive Dilution, Euler Liquidation,
Loan Liquidation Risk, Adaptive Curve IRM, IRM Analyzer, and Campaign Simulation.

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

Single marimo notebook with ~41 cells organized into:
- **Shared**: imports, constants, `apply_style()` chart helper
- **Math Helpers**: euler_math, loan_risk_math, adaptive_irm_math, irm_analyzer_math, campaign_math, csv_helper
- **Tab 1 (Leveraged Yield)**: inputs, computation, heatmap, assembly
- **Tab 2 (Shock to LTV)**: inputs, mode-based computation, assembly
- **Tab 3 (Incentive Dilution)**: inputs, solve-for computation, heatmap, assembly
- **Tab 4 (Euler Liquidation)**: inputs (3 curve slots via `mo.ui.dictionary`), compute, chart, assembly
- **Tab 5 (Loan Liquidation Risk)**: inputs (HF/LTV mode), compute, area chart, assembly
- **Tab 6 (Adaptive Curve IRM)**: inputs, time-step simulation, dual charts, assembly
- **Tab 7 (IRM Analyzer)**: inputs (5 curve slots × 4 points), compute with optional supply/derivatives, chart, assembly
- **Tab 8 (Campaign Simulation)**: inputs (3 campaign slots), simulate 3 strategies, dual charts, assembly
- **Main**: title + `mo.ui.tabs()` with `lazy=True`

Cell dependency graph is linear within each tab, tabs are independent of each other.
Multi-curve tabs (4, 7, 8) use `mo.ui.dictionary()` for grouping curve inputs and `mo.accordion()` for layout.

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

### Euler Liquidation (from tool_library page1)
```
Max Safe LTV: quadratic solver where buffer = raw_bonus
HF = LLTV / LTV, Buffer = 1 - LTV
Bad Debt = max(0, raw_bonus - buffer) * collateral_value
```

### Loan Liquidation Risk (from tool_library page2)
```
(1 + debt_change) / (1 - collateral_change) = ratio
HF mode: ratio = HF_initial / HF_final
LTV mode: ratio = LTV_final / LTV_initial
```

### Adaptive Curve IRM (from tool_library page3)
```
Morpho adaptive kink rate: new_rate = old_rate * exp(speed * error * time)
Borrow rate from kink: rate = ((C-1)*err + 1) * rate_at_target (above target)
Constants: target=90%, steepness=4, speed=50/year
```

### IRM Analyzer (from tool_library page4)
```
Standard supply: utilization * borrow_rate * (1 - reserve_factor)
Kamino supply: APY->APR, subtract host fee, apply take rate, APR->APY (Decimal precision)
```

### Campaign Simulation (from tool_library page5b)
```
Variable Rate: budget_per_epoch / capacity * annualization
Fixed Rate: maintain target_rate, budget may exhaust
Capped Rate (Merkl): min(needed, available_per_epoch), stretches budget
```

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

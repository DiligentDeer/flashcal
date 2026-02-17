# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo>=0.10",
#     "plotly>=5.0",
#     "numpy>=1.24",
# ]
# ///

import marimo

__generated_with = "0.19.11"
app = marimo.App(width="medium")


# --- Cell 0: Imports and constants ---
@app.cell
def imports():
    import marimo as mo
    import numpy as np
    import plotly.express as px
    import plotly.graph_objects as go

    CHART_BG = "#ffffff"
    GRID_COLOR = "#e0e0e0"
    return CHART_BG, GRID_COLOR, go, mo, np, px


# --- Cell 1: Chart styling helper ---
@app.cell
def styling(CHART_BG, GRID_COLOR, go):
    def apply_style(fig: go.Figure, height: int = 500) -> go.Figure:
        fig.update_layout(
            plot_bgcolor=CHART_BG,
            paper_bgcolor=CHART_BG,
            height=height,
            margin=dict(l=60, r=60, t=60, b=50),
            font=dict(family="monospace", size=12),
        )
        fig.update_xaxes(showgrid=True, gridcolor=GRID_COLOR)
        fig.update_yaxes(showgrid=True, gridcolor=GRID_COLOR)
        return fig

    return (apply_style,)


# =====================================================================
# TAB 1: LEVERAGED YIELD
# =====================================================================


# --- Cell 2: Tab 1 inputs ---
@app.cell
def tab1_inputs(mo):
    supply_rate_input = mo.ui.number(
        start=0.0, stop=50.0, step=0.1, value=5.0,
        debounce=True, label="Supply Rate (%)",
    )
    borrow_rate_input = mo.ui.number(
        start=0.0, stop=50.0, step=0.1, value=3.0,
        debounce=True, label="Borrow Rate (%)",
    )
    ltv_input = mo.ui.number(
        start=0.0, stop=99.0, step=1.0, value=80.0,
        debounce=True, label="LTV (%)",
    )
    return borrow_rate_input, ltv_input, supply_rate_input


# --- Cell 3: Tab 1 computation ---
@app.cell
def tab1_compute(borrow_rate_input, ltv_input, supply_rate_input):
    _sr = supply_rate_input.value
    _br = borrow_rate_input.value
    _ltv = ltv_input.value / 100.0  # Convert from % to decimal

    if _ltv is not None and 0.0 <= _ltv < 1.0:
        leverage_result = 1.0 / (1.0 - _ltv)
        leveraged_yield_result = (_sr - _br * _ltv) / (1.0 - _ltv)
    else:
        leverage_result = float("inf")
        leveraged_yield_result = float("inf")
    return leverage_result, leveraged_yield_result


# --- Cell 4: Tab 1 heatmap target input ---
@app.cell
def tab1_heatmap_input(mo):
    target_yield_input = mo.ui.number(
        start=-50.0, stop=100.0, step=0.5, value=10.0,
        debounce=True, label="Target Leveraged Yield (%)",
    )
    return (target_yield_input,)


# --- Cell 5: Tab 1 heatmap ---
@app.cell
def tab1_heatmap(apply_style, np, px, target_yield_input):
    _target = target_yield_input.value
    _borrow_rates = np.linspace(0.0, 15.0, 61)
    _supply_rates = np.linspace(0.0, 15.0, 61)
    _br_grid, _sr_grid = np.meshgrid(_borrow_rates, _supply_rates)

    # LTV = (TargetYield - SupplyRate) / (TargetYield - BorrowRate)
    _denom = _target - _br_grid
    with np.errstate(divide="ignore", invalid="ignore"):
        _raw = (_target - _sr_grid) / _denom
    _ltv_grid = np.where(np.abs(_denom) > 1e-9, _raw, np.nan)
    # Mask invalid LTV (outside [0, 1])
    _ltv_grid = np.where(
        (_ltv_grid >= 0) & (_ltv_grid <= 1), _ltv_grid, np.nan
    )
    # Convert to % for display
    _ltv_grid_pct = _ltv_grid * 100.0

    _fig = px.imshow(
        _ltv_grid_pct,
        x=np.round(_borrow_rates, 2),
        y=np.round(_supply_rates, 2),
        origin="lower",
        labels={"x": "Borrow Rate (%)", "y": "Supply Rate (%)", "color": "LTV (%)"},
        color_continuous_scale="Viridis",
        aspect="auto",
        zmin=40,
        zmax=100,
        title=f"LTV Required for {_target:.1f}% Leveraged Yield",
    )
    heatmap_fig_tab1 = apply_style(_fig, height=520)
    return (heatmap_fig_tab1,)


# --- Cell 7: Tab 1 assembly ---
@app.cell
def tab1_assembly(
    heatmap_fig_tab1,
    leverage_result,
    leveraged_yield_result,
    ltv_input,
    mo,
    supply_rate_input,
    borrow_rate_input,
    target_yield_input,
):
    _lev_str = f"{leverage_result:.2f}x" if leverage_result != float("inf") else "N/A"
    _yield_str = (
        f"{leveraged_yield_result:.2f}%"
        if leveraged_yield_result != float("inf")
        else "N/A"
    )

    tab1_content = mo.vstack([
        mo.md("### Calculator"),
        mo.md(
            "`Leverage = 1/(1-LTV)` · "
            "`Leveraged Yield = (SupplyRate - BorrowRate * LTV) / (1-LTV)`"
        ),
        mo.hstack(
            [supply_rate_input, borrow_rate_input, ltv_input],
            justify="start",
            gap=1.5,
        ),
        mo.md(f"**Leverage:** {_lev_str} | **Leveraged Yield:** {_yield_str}"),
        mo.md("---"),
        mo.md("### Heatmap: LTV Required for Target Yield"),
        mo.md("Given a target leveraged yield, what LTV is needed for each (supply, borrow) pair?"),
        target_yield_input,
        mo.as_html(heatmap_fig_tab1),
    ])
    return (tab1_content,)


# =====================================================================
# TAB 2: SHOCK TO LTV
# =====================================================================


# --- Cell 8: Tab 2 inputs ---
@app.cell
def tab2_inputs(mo):
    shock_mode = mo.ui.dropdown(
        options={
            "LTV0 + LTV1 -> Shocks": "ltv_to_shock",
            "LTV0 + Collateral Shock -> LTV1": "collateral_shock",
            "LTV0 + Debt Spike -> LTV1": "debt_spike",
        },
        value="LTV0 + LTV1 -> Shocks",
        label="Mode",
    )
    ltv0_input = mo.ui.number(
        start=1.0, stop=99.0, step=1.0, value=70.0,
        debounce=True, label="LTV Before (%)",
    )
    ltv1_input = mo.ui.number(
        start=1.0, stop=99.0, step=1.0, value=85.0,
        debounce=True, label="LTV After (%)",
    )
    shock_pct_input = mo.ui.number(
        start=-99.0, stop=500.0, step=1.0, value=20.0,
        debounce=True, label="Shock / Spike (%)",
    )
    return ltv0_input, ltv1_input, shock_mode, shock_pct_input


# --- Cell 9: Tab 2 computation ---
@app.cell
def tab2_compute(ltv0_input, ltv1_input, shock_mode, shock_pct_input):
    _mode = shock_mode.value
    _ltv0 = ltv0_input.value / 100.0  # Convert from % to decimal
    _ltv1 = ltv1_input.value / 100.0  # Convert from % to decimal
    _shock_pct = shock_pct_input.value / 100.0  # Convert to decimal

    shock_results = {}

    if _mode == "ltv_to_shock":
        # Given LTV0 and LTV1, compute both shocks
        if _ltv1 > 0:
            shock_results["collateral_shock"] = (_ltv1 - _ltv0) / _ltv1
        else:
            shock_results["collateral_shock"] = None
        if _ltv0 > 0:
            shock_results["debt_spike"] = (_ltv1 - _ltv0) / _ltv0
        else:
            shock_results["debt_spike"] = None
        shock_results["ltv1_computed"] = None

    elif _mode == "collateral_shock":
        # LTV1 = LTV0 / (1 - shock)
        if abs(1.0 - _shock_pct) > 1e-9:
            _computed_ltv1 = _ltv0 / (1.0 - _shock_pct)
            shock_results["ltv1_computed"] = _computed_ltv1
        else:
            shock_results["ltv1_computed"] = float("inf")
        shock_results["collateral_shock"] = _shock_pct
        shock_results["debt_spike"] = None

    elif _mode == "debt_spike":
        # LTV1 = LTV0 * (1 + spike)
        _computed_ltv1 = _ltv0 * (1.0 + _shock_pct)
        shock_results["ltv1_computed"] = _computed_ltv1
        shock_results["debt_spike"] = _shock_pct
        shock_results["collateral_shock"] = None

    return (shock_results,)


# --- Cell 10: Tab 2 assembly ---
@app.cell
def tab2_assembly(
    ltv0_input, ltv1_input, mo, shock_mode, shock_pct_input, shock_results
):
    _mode = shock_mode.value

    # Build result display
    _lines = []
    if _mode == "ltv_to_shock":
        _cs = shock_results.get("collateral_shock")
        _ds = shock_results.get("debt_spike")
        _cs_str = f"{_cs * 100:.2f}%" if _cs is not None else "N/A"
        _ds_str = f"{_ds * 100:.2f}%" if _ds is not None else "N/A"
        _lines.append(f"**Collateral Price Shock:** {_cs_str} &nbsp;|&nbsp; **Debt Price Spike:** {_ds_str}")
    else:
        _ltv1_c = shock_results.get("ltv1_computed")
        if _ltv1_c is not None and _ltv1_c != float("inf"):
            _lines.append(f"**Computed LTV1:** {_ltv1_c * 100:.2f}%")
            if _ltv1_c >= 1.0:
                _lines.append("*Warning: LTV >= 100% means the position is underwater (liquidation).*")
        elif _ltv1_c == float("inf"):
            _lines.append("**Computed LTV1:** Infinity (100% shock = total loss)")

    # Choose which inputs to show based on mode
    if _mode == "ltv_to_shock":
        _inputs = mo.hstack(
            [ltv0_input, ltv1_input], justify="start", gap=1.5
        )
    else:
        _inputs = mo.hstack(
            [ltv0_input, shock_pct_input], justify="start", gap=1.5
        )

    tab2_content = mo.vstack([
        mo.md("### Calculator"),
        mo.md(
            "Collateral Price Shock: `(LTV1 - LTV0) / LTV1`<br>"
            "Debt Price Spike: `(LTV1 - LTV0) / LTV0`<br>"
            "Reverse: `LTV1 = LTV0 / (1 - shock)` or `LTV1 = LTV0 * (1 + spike)`"
        ),
        shock_mode,
        _inputs,
        mo.md("\n".join(_lines)) if _lines else mo.md(""),
    ])
    return (tab2_content,)


# =====================================================================
# TAB 3: INCENTIVE DILUTION
# =====================================================================


# --- Cell 11: Tab 3 inputs ---
@app.cell
def tab3_inputs(mo):
    solve_for_dropdown = mo.ui.dropdown(
        options={
            "Solve for Rate": "rate",
            "Solve for TVL": "tvl",
            "Solve for Budget": "budget",
        },
        value="Solve for Rate",
        label="Solve for",
    )
    rate_input_tab3 = mo.ui.number(
        start=0.0, stop=100.0, step=0.1, value=5.0,
        debounce=True, label="Rate (annualized %)",
    )
    tvl_input_tab3 = mo.ui.number(
        start=0.0, stop=10_000_000_000.0, step=1_000_000.0, value=50_000_000.0,
        debounce=True, label="Target TVL ($)",
    )
    budget_input_tab3 = mo.ui.number(
        start=0.0, stop=100_000_000.0, step=10_000.0, value=100_000.0,
        debounce=True, label="Budget ($)",
    )
    duration_input_tab3 = mo.ui.number(
        start=1, stop=365, step=1, value=7,
        debounce=True, label="Duration (days)",
    )
    # Heatmap axis range inputs
    budget_min_input = mo.ui.number(
        start=0.0, stop=100_000_000.0, step=10_000.0, value=10_000.0,
        debounce=True, label="Budget Min ($)",
    )
    budget_max_input = mo.ui.number(
        start=0.0, stop=100_000_000.0, step=10_000.0, value=1_000_000.0,
        debounce=True, label="Budget Max ($)",
    )
    tvl_min_input = mo.ui.number(
        start=0.0, stop=10_000_000_000.0, step=1_000_000.0, value=1_000_000.0,
        debounce=True, label="TVL Min ($)",
    )
    tvl_max_input = mo.ui.number(
        start=0.0, stop=10_000_000_000.0, step=1_000_000.0, value=200_000_000.0,
        debounce=True, label="TVL Max ($)",
    )
    return (
        budget_input_tab3,
        budget_max_input,
        budget_min_input,
        duration_input_tab3,
        rate_input_tab3,
        solve_for_dropdown,
        tvl_input_tab3,
        tvl_max_input,
        tvl_min_input,
    )


# --- Cell 12: Tab 3 computation ---
@app.cell
def tab3_compute(
    budget_input_tab3,
    duration_input_tab3,
    rate_input_tab3,
    solve_for_dropdown,
    tvl_input_tab3,
):
    _solve = solve_for_dropdown.value
    _rate = rate_input_tab3.value / 100.0  # Convert to decimal
    _tvl = tvl_input_tab3.value
    _budget = budget_input_tab3.value
    _duration = duration_input_tab3.value

    incentive_result = {}

    if _solve == "rate":
        # Rate = Budget * 365 / (TVL * Duration)
        if _tvl > 0 and _duration > 0:
            _computed = _budget * 365.0 / (_tvl * _duration)
            incentive_result["label"] = "Computed Rate"
            incentive_result["value"] = f"{_computed * 100:.4f}%"
            incentive_result["raw"] = _computed * 100
        else:
            incentive_result["label"] = "Computed Rate"
            incentive_result["value"] = "N/A (TVL or Duration is 0)"
            incentive_result["raw"] = None

    elif _solve == "tvl":
        # TVL = Budget * 365 / (Rate * Duration)
        if _rate > 0 and _duration > 0:
            _computed = _budget * 365.0 / (_rate * _duration)
            incentive_result["label"] = "Computed TVL"
            incentive_result["value"] = f"${_computed:,.0f}"
            incentive_result["raw"] = _computed
        else:
            incentive_result["label"] = "Computed TVL"
            incentive_result["value"] = "N/A (Rate or Duration is 0)"
            incentive_result["raw"] = None

    elif _solve == "budget":
        # Budget = Rate * TVL * Duration / 365
        if _duration > 0:
            _computed = _rate * _tvl * _duration / 365.0
            incentive_result["label"] = "Computed Budget"
            incentive_result["value"] = f"${_computed:,.0f}"
            incentive_result["raw"] = _computed
        else:
            incentive_result["label"] = "Computed Budget"
            incentive_result["value"] = "N/A (Duration is 0)"
            incentive_result["raw"] = None

    return (incentive_result,)


# --- Cell 13: Tab 3 heatmap ---
@app.cell
def tab3_heatmap(
    apply_style, budget_max_input, budget_min_input, duration_input_tab3,
    np, px, tvl_max_input, tvl_min_input,
):
    _duration = duration_input_tab3.value
    _b_min = budget_min_input.value
    _b_max = budget_max_input.value
    _t_min = tvl_min_input.value
    _t_max = tvl_max_input.value

    # Guard against invalid ranges
    if _b_max <= _b_min:
        _b_max = _b_min + 10_000
    if _t_max <= _t_min:
        _t_max = _t_min + 1_000_000

    _budgets = np.linspace(_b_min, _b_max, 50)
    _tvls = np.linspace(_t_min, _t_max, 50)
    _budget_grid, _tvl_grid = np.meshgrid(_budgets, _tvls)

    # Rate = Budget * 365 / (TVL * Duration) * 100 (as %)
    _rate_grid = np.where(
        (_tvl_grid > 0) & (_duration > 0),
        _budget_grid * 365.0 / (_tvl_grid * _duration) * 100.0,
        np.nan,
    )

    _fig = px.imshow(
        _rate_grid,
        x=np.round(_budgets, 0),
        y=np.round(_tvls, 0),
        origin="lower",
        labels={"x": "Budget ($)", "y": "Target TVL ($)", "color": "Rate (%)"},
        color_continuous_scale="Viridis",
        aspect="auto",
        zmin=0,
        zmax=20,
        title=f"Annualized Rate (%) for {_duration}-day Campaign",
    )
    _fig.update_xaxes(tickprefix="$", tickformat=",.0f")
    _fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    heatmap_fig_tab3 = apply_style(_fig, height=520)
    return (heatmap_fig_tab3,)


# --- Cell 14: Tab 3 assembly ---
@app.cell
def tab3_assembly(
    budget_input_tab3,
    budget_max_input,
    budget_min_input,
    duration_input_tab3,
    heatmap_fig_tab3,
    incentive_result,
    mo,
    rate_input_tab3,
    solve_for_dropdown,
    tvl_input_tab3,
    tvl_max_input,
    tvl_min_input,
):
    _solve = solve_for_dropdown.value

    # Show only the relevant inputs (the 2 that are given, not the one being solved)
    _given_inputs = []
    if _solve != "rate":
        _given_inputs.append(rate_input_tab3)
    if _solve != "tvl":
        _given_inputs.append(tvl_input_tab3)
    if _solve != "budget":
        _given_inputs.append(budget_input_tab3)
    _given_inputs.append(duration_input_tab3)

    tab3_content = mo.vstack([
        mo.md("### Calculator"),
        mo.md(
            "**Formula:** `Budget = Rate * TVL * Duration / 365`\n\n"
            "Input any 2 of {Rate, TVL, Budget} to solve for the third."
        ),
        solve_for_dropdown,
        mo.hstack(_given_inputs, justify="start", gap=1.5),
        mo.md(f"**{incentive_result['label']}:** {incentive_result['value']}"),
        mo.md("---"),
        mo.md("### Heatmap: Rate vs Budget and TVL"),
        mo.md("Axis ranges:"),
        mo.hstack([
            mo.vstack([budget_min_input, budget_max_input]),
            mo.vstack([tvl_min_input, tvl_max_input]),
        ], justify="start", gap=3.0),
        mo.as_html(heatmap_fig_tab3),
    ])
    return (tab3_content,)


# =====================================================================
# MAIN: TITLE + TABS
# =====================================================================


@app.cell
def main(mo, tab1_content, tab2_content, tab3_content):
    mo.output.replace(
        mo.vstack([
            mo.md("# Quick Formula Calculator"),
            mo.md("Reactive DeFi formula calculator for leveraged yield, price shocks, and incentive dilution."),
            mo.ui.tabs(
                {
                    "Leveraged Yield": tab1_content,
                    "Shock to LTV": tab2_content,
                    "Incentive Dilution": tab3_content,
                },
                lazy=True,
            ),
        ])
    )
    return


if __name__ == "__main__":
    app.run()

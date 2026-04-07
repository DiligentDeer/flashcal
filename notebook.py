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
    import math
    from plotly.subplots import make_subplots

    CHART_BG = "#ffffff"
    GRID_COLOR = "#e0e0e0"
    return CHART_BG, GRID_COLOR, go, make_subplots, math, mo, np, px


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
# SHARED MATH HELPERS
# =====================================================================


# --- Euler Liquidation Math ---
@app.cell
def euler_math(np):
    def calculate_max_safe_ltv(LLTV, max_bonus):
        """Calculate theoretical LTV where bad debt begins (quadratic solver)."""
        if max_bonus == 0:
            return 1.0
        _M = max_bonus / (1 - LLTV)
        _disc = (_M - 1) ** 2 + 4 * _M * LLTV
        return (-(_M - 1) + np.sqrt(_disc)) / 2

    def euler_liquidation_model(hf_start, hf_end, steps, LLTV, max_bonus, collateral_value):
        """Simulate Euler liquidation across HF range. Returns numpy arrays."""
        _hf = np.linspace(hf_start, hf_end, steps)
        _ltv = LLTV / _hf
        _buffer = 1.0 - _ltv
        _slope = max_bonus / (1 - LLTV)
        _raw = np.where(_hf > LLTV, _slope * (1 - _hf), max_bonus)
        _eff = np.minimum(_raw, max_bonus)
        _profit = _eff * collateral_value
        _bad = np.maximum(0, (_raw - _buffer)) * collateral_value
        return _hf, _ltv, _buffer, _raw, _eff, _profit, _bad

    return calculate_max_safe_ltv, euler_liquidation_model


# --- Loan Liquidation Risk Math ---
@app.cell
def loan_risk_math(np):
    def calculate_price_changes(input_mode, initial_value, final_value):
        """Calculate price changes for HF/LTV transitions."""
        if input_mode == "hf":
            _ratio = initial_value / final_value
            _decreased = final_value < initial_value
        else:
            _ratio = final_value / initial_value
            _decreased = final_value > initial_value
        _debt = (_ratio - 1) * 100
        _coll = (1 - 1 / _ratio) * 100
        if _decreased:
            return _ratio, abs(_debt), -abs(_coll), _decreased
        return _ratio, -abs(_debt), abs(_coll), _decreased

    def generate_combined_scenarios(ratio, max_debt_increase=100):
        """Generate valid (debt_increase, collateral_decrease) pairs."""
        _d = np.linspace(0, max_debt_increase, 101)
        _beta = 1 - (1 + _d / 100) / ratio
        _c = _beta * 100
        _mask = (_c >= 0) & (_c <= 100)
        return _d[_mask], _c[_mask]

    return calculate_price_changes, generate_combined_scenarios


# --- Adaptive Curve IRM Math ---
@app.cell
def adaptive_irm_math(math):
    _SECONDS_PER_YEAR = 365 * 24 * 3600
    _TARGET = 0.9
    _STEEPNESS = 4.0
    _ADJ_SPEED = 50.0 / _SECONDS_PER_YEAR
    _MIN_RT = 0.01
    _MAX_RT = 1000.0

    ADAPTIVE_IRM_CONSTANTS = {
        "Target Utilization (%)": 90.0,
        "Curve Steepness (C)": 4.0,
        "Adjustment Speed (per year)": 50.0,
        "Min Rate At Target (APR, %)": 1.0,
        "Max Rate At Target (APR, %)": 100000.0,
    }

    def simulate_adaptive_irm(u_pct, start_kink_pct, hours):
        """Simulate adaptive IRM evolution at constant utilization."""
        _u = u_pct / 100.0
        _en = (1 - _TARGET) if _u > _TARGET else _TARGET
        _err = 0.0 if _en == 0 else (_u - _TARGET) / _en
        _start_rt = start_kink_pct / 100.0
        _la = (_ADJ_SPEED * _err) * (hours * 3600.0)
        _end_rt = max(min(_start_rt * math.exp(_la), _MAX_RT), _MIN_RT)
        _mid_rt = max(min(_start_rt * math.exp(_la / 2.0), _MAX_RT), _MIN_RT)
        _avg_rt = (_start_rt + _end_rt + 2 * _mid_rt) / 4.0
        _coeff_e = (_STEEPNESS - 1) if _err >= 0 else (1 - 1 / _STEEPNESS)
        _coeff_a = (_STEEPNESS - 1) if _err >= 0 else (1 - 1 / _STEEPNESS)
        _end_borrow = (_coeff_e * _err + 1) * _end_rt * 100.0
        _avg_borrow = (_coeff_a * _err + 1) * _avg_rt * 100.0
        return _err, _start_rt * 100.0, _end_rt * 100.0, _avg_rt * 100.0, _end_borrow, _avg_borrow

    return ADAPTIVE_IRM_CONSTANTS, simulate_adaptive_irm


# --- IRM Analyzer Math ---
@app.cell
def irm_analyzer_math(np):
    from decimal import Decimal as _Decimal, getcontext as _gc
    _gc().prec = 50
    _SLOTS_PER_SECOND = 2
    _SLOTS_PER_YEAR = _SLOTS_PER_SECOND * 60 * 60 * 24 * 365.25

    def calculate_supply_rate_fn(utilization, borrow_rate, reserve_factor):
        """Standard: utilization * borrow_rate * (1 - reserve_factor)."""
        return (utilization / 100) * borrow_rate * (1 - reserve_factor / 100)

    def calculate_kamino_supply_rate_fn(borrow_rate, utilization, fixed_host_rate, protocol_take_rate, slot_duration_ms):
        """Kamino supply rate with Decimal precision."""
        _sa = 1000 / (_SLOTS_PER_SECOND * slot_duration_ms)
        _bapy = _Decimal(str(borrow_rate)) / _Decimal('100')
        _apr = _Decimal(str(float(_bapy + _Decimal('1')) ** (1 / _SLOTS_PER_YEAR) - 1)) * _Decimal(str(_SLOTS_PER_YEAR))
        _host = _Decimal(str(fixed_host_rate)) / _Decimal('100')
        _adj = _apr - (_host * _Decimal(str(_sa)))
        _util = _Decimal(str(utilization)) / _Decimal('100')
        _take = _Decimal(str(protocol_take_rate)) / _Decimal('100')
        _supply_apr = _util * _adj * (_Decimal('1') - _take)
        _sb = _Decimal('1') + (_supply_apr / _Decimal(str(_SLOTS_PER_YEAR)))
        _supply_apy = _Decimal(str(float(_sb) ** _SLOTS_PER_YEAR - 1))
        return float(_supply_apy * _Decimal('100'))

    def interpolate_curve(util_points, rate_points, common_util):
        """Linear interpolation to common utilization grid."""
        return np.interp(common_util, util_points, rate_points)

    def calculate_derivatives(utilization, rates):
        """Rate derivative using numpy gradient."""
        return np.gradient(rates, utilization)

    return calculate_derivatives, calculate_kamino_supply_rate_fn, calculate_supply_rate_fn, interpolate_curve


# --- Campaign Simulation Math ---
@app.cell
def campaign_math(np):
    def simulate_campaigns(campaigns, initial_capacity, final_capacity, duration, epoch_hours):
        """Simulate multiple incentive campaigns with 3 strategies."""
        _ne = max(1, int(duration * 24 / epoch_hours))
        _time = np.linspace(0, duration, _ne)
        _cap = np.linspace(initial_capacity, final_capacity, _ne)
        _res = {"time": _time, "capacity": _cap, "campaigns": {}}

        for _c in campaigns:
            _rates = np.zeros(_ne)
            _brem = np.zeros(_ne)
            _b = _c["budget"]

            if _c["type"] == "variable":
                _bpe = _c["budget"] / _ne
                for _i in range(_ne):
                    if _b >= _bpe and _cap[_i] > 0:
                        _rates[_i] = (_bpe / _cap[_i]) * (365 * 24 / epoch_hours) * 100
                        _b -= _bpe
                    _brem[_i] = _b

            elif _c["type"] == "fixed":
                _tr = _c["target_rate"] / 100
                for _i in range(_ne):
                    if _cap[_i] > 0:
                        _req = _cap[_i] * _tr * ((epoch_hours / 24) / 365)
                        if _b >= _req:
                            _rates[_i] = _tr * 100
                            _b -= _req
                    _brem[_i] = _b

            elif _c["type"] == "capped":
                _tr = _c["target_rate"] / 100
                for _i in range(_ne):
                    if _cap[_i] == 0:
                        _brem[_i] = _b
                        continue
                    _needed = _cap[_i] * _tr * ((epoch_hours / 24) / 365)
                    _left = _ne - _i
                    _avail = _b / _left
                    if _needed <= _avail:
                        _rates[_i] = _tr * 100
                        _b -= _needed
                    else:
                        _rates[_i] = (_avail / _cap[_i]) * (365 * 24 / epoch_hours) * 100
                        _b -= _avail
                    _brem[_i] = _b

            _res["campaigns"][_c["name"]] = {"rates": _rates, "budget_remaining": _brem}

        return _res

    return (simulate_campaigns,)


# --- CSV Helper ---
@app.cell
def csv_helper():
    def dicts_to_csv(rows):
        """Convert list of dicts to CSV string without pandas."""
        if not rows:
            return ""
        _h = list(rows[0].keys())
        _lines = [",".join(_h)]
        for _r in rows:
            _lines.append(",".join(str(_r.get(k, "")) for k in _h))
        return "\n".join(_lines)

    return (dicts_to_csv,)


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
    max_supply_rate_input = mo.ui.number(
        start=0.5, stop=100.0, step=0.5, value=15.0,
        debounce=True, label="Max Supply Rate (%)",
    )
    max_borrow_rate_input = mo.ui.number(
        start=0.5, stop=100.0, step=0.5, value=15.0,
        debounce=True, label="Max Borrow Rate (%)",
    )
    ltv_highlight_input = mo.ui.number(
        start=0.0, stop=100.0, step=0.5, value=86.0,
        debounce=True, label="LTV to Highlight (%)",
    )
    ltv_tolerance_input = mo.ui.number(
        start=0.0, stop=20.0, step=0.1, value=1.5,
        debounce=True, label="Tolerance ± (%)",
    )
    return (ltv_highlight_input, ltv_tolerance_input, max_borrow_rate_input, max_supply_rate_input, target_yield_input,)


# --- Cell 5: Tab 1 heatmap ---
@app.cell
def tab1_heatmap(apply_style, go, ltv_highlight_input, ltv_tolerance_input, max_borrow_rate_input, max_supply_rate_input, np, px, target_yield_input):
    _target = target_yield_input.value
    _max_sr = max_supply_rate_input.value
    _max_br = max_borrow_rate_input.value
    _ltv_hl_pct = ltv_highlight_input.value
    _tol = ltv_tolerance_input.value
    _borrow_rates = np.linspace(0.0, _max_br, 61)
    _supply_rates = np.linspace(0.0, _max_sr, 61)
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

    # Highlight cells where LTV is within ±tolerance of the target LTV
    _highlight = np.where(
        np.abs(_ltv_grid_pct - _ltv_hl_pct) <= _tol,
        _ltv_grid_pct,
        np.nan,
    )
    _fig.add_trace(go.Heatmap(
        z=_highlight,
        x=np.round(_borrow_rates, 2),
        y=np.round(_supply_rates, 2),
        colorscale=[[0, "rgba(255,0,0,0.7)"], [1, "rgba(255,0,0,0.7)"]],
        showscale=False,
        name=f"LTV = {_ltv_hl_pct:.1f}%",
        hovertemplate="Borrow: %{x:.1f}%<br>Supply: %{y:.1f}%<br>LTV: %{z:.1f}%<extra>Highlighted LTV</extra>",
    ))

    heatmap_fig_tab1 = apply_style(_fig, height=520)
    return (heatmap_fig_tab1,)


# --- Cell 7: Tab 1 assembly ---
@app.cell
def tab1_assembly(
    heatmap_fig_tab1,
    leverage_result,
    leveraged_yield_result,
    ltv_highlight_input,
    ltv_input,
    ltv_tolerance_input,
    max_borrow_rate_input,
    max_supply_rate_input,
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
        mo.hstack(
            [target_yield_input, max_supply_rate_input, max_borrow_rate_input, ltv_highlight_input, ltv_tolerance_input],
            justify="start",
            gap=1.5,
        ),
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
        start=0.0, stop=10_000_000_000.0, step=100.0, value=50_000_000.0,
        debounce=True, label="Target TVL ($)",
    )
    budget_input_tab3 = mo.ui.number(
        start=0.0, stop=100_000_000.0, step=100.0, value=100_000.0,
        debounce=True, label="Budget ($)",
    )
    duration_input_tab3 = mo.ui.number(
        start=1, stop=365, step=1, value=7,
        debounce=True, label="Duration (days)",
    )
    # Heatmap axis range inputs
    budget_min_input = mo.ui.number(
        start=0.0, stop=100_000_000.0, step=100.0, value=10_000.0,
        debounce=True, label="Budget Min ($)",
    )
    budget_max_input = mo.ui.number(
        start=0.0, stop=100_000_000.0, step=100.0, value=1_000_000.0,
        debounce=True, label="Budget Max ($)",
    )
    tvl_min_input = mo.ui.number(
        start=0.0, stop=10_000_000_000.0, step=100.0, value=1_000_000.0,
        debounce=True, label="TVL Min ($)",
    )
    tvl_max_input = mo.ui.number(
        start=0.0, stop=10_000_000_000.0, step=100.0, value=200_000_000.0,
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
# TAB 4: EULER LIQUIDATION
# =====================================================================


# --- Tab 4 inputs ---
@app.cell
def tab4_inputs(mo):
    euler_hf_start = mo.ui.number(
        start=0.1, stop=2.0, step=0.01, value=1.0,
        debounce=True, label="HF Start",
    )
    euler_hf_end = mo.ui.number(
        start=0.1, stop=1.5, step=0.01, value=0.80,
        debounce=True, label="HF End",
    )
    euler_steps = mo.ui.number(
        start=10, stop=1000, step=10, value=100,
        debounce=True, label="Steps",
    )
    euler_use_ltv = mo.ui.checkbox(label="Show X-axis as LTV (%)")
    euler_c1 = mo.ui.dictionary({
        "enabled": mo.ui.checkbox(value=True, label="Enabled"),
        "lltv": mo.ui.number(start=10, stop=99, step=1, value=91, debounce=True, label="LLTV (%)"),
        "bonus": mo.ui.number(start=1, stop=50, step=1, value=15, debounce=True, label="Max Bonus (%)"),
        "collateral": mo.ui.number(start=1.0, stop=10000.0, step=1.0, value=100.0, debounce=True, label="Collateral ($)"),
    })
    euler_c2 = mo.ui.dictionary({
        "enabled": mo.ui.checkbox(value=False, label="Enabled"),
        "lltv": mo.ui.number(start=10, stop=99, step=1, value=86, debounce=True, label="LLTV (%)"),
        "bonus": mo.ui.number(start=1, stop=50, step=1, value=12, debounce=True, label="Max Bonus (%)"),
        "collateral": mo.ui.number(start=1.0, stop=10000.0, step=1.0, value=100.0, debounce=True, label="Collateral ($)"),
    })
    euler_c3 = mo.ui.dictionary({
        "enabled": mo.ui.checkbox(value=False, label="Enabled"),
        "lltv": mo.ui.number(start=10, stop=99, step=1, value=80, debounce=True, label="LLTV (%)"),
        "bonus": mo.ui.number(start=1, stop=50, step=1, value=10, debounce=True, label="Max Bonus (%)"),
        "collateral": mo.ui.number(start=1.0, stop=10000.0, step=1.0, value=100.0, debounce=True, label="Collateral ($)"),
    })
    return euler_c1, euler_c2, euler_c3, euler_hf_end, euler_hf_start, euler_steps, euler_use_ltv


# --- Tab 4 compute ---
@app.cell
def tab4_compute(
    euler_c1, euler_c2, euler_c3, euler_hf_end, euler_hf_start, euler_steps,
    euler_liquidation_model, calculate_max_safe_ltv, np,
):
    _curves = [
        ("Curve 1", euler_c1.value),
        ("Curve 2", euler_c2.value),
        ("Curve 3", euler_c3.value),
    ]
    euler_results = []
    for _name, _cv in _curves:
        if not _cv["enabled"]:
            continue
        _lltv = _cv["lltv"] / 100
        _bonus = _cv["bonus"] / 100
        _coll = _cv["collateral"]
        _hf, _ltv, _buf, _raw, _eff, _profit, _bad = euler_liquidation_model(
            euler_hf_start.value, euler_hf_end.value, int(euler_steps.value),
            _lltv, _bonus, _coll,
        )
        _msl = calculate_max_safe_ltv(_lltv, _bonus)
        euler_results.append({
            "name": _name, "hf": _hf, "ltv": _ltv, "profit": _profit,
            "bad_debt": _bad, "max_safe_ltv": _msl, "lltv": _lltv, "bonus": _bonus,
        })
    return (euler_results,)


# --- Tab 4 chart ---
@app.cell
def tab4_chart(euler_results, euler_use_ltv, apply_style, go):
    _colors = ["#1f77b4", "#ff7f0e", "#2ca02c"]
    euler_fig = go.Figure()
    for _i, _r in enumerate(euler_results):
        _col = _colors[_i % len(_colors)]
        _x = _r["ltv"] * 100 if euler_use_ltv.value else _r["hf"]
        euler_fig.add_trace(go.Scatter(
            x=_x, y=_r["profit"], mode="lines",
            name=f'{_r["name"]} - Profit', line=dict(color=_col, width=3),
        ))
        euler_fig.add_trace(go.Scatter(
            x=_x, y=_r["bad_debt"], mode="lines",
            name=f'{_r["name"]} - Bad Debt', line=dict(color=_col, width=3, dash="dash"),
        ))
        # Max safe LTV / Min safe HF line
        if euler_use_ltv.value:
            euler_fig.add_vline(
                x=_r["max_safe_ltv"] * 100, line_dash="dashdot", line_color="orange",
                annotation_text=f'{_r["name"]} Max Safe LTV',
            )
        elif _r["max_safe_ltv"] > 0:
            euler_fig.add_vline(
                x=_r["lltv"] / _r["max_safe_ltv"], line_dash="dashdot", line_color="orange",
                annotation_text=f'{_r["name"]} Min Safe HF',
            )
    _xt = "LTV (%)" if euler_use_ltv.value else "Health Factor"
    euler_fig.update_xaxes(title_text=_xt)
    euler_fig.update_yaxes(title_text="Amount ($)")
    if not euler_use_ltv.value:
        euler_fig.update_xaxes(autorange="reversed")
    euler_fig.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.6)
    euler_fig = apply_style(euler_fig, height=500)
    return (euler_fig,)


# --- Tab 4 assembly ---
@app.cell
def tab4_assembly(
    euler_c1, euler_c2, euler_c3, euler_fig, euler_hf_end, euler_hf_start,
    euler_results, euler_steps, euler_use_ltv, mo,
):
    _metrics = []
    for _r in euler_results:
        _metrics.append(f'**{_r["name"]}** Max Safe LTV: {_r["max_safe_ltv"]*100:.2f}%')

    tab4_content = mo.vstack([
        mo.md("### Euler Liquidation Factor"),
        mo.md("Buffer-capped liquidation-bonus model with bad debt analysis."),
        mo.md(
            "`Max Safe LTV`: Quadratic solution where bad debt begins (buffer = raw bonus)."
        ),
        mo.hstack([euler_hf_start, euler_hf_end, euler_steps, euler_use_ltv], justify="start", gap=1.5),
        mo.accordion({
            "Curve 1": euler_c1,
            "Curve 2": euler_c2,
            "Curve 3": euler_c3,
        }),
        mo.md(" | ".join(_metrics)) if _metrics else mo.md("Enable at least one curve."),
        mo.as_html(euler_fig) if euler_results else mo.md("No curves enabled."),
    ])
    return (tab4_content,)


# =====================================================================
# TAB 5: LOAN LIQUIDATION RISK
# =====================================================================


# --- Tab 5 inputs ---
@app.cell
def tab5_inputs(mo):
    loan_mode = mo.ui.dropdown(
        options={"Health Factor": "hf", "LTV Ratio": "ltv"},
        value="Health Factor",
        label="Input Mode",
    )
    loan_initial = mo.ui.number(
        start=0.01, stop=3.0, step=0.01, value=1.5,
        debounce=True, label="Initial (HF or LTV decimal)",
    )
    loan_final = mo.ui.number(
        start=0.01, stop=3.0, step=0.01, value=1.0,
        debounce=True, label="Final (HF or LTV decimal)",
    )
    return loan_final, loan_initial, loan_mode


# --- Tab 5 compute ---
@app.cell
def tab5_compute(
    loan_final, loan_initial, loan_mode,
    calculate_price_changes, generate_combined_scenarios, np,
):
    _mode = loan_mode.value
    _init = loan_initial.value
    _fin = loan_final.value

    # Values used directly: HF as decimal (e.g. 1.5), LTV as decimal (e.g. 0.6 = 60%)
    loan_ratio, loan_debt_only, loan_coll_only, loan_hf_decreased = calculate_price_changes(
        _mode, _init, _fin,
    )
    loan_scenario_debt, loan_scenario_coll = generate_combined_scenarios(loan_ratio)
    return loan_coll_only, loan_debt_only, loan_hf_decreased, loan_ratio, loan_scenario_coll, loan_scenario_debt


# --- Tab 5 chart ---
@app.cell
def tab5_chart(
    loan_coll_only, loan_debt_only, loan_scenario_coll, loan_scenario_debt,
    apply_style, go,
):
    loan_fig = go.Figure()
    if len(loan_scenario_debt) > 0:
        loan_fig.add_trace(go.Scatter(
            x=loan_scenario_debt, y=loan_scenario_coll, fill="tonexty",
            mode="lines", name="Valid Scenarios",
            line=dict(color="#f97316", width=2),
            fillcolor="rgba(249, 115, 22, 0.3)",
        ))
        loan_fig.add_trace(go.Scatter(
            x=[0, abs(loan_debt_only)],
            y=[abs(loan_coll_only), 0],
            mode="markers", name="Isolated Changes",
            marker=dict(size=10, color=["red", "orange"], symbol=["circle", "square"]),
        ))
    loan_fig.update_layout(
        title="Price Movement Combinations",
        xaxis_title="Debt Token Price Increase (%)",
        yaxis_title="Collateral Token Price Decrease (%)",
    )
    loan_fig = apply_style(loan_fig, height=450)
    return (loan_fig,)


# --- Tab 5 assembly ---
@app.cell
def tab5_assembly(
    loan_coll_only, loan_debt_only, loan_fig, loan_final,
    loan_hf_decreased, loan_initial, loan_mode, loan_ratio, mo,
):
    _mode = loan_mode.value
    _init = loan_initial.value
    _fin = loan_final.value
    _lbl = "HF" if _mode == "hf" else "LTV"
    _init_str = f"{_init:.2f}" if _mode == "hf" else f"{_init*100:.1f}%"
    _fin_str = f"{_fin:.2f}" if _mode == "hf" else f"{_fin*100:.1f}%"
    _change = ((_fin / _init - 1) * 100) if _init != 0 else 0
    _risk = ""
    if _mode == "hf" and _fin < 1.0:
        _risk = "*Warning: Final HF < 1 — position is liquidatable.*"
    elif _mode == "ltv" and _fin > 0.9:
        _risk = "*Warning: Final LTV > 90% — position may be close to liquidation.*"

    _ds = f"+{loan_debt_only:.2f}%" if loan_debt_only >= 0 else f"{loan_debt_only:.2f}%"
    _cs = f"+{loan_coll_only:.2f}%" if loan_coll_only >= 0 else f"{loan_coll_only:.2f}%"

    tab5_content = mo.vstack([
        mo.md("### Loan Liquidation Risk Calculator"),
        mo.md(
            "Analyze how debt and collateral price movements affect your loan health."
        ),
        mo.md(
            "`(1 + debt_change) / (1 - collateral_change) = ratio`"
        ),
        loan_mode,
        mo.hstack([loan_initial, loan_final], justify="start", gap=1.5),
        mo.md(f"**{_risk}**") if _risk else mo.md(""),
        mo.md(
            f"**Initial {_lbl}:** {_init_str} | "
            f"**Final {_lbl}:** {_fin_str} | "
            f"**Change:** {_change:+.1f}% | "
            f"**Price Ratio:** {loan_ratio:.4f}"
        ),
        mo.md(
            f"**Debt Token Price Change:** {_ds} | "
            f"**Collateral Token Price Change:** {_cs}"
        ),
        mo.md("---"),
        mo.md("### Combined Price Movement Scenarios"),
        mo.as_html(loan_fig),
    ])
    return (tab5_content,)


# =====================================================================
# TAB 6: ADAPTIVE CURVE IRM
# =====================================================================


# --- Tab 6 inputs ---
@app.cell
def tab6_inputs(mo):
    irm_util = mo.ui.number(
        start=0.0, stop=100.0, step=0.1, value=80.0,
        debounce=True, label="Current Utilization (%)",
    )
    irm_kink = mo.ui.number(
        start=0.0, stop=1000.0, step=0.1, value=5.0,
        debounce=True, label="Current IRM Kink Rate (APR, %)",
    )
    irm_use_days = mo.ui.checkbox(label="Use days for time axis")
    irm_horizon = mo.ui.number(
        start=1, stop=8760, step=1, value=240,
        debounce=True, label="Horizon",
    )
    irm_show_avg = mo.ui.checkbox(value=True, label="Show average rate over interval")
    return irm_horizon, irm_kink, irm_show_avg, irm_use_days, irm_util


# --- Tab 6 compute ---
@app.cell
def tab6_compute(irm_horizon, irm_kink, irm_use_days, irm_util, simulate_adaptive_irm, np):
    _h_max = irm_horizon.value
    _times = np.linspace(0, _h_max, int(_h_max) + 1)
    irm_end_kinks = []
    irm_avg_kinks = []
    irm_end_borrows = []
    for _t in _times:
        _th = float(_t) if not irm_use_days.value else float(_t) * 24.0
        _, _, _ek, _ak, _eb, _ = simulate_adaptive_irm(irm_util.value, irm_kink.value, _th)
        irm_end_kinks.append(_ek)
        irm_avg_kinks.append(_ak)
        irm_end_borrows.append(_eb)
    irm_times = _times
    return irm_avg_kinks, irm_end_borrows, irm_end_kinks, irm_times


# --- Tab 6 charts ---
@app.cell
def tab6_charts(
    irm_avg_kinks, irm_end_borrows, irm_end_kinks, irm_show_avg,
    irm_times, irm_use_days, apply_style, go,
):
    _x_label = "Days" if irm_use_days.value else "Hours"

    irm_fig_kink = go.Figure()
    irm_fig_kink.add_trace(go.Scatter(
        x=irm_times, y=irm_end_kinks, mode="lines",
        name="End IRM Kink Rate (APR, %)", line=dict(width=3),
    ))
    if irm_show_avg.value:
        irm_fig_kink.add_trace(go.Scatter(
            x=irm_times, y=irm_avg_kinks, mode="lines",
            name="Average IRM Kink Rate (APR, %)", line=dict(width=2, dash="dash"),
        ))
    irm_fig_kink.update_layout(title="IRM Kink Rate vs Time")
    irm_fig_kink.update_xaxes(title_text=_x_label)
    irm_fig_kink.update_yaxes(title_text="Rate (APR, %)")
    irm_fig_kink = apply_style(irm_fig_kink, height=400)

    irm_fig_borrow = go.Figure()
    irm_fig_borrow.add_trace(go.Scatter(
        x=irm_times, y=irm_end_borrows, mode="lines",
        name="Borrow Rate (APR, %)", line=dict(width=3, color="#FFA500"),
    ))
    irm_fig_borrow.update_layout(title="Borrow Rate vs Time")
    irm_fig_borrow.update_xaxes(title_text=_x_label)
    irm_fig_borrow.update_yaxes(title_text="Borrow Rate (APR, %)")
    irm_fig_borrow = apply_style(irm_fig_borrow, height=400)

    return irm_fig_borrow, irm_fig_kink


# --- Tab 6 assembly ---
@app.cell
def tab6_assembly(
    ADAPTIVE_IRM_CONSTANTS, irm_fig_borrow, irm_fig_kink, irm_horizon,
    irm_kink, irm_show_avg, irm_use_days, irm_util, mo,
):
    _const_lines = [f"- **{k}:** {v}" for k, v in ADAPTIVE_IRM_CONSTANTS.items()]

    tab6_content = mo.vstack([
        mo.md("### Adaptive Curve IRM Simulator"),
        mo.md("Simulate Morpho's adaptive kink rate evolution under constant utilization."),
        mo.hstack([irm_util, irm_kink], justify="start", gap=1.5),
        mo.hstack([irm_use_days, irm_horizon, irm_show_avg], justify="start", gap=1.5),
        mo.as_html(irm_fig_kink),
        mo.as_html(irm_fig_borrow),
        mo.md("**Model Constants (fixed):**"),
        mo.md("\n".join(_const_lines)),
    ])
    return (tab6_content,)


# =====================================================================
# TAB 7: IRM ANALYZER
# =====================================================================


# --- Tab 7 inputs ---
@app.cell
def tab7_inputs(mo):
    irm_an_util_min = mo.ui.number(
        start=0, stop=100, step=5, value=0, debounce=True, label="Util Min (%)",
    )
    irm_an_util_max = mo.ui.number(
        start=0, stop=100, step=5, value=100, debounce=True, label="Util Max (%)",
    )
    irm_an_show_deriv = mo.ui.checkbox(label="Show Derivative Chart")
    irm_an_show_supply = mo.ui.checkbox(label="Show Supply Rate Curves")
    irm_an_use_kamino = mo.ui.checkbox(label="Kamino Supply Rate Calculation")
    irm_an_reserve = mo.ui.number(
        start=0.0, stop=50.0, step=0.5, value=10.0,
        debounce=True, label="Reserve Factor / Take Rate (%)",
    )
    irm_an_host = mo.ui.number(
        start=0.0, stop=10.0, step=0.1, value=1.0,
        debounce=True, label="Fixed Host Rate (%)",
    )
    irm_an_slot_ms = mo.ui.number(
        start=100, stop=2000, step=50, value=500,
        debounce=True, label="Slot Duration (ms)",
    )
    # 5 curve slots, each with name + 4 (util, rate) points
    irm_an_c1 = mo.ui.dictionary({
        "name": mo.ui.text(value="", label="Name"),
        "u0": mo.ui.number(start=0, stop=100, step=1, value=0, debounce=True, label="Util 1 (%)"),
        "r0": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=0.0, debounce=True, label="Rate 1 (%)"),
        "u1": mo.ui.number(start=0, stop=100, step=1, value=80, debounce=True, label="Util 2 (%)"),
        "r1": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=4.0, debounce=True, label="Rate 2 (%)"),
        "u2": mo.ui.number(start=0, stop=100, step=1, value=90, debounce=True, label="Util 3 (%)"),
        "r2": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=8.0, debounce=True, label="Rate 3 (%)"),
        "u3": mo.ui.number(start=0, stop=100, step=1, value=100, debounce=True, label="Util 4 (%)"),
        "r3": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=20.0, debounce=True, label="Rate 4 (%)"),
    })
    irm_an_c2 = mo.ui.dictionary({
        "name": mo.ui.text(value="", label="Name"),
        "u0": mo.ui.number(start=0, stop=100, step=1, value=0, debounce=True, label="Util 1 (%)"),
        "r0": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=0.0, debounce=True, label="Rate 1 (%)"),
        "u1": mo.ui.number(start=0, stop=100, step=1, value=80, debounce=True, label="Util 2 (%)"),
        "r1": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=2.0, debounce=True, label="Rate 2 (%)"),
        "u2": mo.ui.number(start=0, stop=100, step=1, value=90, debounce=True, label="Util 3 (%)"),
        "r2": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=5.0, debounce=True, label="Rate 3 (%)"),
        "u3": mo.ui.number(start=0, stop=100, step=1, value=100, debounce=True, label="Util 4 (%)"),
        "r3": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=15.0, debounce=True, label="Rate 4 (%)"),
    })
    irm_an_c3 = mo.ui.dictionary({
        "name": mo.ui.text(value="", label="Name"),
        "u0": mo.ui.number(start=0, stop=100, step=1, value=0, debounce=True, label="Util 1 (%)"),
        "r0": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=0.0, debounce=True, label="Rate 1 (%)"),
        "u1": mo.ui.number(start=0, stop=100, step=1, value=80, debounce=True, label="Util 2 (%)"),
        "r1": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=0.0, debounce=True, label="Rate 2 (%)"),
        "u2": mo.ui.number(start=0, stop=100, step=1, value=90, debounce=True, label="Util 3 (%)"),
        "r2": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=0.0, debounce=True, label="Rate 3 (%)"),
        "u3": mo.ui.number(start=0, stop=100, step=1, value=100, debounce=True, label="Util 4 (%)"),
        "r3": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=0.0, debounce=True, label="Rate 4 (%)"),
    })
    irm_an_c4 = mo.ui.dictionary({
        "name": mo.ui.text(value="", label="Name"),
        "u0": mo.ui.number(start=0, stop=100, step=1, value=0, debounce=True, label="Util 1 (%)"),
        "r0": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=0.0, debounce=True, label="Rate 1 (%)"),
        "u1": mo.ui.number(start=0, stop=100, step=1, value=80, debounce=True, label="Util 2 (%)"),
        "r1": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=0.0, debounce=True, label="Rate 2 (%)"),
        "u2": mo.ui.number(start=0, stop=100, step=1, value=90, debounce=True, label="Util 3 (%)"),
        "r2": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=0.0, debounce=True, label="Rate 3 (%)"),
        "u3": mo.ui.number(start=0, stop=100, step=1, value=100, debounce=True, label="Util 4 (%)"),
        "r3": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=0.0, debounce=True, label="Rate 4 (%)"),
    })
    irm_an_c5 = mo.ui.dictionary({
        "name": mo.ui.text(value="", label="Name"),
        "u0": mo.ui.number(start=0, stop=100, step=1, value=0, debounce=True, label="Util 1 (%)"),
        "r0": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=0.0, debounce=True, label="Rate 1 (%)"),
        "u1": mo.ui.number(start=0, stop=100, step=1, value=80, debounce=True, label="Util 2 (%)"),
        "r1": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=0.0, debounce=True, label="Rate 2 (%)"),
        "u2": mo.ui.number(start=0, stop=100, step=1, value=90, debounce=True, label="Util 3 (%)"),
        "r2": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=0.0, debounce=True, label="Rate 3 (%)"),
        "u3": mo.ui.number(start=0, stop=100, step=1, value=100, debounce=True, label="Util 4 (%)"),
        "r3": mo.ui.number(start=0.0, stop=1000.0, step=0.1, value=0.0, debounce=True, label="Rate 4 (%)"),
    })
    return (
        irm_an_c1, irm_an_c2, irm_an_c3, irm_an_c4, irm_an_c5,
        irm_an_host, irm_an_reserve, irm_an_show_deriv, irm_an_show_supply,
        irm_an_slot_ms, irm_an_use_kamino, irm_an_util_max, irm_an_util_min,
    )


# --- Tab 7 compute ---
@app.cell
def tab7_compute(
    irm_an_c1, irm_an_c2, irm_an_c3, irm_an_c4, irm_an_c5,
    irm_an_host, irm_an_reserve, irm_an_show_deriv, irm_an_show_supply,
    irm_an_slot_ms, irm_an_use_kamino, irm_an_util_max, irm_an_util_min,
    calculate_derivatives, calculate_kamino_supply_rate_fn,
    calculate_supply_rate_fn, interpolate_curve, np,
):
    _umin = irm_an_util_min.value
    _umax = irm_an_util_max.value
    if _umax <= _umin:
        _umax = _umin + 10
    _common = np.linspace(_umin, _umax, int(_umax - _umin) + 1)

    irm_an_active = []
    for _cv in [irm_an_c1, irm_an_c2, irm_an_c3, irm_an_c4, irm_an_c5]:
        _v = _cv.value
        if not _v["name"]:
            continue
        _util_pts = sorted([_v["u0"], _v["u1"], _v["u2"], _v["u3"]])
        _rate_pts_raw = [_v[f"r{i}"] for i in range(4)]
        # Sort rates by their corresponding utilization
        _pairs = sorted(zip(
            [_v["u0"], _v["u1"], _v["u2"], _v["u3"]],
            [_v["r0"], _v["r1"], _v["r2"], _v["r3"]],
        ))
        _util_pts = [p[0] for p in _pairs]
        _rate_pts = [p[1] for p in _pairs]
        _interp_borrow = interpolate_curve(_util_pts, _rate_pts, _common)

        _entry = {"name": _v["name"], "util": _common, "borrow": _interp_borrow,
                  "util_pts": _util_pts, "rate_pts": _rate_pts}

        if irm_an_show_supply.value:
            if irm_an_use_kamino.value:
                _supply = np.array([
                    calculate_kamino_supply_rate_fn(
                        br, ut, irm_an_host.value, irm_an_reserve.value, irm_an_slot_ms.value,
                    ) for ut, br in zip(_common, _interp_borrow)
                ])
            else:
                _supply = calculate_supply_rate_fn(_common, _interp_borrow, irm_an_reserve.value)
            _entry["supply"] = _supply

        if irm_an_show_deriv.value:
            _entry["borrow_deriv"] = calculate_derivatives(_common, _interp_borrow)
            if irm_an_show_supply.value:
                _entry["supply_deriv"] = calculate_derivatives(_common, _entry["supply"])

        irm_an_active.append(_entry)

    return (irm_an_active,)


# --- Tab 7 chart ---
@app.cell
def tab7_chart(
    irm_an_active, irm_an_show_deriv, irm_an_show_supply,
    irm_an_util_max, irm_an_util_min, apply_style, go, make_subplots,
):
    _colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]

    if irm_an_show_deriv.value and irm_an_active:
        irm_an_fig = make_subplots(
            rows=2, cols=1, subplot_titles=("Interest Rate Models", "Rate Derivatives"),
            vertical_spacing=0.15, row_heights=[0.55, 0.45],
        )
    else:
        irm_an_fig = go.Figure()

    for _i, _e in enumerate(irm_an_active):
        _col = _colors[_i % len(_colors)]
        _row_args = dict(row=1, col=1) if irm_an_show_deriv.value else {}

        irm_an_fig.add_trace(go.Scatter(
            x=_e["util"], y=_e["borrow"], mode="lines",
            name=f'{_e["name"]} Borrow', line=dict(color=_col, width=3),
        ), **_row_args)
        irm_an_fig.add_trace(go.Scatter(
            x=_e["util_pts"], y=_e["rate_pts"], mode="markers",
            name=f'{_e["name"]} Points', showlegend=False,
            marker=dict(color=_col, size=8, line=dict(color="white", width=2)),
        ), **_row_args)

        if irm_an_show_supply.value and "supply" in _e:
            irm_an_fig.add_trace(go.Scatter(
                x=_e["util"], y=_e["supply"], mode="lines",
                name=f'{_e["name"]} Supply', line=dict(color=_col, width=2, dash="dash"),
            ), **_row_args)

        if irm_an_show_deriv.value and "borrow_deriv" in _e:
            irm_an_fig.add_trace(go.Scatter(
                x=_e["util"], y=_e["borrow_deriv"], mode="lines",
                name=f'{_e["name"]} Borrow Deriv', line=dict(color=_col, width=2),
            ), row=2, col=1)
            if "supply_deriv" in _e:
                irm_an_fig.add_trace(go.Scatter(
                    x=_e["util"], y=_e["supply_deriv"], mode="lines",
                    name=f'{_e["name"]} Supply Deriv', line=dict(color=_col, width=2, dash="dash"),
                ), row=2, col=1)

    _h = 900 if irm_an_show_deriv.value and irm_an_active else 500
    irm_an_fig.update_xaxes(title_text="Utilization Rate (%)", range=[irm_an_util_min.value, irm_an_util_max.value])
    if irm_an_show_deriv.value and irm_an_active:
        irm_an_fig.update_yaxes(title_text="Interest Rate (%)", row=1, col=1)
        irm_an_fig.update_yaxes(title_text="Rate Change", row=2, col=1)
    else:
        irm_an_fig.update_yaxes(title_text="Interest Rate (%)")
    irm_an_fig = apply_style(irm_an_fig, height=_h)
    return (irm_an_fig,)


# --- Tab 7 assembly ---
@app.cell
def tab7_assembly(
    irm_an_active, irm_an_c1, irm_an_c2, irm_an_c3, irm_an_c4, irm_an_c5,
    irm_an_fig, irm_an_host, irm_an_reserve, irm_an_show_deriv,
    irm_an_show_supply, irm_an_slot_ms, irm_an_use_kamino,
    irm_an_util_max, irm_an_util_min, mo,
):
    # Summary table
    _summary = []
    for _e in irm_an_active:
        _summary.append(
            f'**{_e["name"]}**: '
            f'Max={max(_e["borrow"]):.2f}%, '
            f'Min={min(_e["borrow"]):.2f}%, '
            f'Avg={sum(_e["borrow"])/len(_e["borrow"]):.2f}%'
        )

    tab7_content = mo.vstack([
        mo.md("### Interest Rate Model Analyzer"),
        mo.md("Compare up to 5 IRM curves. Give a curve a name to activate it."),
        mo.hstack([irm_an_util_min, irm_an_util_max], justify="start", gap=1.5),
        mo.hstack([irm_an_show_deriv, irm_an_show_supply, irm_an_use_kamino], justify="start", gap=1.5),
        mo.hstack([irm_an_reserve, irm_an_host, irm_an_slot_ms], justify="start", gap=1.5),
        mo.accordion({
            "Curve 1": irm_an_c1,
            "Curve 2": irm_an_c2,
            "Curve 3": irm_an_c3,
            "Curve 4": irm_an_c4,
            "Curve 5": irm_an_c5,
        }),
        mo.as_html(irm_an_fig) if irm_an_active else mo.md(
            "Add at least one curve with a name to see the visualization."
        ),
        mo.md("\n\n".join(_summary)) if _summary else mo.md(""),
    ])
    return (tab7_content,)


# =====================================================================
# TAB 8: CAMPAIGN SIMULATION
# =====================================================================


# --- Tab 8 inputs ---
@app.cell
def tab8_inputs(mo):
    camp_init_cap = mo.ui.number(
        start=0.0, stop=10_000_000_000.0, step=100.0, value=100_000_000.0,
        debounce=True, label="Initial Capacity ($)",
    )
    camp_final_cap = mo.ui.number(
        start=0.0, stop=10_000_000_000.0, step=100.0, value=200_000_000.0,
        debounce=True, label="Final Capacity ($)",
    )
    camp_duration = mo.ui.number(
        start=1, stop=365, step=1, value=7,
        debounce=True, label="Duration (days)",
    )
    camp_epoch_hrs = mo.ui.number(
        start=0.5, stop=4.0, step=0.5, value=1.0,
        debounce=True, label="Epoch (hours)",
    )
    camp_c1 = mo.ui.dictionary({
        "name": mo.ui.text(value="Campaign 1", label="Name"),
        "budget": mo.ui.number(start=0.0, stop=100_000_000.0, step=100.0, value=100_000.0, debounce=True, label="Budget ($)"),
        "type": mo.ui.dropdown(
            options={"Variable Rate": "variable", "Fixed Rate": "fixed", "Capped Rate": "capped"},
            value="Variable Rate", label="Type",
        ),
        "target_rate": mo.ui.number(start=0.0, stop=100.0, step=0.5, value=5.0, debounce=True, label="Target Rate (%)"),
    })
    camp_c2 = mo.ui.dictionary({
        "name": mo.ui.text(value="", label="Name"),
        "budget": mo.ui.number(start=0.0, stop=100_000_000.0, step=100.0, value=0.0, debounce=True, label="Budget ($)"),
        "type": mo.ui.dropdown(
            options={"Variable Rate": "variable", "Fixed Rate": "fixed", "Capped Rate": "capped"},
            value="Variable Rate", label="Type",
        ),
        "target_rate": mo.ui.number(start=0.0, stop=100.0, step=0.5, value=5.0, debounce=True, label="Target Rate (%)"),
    })
    camp_c3 = mo.ui.dictionary({
        "name": mo.ui.text(value="", label="Name"),
        "budget": mo.ui.number(start=0.0, stop=100_000_000.0, step=100.0, value=0.0, debounce=True, label="Budget ($)"),
        "type": mo.ui.dropdown(
            options={"Variable Rate": "variable", "Fixed Rate": "fixed", "Capped Rate": "capped"},
            value="Variable Rate", label="Type",
        ),
        "target_rate": mo.ui.number(start=0.0, stop=100.0, step=0.5, value=5.0, debounce=True, label="Target Rate (%)"),
    })
    return camp_c1, camp_c2, camp_c3, camp_duration, camp_epoch_hrs, camp_final_cap, camp_init_cap


# --- Tab 8 compute ---
@app.cell
def tab8_compute(
    camp_c1, camp_c2, camp_c3, camp_duration, camp_epoch_hrs,
    camp_final_cap, camp_init_cap, simulate_campaigns,
):
    _active = []
    for _cv in [camp_c1, camp_c2, camp_c3]:
        _v = _cv.value
        if _v["name"] and _v["budget"] > 0:
            _active.append({
                "name": _v["name"],
                "budget": _v["budget"],
                "type": _v["type"],
                "target_rate": _v["target_rate"],
            })

    if _active:
        camp_results = simulate_campaigns(
            _active, camp_init_cap.value, camp_final_cap.value,
            camp_duration.value, camp_epoch_hrs.value,
        )
    else:
        camp_results = None
    return (camp_results,)


# --- Tab 8 charts ---
@app.cell
def tab8_charts(camp_results, apply_style, go, np):
    _colors = ["#e41a1c", "#377eb8", "#4daf4a"]

    camp_fig_rate = go.Figure()
    camp_fig_budget = go.Figure()

    if camp_results is not None:
        for _i, (_name, _data) in enumerate(camp_results["campaigns"].items()):
            _col = _colors[_i % len(_colors)]
            camp_fig_rate.add_trace(go.Scatter(
                x=camp_results["capacity"], y=_data["rates"],
                mode="lines", name=_name, stackgroup="one",
                fillcolor=_col, line=dict(width=0.5, color=_col),
                customdata=np.column_stack((camp_results["time"],)),
                hovertemplate="<b>%{fullData.name}</b><br>Capacity: %{x:,.0f}<br>"
                              "Time: %{customdata[0]:.2f} days<br>Rate: %{y:.2f}%<extra></extra>",
            ))
            camp_fig_budget.add_trace(go.Scatter(
                x=camp_results["time"], y=_data["budget_remaining"],
                mode="lines", name=_name, line=dict(width=2, color=_col),
            ))

    camp_fig_rate.update_layout(title="Total Incentive Rate vs Capacity")
    camp_fig_rate.update_xaxes(title_text="Capacity (TVL)", tickformat=",.0f")
    camp_fig_rate.update_yaxes(title_text="Annual Incentive Rate (%)")
    camp_fig_rate = apply_style(camp_fig_rate, height=450)

    camp_fig_budget.update_layout(title="Budget Consumption Over Time")
    camp_fig_budget.update_xaxes(title_text="Time (days)")
    camp_fig_budget.update_yaxes(title_text="Remaining Budget", tickformat=",.0f")
    camp_fig_budget = apply_style(camp_fig_budget, height=450)

    return camp_fig_budget, camp_fig_rate


# --- Tab 8 assembly ---
@app.cell
def tab8_assembly(
    camp_c1, camp_c2, camp_c3, camp_duration, camp_epoch_hrs,
    camp_fig_budget, camp_fig_rate, camp_final_cap, camp_init_cap,
    camp_results, mo, np,
):
    _summary = []
    if camp_results is not None:
        for _name, _data in camp_results["campaigns"].items():
            _avg = np.mean(_data["rates"])
            _max = np.max(_data["rates"])
            _used = _data["budget_remaining"][0] - _data["budget_remaining"][-1]
            _summary.append(
                f"**{_name}**: Avg Rate={_avg:.2f}%, Max Rate={_max:.2f}%, Budget Used=${_used:,.0f}"
            )

    _init_m = camp_init_cap.value / 1_000_000
    _fin_m = camp_final_cap.value / 1_000_000

    tab8_content = mo.vstack([
        mo.md("### Campaign Simulation"),
        mo.md(
            "Simulate multiple incentive campaigns with Variable, Fixed, or Capped rate strategies."
        ),
        mo.md(
            f"**Capacity:** ${_init_m:.1f}M -> ${_fin_m:.1f}M | "
            f"**Duration:** {camp_duration.value} days | "
            f"**Epoch:** {camp_epoch_hrs.value}h"
        ),
        mo.hstack([camp_init_cap, camp_final_cap, camp_duration, camp_epoch_hrs], justify="start", gap=1.5),
        mo.accordion({
            "Campaign 1": camp_c1,
            "Campaign 2": camp_c2,
            "Campaign 3": camp_c3,
        }),
        mo.as_html(camp_fig_rate) if camp_results else mo.md("Configure campaigns with a name and budget > 0 to see results."),
        mo.as_html(camp_fig_budget) if camp_results else mo.md(""),
        mo.md("\n\n".join(_summary)) if _summary else mo.md(""),
    ])
    return (tab8_content,)


# =====================================================================
# MAIN: TITLE + TABS
# =====================================================================


@app.cell
def main(
    mo, tab1_content, tab2_content, tab3_content,
    tab4_content, tab5_content, tab6_content, tab7_content, tab8_content,
):
    mo.output.replace(
        mo.vstack([
            mo.md("# Quick Formula Calculator"),
            mo.md(
                "Reactive DeFi formula tools: leveraged yield, price shocks, incentive dilution, "
                "liquidation analysis, interest rate models, and campaign simulation."
            ),
            mo.ui.tabs(
                {
                    "Leveraged Yield": tab1_content,
                    "Shock to LTV": tab2_content,
                    "Incentive Dilution": tab3_content,
                    "Euler Liquidation": tab4_content,
                    "Loan Liquidation Risk": tab5_content,
                    "Adaptive Curve IRM": tab6_content,
                    "IRM Analyzer": tab7_content,
                    "Campaign Simulation": tab8_content,
                },
                lazy=True,
            ),
        ])
    )
    return


if __name__ == "__main__":
    app.run()

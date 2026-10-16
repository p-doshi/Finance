import numpy as np
import pandas as pd
import pytest

from portfolio_pipeline.research.ic_analysis import (
    trailing_window_return,
    forward_window_return,
    composite_momentum_signal,
    information_coefficient,
    run_ic_study,
    summarize_ic,
)

RNG = np.random.default_rng(55)


def _synthetic_log_returns(n_days=400, n_assets=6, seed=55):
    rng = np.random.default_rng(seed)
    data = rng.normal(0.0003, 0.01, size=(n_days, n_assets))
    idx = pd.bdate_range("2023-01-02", periods=n_days)
    return pd.DataFrame(data, index=idx, columns=[f"T{i}" for i in range(n_assets)])


def test_trailing_window_return_known_value():
    log_ret = _synthetic_log_returns()
    as_of = 50
    window = 10
    r = trailing_window_return(log_ret, as_of, window)
    manual = np.expm1(log_ret.iloc[as_of - window + 1: as_of + 1].sum())
    pd.testing.assert_series_equal(r, manual, check_names=False)


def test_trailing_window_return_nan_with_gap_in_window():
    log_ret = _synthetic_log_returns()
    log_ret.iloc[45, 2] = np.nan  # a single gap inside the lookback window for ticker T2
    r = trailing_window_return(log_ret, as_of_idx=50, window=10)
    assert np.isnan(r["T2"])
    assert not np.isnan(r["T0"])  # untouched tickers are unaffected


def test_trailing_window_return_nan_when_insufficient_history():
    log_ret = _synthetic_log_returns()
    r = trailing_window_return(log_ret, as_of_idx=5, window=252)
    assert r.isna().all()


def test_forward_window_return_known_value():
    log_ret = _synthetic_log_returns()
    as_of, horizon = 50, 21
    r = forward_window_return(log_ret, as_of, horizon)
    manual = np.expm1(log_ret.iloc[as_of + 1: as_of + 1 + horizon].sum())
    pd.testing.assert_series_equal(r, manual, check_names=False)


def test_forward_window_return_nan_when_insufficient_future_data():
    log_ret = _synthetic_log_returns(n_days=100)
    r = forward_window_return(log_ret, as_of_idx=95, horizon=21)
    assert r.isna().all()


def test_composite_momentum_signal_matches_screen_module_logic():
    """Should match research.screen's own composite-rank construction
    (percentile rank average across horizons) exactly — this is meant to
    be the same signal, just evaluated at an arbitrary historical point."""
    log_ret = _synthetic_log_returns(n_days=400, n_assets=5)
    as_of = 300
    signal = composite_momentum_signal(log_ret, as_of, windows=(63, 126, 252))

    from portfolio_pipeline.research.screen import trailing_simple_return
    expected_ranks = []
    for w in (63, 126, 252):
        raw = pd.Series({t: trailing_simple_return(log_ret[t].iloc[:as_of + 1], w) for t in log_ret.columns})
        expected_ranks.append(raw.rank(pct=True) * 100)
    expected = pd.concat(expected_ranks, axis=1).mean(axis=1)
    pd.testing.assert_series_equal(signal.sort_index(), expected.sort_index(), check_names=False)


def test_information_coefficient_perfect_rank_correlation():
    # 12 names, >= the function's own min-names-for-a-meaningful-IC floor
    names = list("ABCDEFGHIJKL")
    signal = pd.Series(range(12, 0, -1), index=names)
    forward_return = pd.Series(sorted(RNG.uniform(0, 0.1, 12), reverse=True), index=names)  # same rank order
    ic, n = information_coefficient(signal, forward_return)
    assert n == 12
    assert ic == pytest.approx(1.0)


def test_information_coefficient_perfect_inverse_correlation():
    names = list("ABCDEFGHIJKL")
    signal = pd.Series(range(12, 0, -1), index=names)
    forward_return = pd.Series(sorted(RNG.uniform(0, 0.1, 12)), index=names)  # reversed rank order
    ic, n = information_coefficient(signal, forward_return)
    assert ic == pytest.approx(-1.0)


def test_information_coefficient_nan_with_too_few_names():
    signal = pd.Series([1.0, 2.0, 3.0], index=list("ABC"))
    forward_return = pd.Series([0.1, 0.2, 0.3], index=list("ABC"))
    ic, n = information_coefficient(signal, forward_return)
    assert np.isnan(ic)
    assert n == 3


def test_run_ic_study_no_lookahead():
    """The same discipline as walk_forward's own no-lookahead test:
    corrupting data after a cutoff must not change any snapshot's IC
    whose signal AND forward-return window are both entirely before the
    cutoff."""
    log_ret = _synthetic_log_returns(n_days=600, n_assets=15, seed=61)
    cutoff = 400
    corrupted = log_ret.copy()
    corrupted.iloc[cutoff:] = RNG.normal(0.05, 0.3, size=corrupted.iloc[cutoff:].shape)

    base_study = run_ic_study(log_ret, horizon=21, snapshot_every=63, min_lookback=252)
    corrupt_study = run_ic_study(corrupted, horizon=21, snapshot_every=63, min_lookback=252)

    checked_any = False
    for i, row in base_study.iterrows():
        as_of_idx = log_ret.index.get_loc(row["date"])
        if as_of_idx + 21 < cutoff:  # signal window AND forward window both untouched
            checked_any = True
            if np.isnan(row["ic"]):
                assert np.isnan(corrupt_study.loc[i, "ic"])
            else:
                assert corrupt_study.loc[i, "ic"] == pytest.approx(row["ic"])
    assert checked_any  # sanity: the cutoff must actually leave some untouched snapshots to compare


def test_summarize_ic_known_values():
    ic_df = pd.DataFrame({"ic": [0.10, 0.06, 0.08, 0.04]})
    s = summarize_ic(ic_df)
    vals = np.array([0.10, 0.06, 0.08, 0.04])
    assert s["mean_ic"] == pytest.approx(vals.mean())
    expected_se = vals.std(ddof=1) / np.sqrt(4)
    assert s["se_ic"] == pytest.approx(expected_se)
    assert s["t_stat"] == pytest.approx(vals.mean() / expected_se)
    assert s["ir_approx"] == pytest.approx(vals.mean() * np.sqrt(4))
    assert s["n_snapshots"] == 4


def test_summarize_ic_handles_nans_and_too_few_snapshots():
    ic_df = pd.DataFrame({"ic": [float("nan")]})
    s = summarize_ic(ic_df)
    assert np.isnan(s["mean_ic"])

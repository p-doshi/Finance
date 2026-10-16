import numpy as np
import pandas as pd
import pytest

from portfolio_pipeline.research.overfitting import (
    probabilistic_sharpe_ratio,
    expected_max_sharpe_under_null,
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
)

RNG = np.random.default_rng(99)


def test_psr_known_value_normal_returns():
    # hand-computed: sr_hat=0.1, sr_benchmark=0.0, n=100, skew=0, kurt=3 (normal)
    # denom = sqrt(1 - 0*0.1 + ((3-1)/4)*0.1^2) = sqrt(1 + 0.005) = sqrt(1.005)
    # z = 0.1 * sqrt(99) / sqrt(1.005)
    expected_z = 0.1 * np.sqrt(99) / np.sqrt(1.005)
    from scipy.stats import norm
    expected = norm.cdf(expected_z)
    got = probabilistic_sharpe_ratio(sr_hat=0.1, sr_benchmark=0.0, n_obs=100, skewness=0.0, kurtosis_raw=3.0)
    assert got == pytest.approx(expected)


def test_psr_increases_with_sr_hat():
    low = probabilistic_sharpe_ratio(0.05, 0.0, 100, 0.0, 3.0)
    high = probabilistic_sharpe_ratio(0.20, 0.0, 100, 0.0, 3.0)
    assert high > low


def test_psr_decreases_with_higher_benchmark():
    against_zero = probabilistic_sharpe_ratio(0.1, 0.0, 100, 0.0, 3.0)
    against_higher_bar = probabilistic_sharpe_ratio(0.1, 0.05, 100, 0.0, 3.0)
    assert against_higher_bar < against_zero


def test_expected_max_sharpe_zero_for_single_trial():
    assert expected_max_sharpe_under_null(n_trials=1, sharpe_variance=0.5) == 0.0
    assert expected_max_sharpe_under_null(n_trials=0, sharpe_variance=0.5) == 0.0


def test_expected_max_sharpe_zero_when_no_variance_across_trials():
    assert expected_max_sharpe_under_null(n_trials=10, sharpe_variance=0.0) == pytest.approx(0.0)


def test_expected_max_sharpe_increases_with_more_trials():
    """More trials tried under the null -> a higher bar for 'best observed
    Sharpe' to have been found by pure luck -- the whole point of the
    deflation."""
    b5 = expected_max_sharpe_under_null(n_trials=5, sharpe_variance=0.1)
    b50 = expected_max_sharpe_under_null(n_trials=50, sharpe_variance=0.1)
    b500 = expected_max_sharpe_under_null(n_trials=500, sharpe_variance=0.1)
    assert b5 < b50 < b500


def test_deflated_sharpe_equals_psr_against_zero_for_single_trial():
    rng = np.random.default_rng(1)
    rets = rng.normal(0.001, 0.01, size=200)
    result = deflated_sharpe_ratio({"only_trial": rets}, best_trial="only_trial")
    expected_psr = probabilistic_sharpe_ratio(
        result["sr_hat"], 0.0, result["n_obs"], result["skewness"], result["kurtosis_raw"])
    assert result["dsr"] == pytest.approx(expected_psr)
    assert result["n_trials"] == 1


def test_deflated_sharpe_decreases_with_more_competing_trials():
    """Same 'best' trial, but drawn from a larger pool of similarly-varied
    trials -> DSR should go down, since more trials means a higher chance
    the best one just got lucky."""
    rng = np.random.default_rng(2)
    best_rets = rng.normal(0.002, 0.01, size=200)

    few_trials = {"best": best_rets}
    for i in range(2):
        few_trials[f"other{i}"] = rng.normal(0.0005, 0.01, size=200)

    many_trials = dict(few_trials)
    for i in range(2, 30):
        many_trials[f"other{i}"] = rng.normal(0.0005, 0.01, size=200)

    dsr_few = deflated_sharpe_ratio(few_trials, best_trial="best")["dsr"]
    dsr_many = deflated_sharpe_ratio(many_trials, best_trial="best")["dsr"]
    assert dsr_many <= dsr_few


def test_pbo_rejects_odd_n_splits():
    returns = pd.DataFrame(RNG.normal(0, 0.01, size=(24, 3)))
    with pytest.raises(ValueError, match="even"):
        probability_of_backtest_overfitting(returns, n_splits=7)


def test_pbo_rejects_non_divisible_periods():
    returns = pd.DataFrame(RNG.normal(0, 0.01, size=(25, 3)))
    with pytest.raises(ValueError, match="divisible"):
        probability_of_backtest_overfitting(returns, n_splits=8)


def test_pbo_near_half_for_pure_noise_with_no_true_skill_difference():
    """All strategies drawn from the identical distribution -- no real
    skill differences -- should show PBO close to 0.5: picking the
    in-sample winner is no better than a coin flip at finding the OOS
    winner, by symmetry."""
    rng = np.random.default_rng(3)
    returns = pd.DataFrame(rng.normal(0.0005, 0.01, size=(240, 6)))
    result = probability_of_backtest_overfitting(returns, n_splits=8)
    assert 0.3 < result["pbo"] < 0.7
    assert result["n_combinations"] > 0


def test_pbo_near_zero_when_one_strategy_truly_dominates():
    """One strategy has a much higher true mean return every period;
    nothing about it is a fluke of a particular split, so it should win
    both in-sample and out-of-sample almost every combination -> low PBO."""
    rng = np.random.default_rng(4)
    t = 240
    dominant = rng.normal(0.02, 0.005, size=t)       # consistently strong
    weak = {f"weak{i}": rng.normal(0.0001, 0.005, size=t) for i in range(5)}
    returns = pd.DataFrame({"dominant": dominant, **weak})
    result = probability_of_backtest_overfitting(returns, n_splits=8)
    assert result["pbo"] < 0.15


def test_pbo_deterministic():
    returns = pd.DataFrame(RNG.normal(0, 0.01, size=(24, 4)))
    r1 = probability_of_backtest_overfitting(returns, n_splits=8)
    r2 = probability_of_backtest_overfitting(returns, n_splits=8)
    assert r1 == r2

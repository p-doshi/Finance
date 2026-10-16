import numpy as np
import pytest

from portfolio_pipeline.risk.controls import cap_weights, volatility_target_scale

RNG = np.random.default_rng(13)


def test_cap_weights_no_change_when_already_under_cap():
    w = np.array([0.3, 0.3, 0.4])
    capped = cap_weights(w, max_weight=0.5)
    np.testing.assert_allclose(capped, w)


def test_cap_weights_single_breach_redistributes_and_sums_to_one():
    w = np.array([0.6, 0.2, 0.2])
    capped = cap_weights(w, max_weight=0.4)
    assert capped[0] == pytest.approx(0.4)
    assert capped.sum() == pytest.approx(1.0)
    # the 0.2 excess from asset 0 split proportionally between the other two (equal weights -> equal split)
    assert capped[1] == pytest.approx(0.3)
    assert capped[2] == pytest.approx(0.3)


def test_cap_weights_requires_iteration_when_redistribution_creates_new_breach():
    """0.50 capped to 0.25 dumps 0.25 excess across [0.20,0.15,0.10,0.05]
    (proportional to each name's own weight) -- the largest of those
    (0.20) receives enough in one pass to go over 0.25 itself, requiring a
    second iteration. (5 names at a 0.25 cap is feasible: 5*0.25=1.25>=1.)
    A capped-from-pass-1 name must also never get pushed over the cap
    again in a later pass -- the actual bug this test caught."""
    w = np.array([0.50, 0.20, 0.15, 0.10, 0.05])
    result = cap_weights(w, max_weight=0.25)
    assert result.sum() == pytest.approx(1.0, abs=1e-9)
    assert np.all(result <= 0.25 + 1e-9)


def test_cap_weights_rejects_infeasible_cap():
    w = np.array([0.5, 0.3, 0.2])
    with pytest.raises(ValueError, match="infeasible"):
        cap_weights(w, max_weight=0.1)  # 0.1*3=0.3 < 1.0, can't reach 100%


def test_cap_weights_random_cases_always_sum_to_one_and_respect_cap():
    for _ in range(20):
        n = RNG.integers(3, 15)
        w = RNG.dirichlet(np.ones(n))
        max_weight = max(1.0 / n, float(RNG.uniform(0.15, 0.6)))
        capped = cap_weights(w, max_weight=max_weight)
        assert capped.sum() == pytest.approx(1.0, abs=1e-6)
        assert np.all(capped <= max_weight + 1e-6)


def test_volatility_target_scale_known_value():
    assert volatility_target_scale(realized_vol=0.20, target_vol=0.10) == pytest.approx(0.5)


def test_volatility_target_scale_capped_at_max_leverage_by_default():
    # realized vol way below target would imply scale=2.0, but default max_leverage=1.0
    assert volatility_target_scale(realized_vol=0.05, target_vol=0.10) == pytest.approx(1.0)


def test_volatility_target_scale_allows_explicit_higher_leverage():
    assert volatility_target_scale(realized_vol=0.05, target_vol=0.10, max_leverage=2.0) == pytest.approx(2.0)


def test_volatility_target_scale_handles_zero_realized_vol():
    assert volatility_target_scale(realized_vol=0.0, target_vol=0.10) == 1.0


def test_volatility_target_scale_never_negative():
    assert volatility_target_scale(realized_vol=0.30, target_vol=0.0) == pytest.approx(0.0)

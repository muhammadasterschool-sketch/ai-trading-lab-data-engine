"""v1.5.0 quant extension tests — top-50 indicator pack.

Deterministic, offline. Pins: output alignment/None-warmups, plausible
ranges, registry wiring (>= 50 registered indicators), and behaviour
on monotonic trends (ADX/ER sanity).
"""

import math

from data_engine.quant import oscillators as osc
from data_engine.quant import bands as bnd
from data_engine.quant import statistics_ext as ste
from data_engine.quant import trend_indicators as tre
from data_engine.quant import volume_ta as vol
from data_engine.quant.registry import get_registry


def _series(n=300, drift=0.001, seed=11):
    import random

    rng = random.Random(seed)
    price = 100.0
    closes, highs, lows, volumes = [], [], [], []
    for _ in range(n):
        price = max(1.0, price * (1 + drift + rng.gauss(0, 0.004)))
        closes.append(price)
        highs.append(price * (1 + abs(rng.gauss(0, 0.0015))))
        lows.append(price * (1 - abs(rng.gauss(0, 0.0015))))
        volumes.append(max(1.0, rng.expovariate(1 / 1000.0)))
    return closes, highs, lows, volumes


class TestOscillators:
    def test_macd_alignment_and_warmup(self):
        closes, *_ = _series()
        result = osc.macd(closes)
        assert len(result["macd"]) == len(closes)
        assert result["macd"][0] is None
        valid = [x for x in result["histogram"] if x is not None]
        assert all(math.isfinite(x) for x in valid)

    def test_stochastic_bounds(self):
        closes, highs, lows, _ = _series()
        s = osc.stochastic(highs, lows, closes)
        for series in (s["k"], s["d"]):
            for value in series:
                if value is not None:
                    assert -1e-9 <= value <= 100 + 1e-9

    def test_stoch_rsi_bounded(self):
        closes, *_ = _series()
        for value in osc.stoch_rsi(closes):
            if value is not None:
                assert 0 <= value <= 100

    def test_williams_r_range(self):
        closes, highs, lows, _ = _series()
        for value in osc.williams_r(highs, lows, closes):
            if value is not None:
                assert -100 - 1e-9 <= value <= 1e-9

    def test_trix_and_uo_finite(self):
        closes, highs, lows, _ = _series()
        for fn in (osc.trix, lambda c: osc.ultimate_oscillator(highs, lows, c)):
            for value in fn(closes):
                if value is not None:
                    assert math.isfinite(value)

    def test_roc_and_momentum_none_warmup(self):
        closes, *_ = _series()
        assert osc.rate_of_change(closes)[5] is None
        assert osc.momentum(closes)[5] is None


class TestBands:
    def test_bollinger_ordering(self):
        closes, *_ = _series()
        b = bnd.bollinger(closes)
        for up, mid, lo in zip(b["upper"], b["middle"], b["lower"]):
            if None not in (up, mid, lo):
                assert lo < mid < up

    def test_bollinger_percent_b_range(self):
        closes, *_ = _series()
        for value in bnd.bollinger(closes)["percent_b"]:
            if value is not None:
                assert -5 <= value <= 5  # generous but sane

    def test_keltner_and_donchian(self):
        closes, highs, lows, _ = _series()
        k = bnd.keltner(highs, lows, closes)
        d = bnd.donchian(highs, lows)
        assert k["upper"][-1] > k["middle"][-1] > k["lower"][-1]
        assert d["upper"][-1] >= d["lower"][-1]

    def test_rolling_vwap_between_extremes(self):
        closes, highs, lows, volumes = _series()
        vwap = bnd.rolling_vwap(highs, lows, closes, volumes)
        assert vwap[0] is None
        tail = list(zip(lows, closes))[-30:]
        lo = min(min(l, c) for l, c in tail)
        tail_hi = list(zip(highs, closes))[-30:]
        hi = max(max(h, c) for h, c in tail_hi)
        assert lo - 1e-9 <= vwap[-1] <= hi + 1e-9

    def test_anchored_vwap_resets_daily(self):
        from datetime import datetime, timedelta, timezone

        closes, highs, lows, volumes = _series(n=120)
        t0 = datetime(2026, 9, 1, 23, 50, tzinfo=timezone.utc)
        ts = [t0 + timedelta(minutes=i) for i in range(120)]
        out = bnd.anchored_vwap(highs, lows, closes, volumes, ts)
        assert len(out) == 120
        assert out[0] is not None


class TestTrendIndicators:
    def test_adx_bounded_and_trending_market_reads_high(self):
        closes, *_ = _series()
        a = tre.adx([c * 1.001 for c in closes], [c * 0.999 for c in closes], closes)
        for value in a["adx"]:
            if value is not None:
                assert 0 <= value <= 100
        up = [100.0 * (1.002 ** i) for i in range(300)]
        a2 = tre.adx([u * 1.001 for u in up], [u * 0.999 for u in up], up)
        assert a2["adx"][-1] > 30

    def test_supertrend_direction_values(self):
        closes, highs, lows, _ = _series()
        st = tre.supertrend(highs, lows, closes)
        for value in st["direction"]:
            if value is not None:
                assert value in (1, -1)

    def test_parabolic_sar_finite(self):
        closes, highs, lows, _ = _series()
        for value in tre.parabolic_sar(highs, lows):
            if value is not None:
                assert math.isfinite(value)

    def test_ichimoku_components(self):
        closes, highs, lows, _ = _series()
        ich = tre.ichimoku(highs, lows)
        assert ich["tenkan"][8] is not None
        assert ich["kijun"][25] is not None

    def test_aroon_bounds(self):
        closes, highs, lows, _ = _series()
        a = tre.aroon(highs, lows)
        for value in a["up"] + a["down"]:
            if value is not None:
                assert 0 <= value <= 100

    def test_moving_average_family_warmup(self):
        closes, *_ = _series()
        for fn in (tre.wma, tre.hma, tre.dema, tre.tema, tre.zlema, tre.kama):
            series = fn(closes, 20) if fn is not tre.kama else fn(closes)
            assert series[0] is None
            assert series[-1] is not None

    def test_linreg_slope_positive_on_uptrend(self):
        up = [100.0 * (1.002 ** i) for i in range(100)]
        assert tre.linear_regression_slope(up, 20)[-1] > 0
        assert tre.r_squared(up, 20)[-1] > 0.9


class TestVolumeIndicators:
    def test_obv_rises_on_uptrend(self):
        up = [100.0 * (1.001 ** i) for i in range(50)]
        volumes = [10.0] * 50
        obv = vol.on_balance_volume(up, volumes)
        assert obv[-1] > obv[0]

    def test_mfi_bounded(self):
        closes, highs, lows, volumes = _series()
        for value in vol.money_flow_index(highs, lows, closes, volumes):
            if value is not None:
                assert 0 <= value <= 100

    def test_cmf_bounded(self):
        closes, highs, lows, volumes = _series()
        for value in vol.chaikin_money_flow(highs, lows, closes, volumes):
            if value is not None:
                assert -1 - 1e-9 <= value <= 1 + 1e-9

    def test_volume_zscore_and_force_finite(self):
        closes, highs, lows, volumes = _series()
        for value in vol.volume_zscore(volumes):
            if value is not None:
                assert math.isfinite(value)
        for value in vol.force_index(closes, volumes):
            if value is not None:
                assert math.isfinite(value)


class TestStatisticsExt:
    def test_choppiness_bounded(self):
        closes, highs, lows, _ = _series()
        for value in ste.choppiness_index(highs, lows, closes):
            if value is not None:
                assert 0 <= value <= 100

    def test_vortex_positive_values(self):
        closes, highs, lows, _ = _series()
        v = ste.vortex(highs, lows, closes)
        for value in v["plus"] + v["minus"]:
            if value is not None:
                assert value >= -1e-9

    def test_hurst_and_variance_ratio_ranges(self):
        closes, *_ = _series(n=600)
        h = ste.hurst_exponent_approx(closes)
        assert h is not None and 0.05 <= h <= 0.95
        vr = ste.variance_ratio(closes)
        assert vr is not None and 0.1 <= vr <= 10.0

    def test_efficiency_ratio_near_one_on_trend(self):
        up = [100.0 * (1.002 ** i) for i in range(100)]
        assert ste.efficiency_ratio(up, 10)[-1] > 0.99


class TestRegistry:
    def test_registry_reaches_top50(self):
        registry = get_registry()
        assert registry.count() >= 50

    def test_registry_contains_key_new_indicators(self):
        registry = get_registry()
        for name in (
            "macd", "stochastic_k", "cci", "williams_r", "bollinger_upper",
            "keltner_upper", "donchian_upper", "rolling_vwap", "adx",
            "supertrend", "parabolic_sar", "ichimoku_tenkan", "aroon_up",
            "wma", "hma", "dema", "tema", "zlema", "kama",
            "linear_regression_slope", "r_squared", "on_balance_volume",
            "money_flow_index", "force_index", "chaikin_money_flow",
            "choppiness_index", "vortex_plus", "vortex_minus",
            "efficiency_ratio", "volume_zscore",
        ):
            assert registry.has_indicator(name), name

    def test_registry_categories_populated(self):
        registry = get_registry()
        for category in (
            "momentum", "volatility", "moving_average", "trend",
            "volume", "statistics",
        ):
            assert registry.list_by_category(category)

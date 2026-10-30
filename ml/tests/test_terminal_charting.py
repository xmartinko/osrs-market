import math

import pytest

from osrs_ml.server.charting import (
    STYLES,
    aggregate,
    bollinger,
    chart,
    collapse_labels,
    comparison,
    ema,
    heikin_ashi,
    kagi,
    line_break,
    macd,
    mean_envelopes,
    point_figure,
    renko,
    rsi,
    scale,
    sma,
    treemap,
    vwap,
)


def rows(values):
    return mean_envelopes(
        [dict(timestamp=i * 300, close=v, volume=i + 1) for i, v in enumerate(values)]
    )


def test_sma_and_seeded_ema():
    assert sma([1, 2, 3, 4], 3) == [None, None, 2, 3]
    assert ema([1, 2, 3, 7], 3) == [None, None, 2, 4.5]
    assert sma([], 3) == ema([], 3) == []


def test_bollinger_population_deviation():
    b = bollinger([1, 2, 3], 3)
    assert b["BOLL mid"][-1] == 2
    assert b["BOLL upper"][-1] == pytest.approx(2 + 2 * math.sqrt(2 / 3))
    assert b["BOLL lower"][-1] == pytest.approx(2 - 2 * math.sqrt(2 / 3))


def test_wilder_rsi_flat_gain_loss_and_reference():
    assert rsi([2] * 20)[14:] == [50] * 6
    assert rsi(list(range(20)))[14:] == [100] * 6
    assert rsi(list(range(20, 0, -1)))[14:] == [0] * 6
    values = [
        44.34,
        44.09,
        44.15,
        43.61,
        44.33,
        44.83,
        45.10,
        45.42,
        45.84,
        46.08,
        45.89,
        46.03,
        45.61,
        46.28,
        46.28,
        46.00,
    ]
    assert rsi(values)[14] == pytest.approx(70.464135, abs=1e-5)
    assert rsi(values)[15] == pytest.approx(66.249619, abs=1e-5)


def test_macd_seed_and_signal_histogram():
    m = macd(list(range(1, 51)))
    assert m["MACD"][:25] == [None] * 25
    assert m["MACD"][25:] == pytest.approx([7] * 25)
    assert m["Signal"][:33] == [None] * 33
    assert m["Signal"][33:] == pytest.approx([7] * 17)
    assert m["Histogram"][33:] == pytest.approx([0] * 17)


def test_vwap_ignores_absent_and_zero_volume():
    assert vwap([10, 20, 100, 30], [0, 2, None, 1]) == [None, 20, 20, 70 / 3]


@pytest.mark.parametrize(
    "mode,expected",
    [("linear", 110), ("percent", 10), ("indexed", 110), ("logarithmic", math.log10(110))],
)
def test_scales(mode, expected):
    assert scale(110, mode, 100) == pytest.approx(expected)
    with pytest.raises(ValueError):
        scale(0, "logarithmic", 100)


def test_aggregate_is_ohlc_of_means_only():
    a = aggregate(rows([10, 14, 8, 12]), 900)
    assert (a[0]["open"], a[0]["high"], a[0]["low"], a[0]["close"]) == (10, 14, 8, 8)
    assert a[0]["volume"] == 6


def test_heikin_ashi_recurrence():
    ha = heikin_ashi(rows([10, 14, 8]))
    assert ha[0]["open"] == ha[0]["close"] == 10
    assert ha[1]["close"] == 12
    assert ha[2]["open"] == 11


def test_renko_two_box_reversal_and_noise():
    bricks = renko([100, 102, 103, 102, 101, 98], 2)
    assert [(b["open"], b["close"]) for b in bricks] == [(100, 102), (100, 98)]
    assert renko([100, 101, 100], 2) == []
    with pytest.raises(ValueError):
        renko([1, 2], 0)


def test_kagi_ignores_subthreshold_reversals():
    legs = kagi([100, 110, 108, 109, 105, 102], 5)
    assert [x["close"] for x in legs] == [100, 110, 102]


def test_point_figure_three_box_reversal():
    cols = point_figure([100, 104, 102, 101, 106], 1)
    assert [(c["direction"], c["close"]) for c in cols] == [(1, 104), (-1, 101), (1, 106)]
    with pytest.raises(ValueError):
        point_figure([1, 2], 0)


def test_three_line_break_reversal():
    lines = line_break([10, 11, 12, 13, 12, 11, 9])
    assert [r["close"] for r in lines] == [11, 12, 13, 9]


@pytest.mark.parametrize("style", STYLES)
def test_all_styles_produce_finite_geometry(style):
    c = chart(
        rows([100, 110, 106, 112, 103, 97, 105] * 8),
        style,
        indicators=["SMA", "EMA", "BOLL", "RSI", "MACD", "VWAP"],
    )
    assert c["lines"] or c["rects"] or c["glyphs"]
    assert all(math.isfinite(v) for line in c["lines"] for v in line[:4])
    assert len(c["panes"]) == 2
    assert c["bounds"][0] < c["bounds"][1]


def test_invert_fixed_bounds_and_label_collision():
    c = chart(rows([100, 110]), mode="percent", invert=True, fixed_bounds=[-20, 5])
    assert c["bounds"] == [-20, 5]
    assert c["lines"][0][3] == pytest.approx(-10)
    assert len(collapse_labels([("LAST", 1), ("HIGH", 1), ("LOW", 1)], 0, 2, 10)) == 1


def test_comparison_exact_common_start_without_filling():
    a = [dict(timestamp=t, close=p) for t, p in [(1, 10), (2, 20), (4, 40)]]
    b = [dict(timestamp=t, close=p) for t, p in [(2, 5), (3, 9), (4, 10)]]
    c = comparison({"a": a, "b": b})
    assert c[0]["points"] == [[2, 100], [4, 200]]
    assert c[1]["points"] == [[2, 100], [4, 200]]
    assert comparison({"a": a, "b": []}) == []


@pytest.mark.parametrize("width,height", [(80, 20), (1, 1), (1, 20), (30, 1), (0, 0)])
def test_treemap_tiles_without_overlap(width, height):
    cells = treemap([dict(volume=v, name=str(v)) for v in range(1, 15)], width, height)
    occupied = set()
    for c in cells:
        assert c["width"] > 0 and c["height"] > 0
        for x in range(c["x"], c["x"] + c["width"]):
            for y in range(c["y"], c["y"] + c["height"]):
                assert (x, y) not in occupied
                occupied.add((x, y))
    assert len(occupied) == width * height


def test_kagi_monotone_series_keeps_initial_anchor():
    assert [r["close"] for r in kagi([100, 110, 120], 5)] == [100, 120]
    assert chart(rows([100, 110, 120]), "Kagi")["lines"]


def test_price_only_autofit_excludes_extreme_studies():
    data = rows([100] * 20 + [200])
    price = chart(data, indicators=["BOLL"], price_only=True)
    all_studies = chart(data, indicators=["BOLL"], price_only=False)
    assert price["bounds"][0] > all_studies["bounds"][0]

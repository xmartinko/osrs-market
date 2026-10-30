"""Pure chart mathematics. Inputs are observations, never invented trade prints."""

import math
from collections import defaultdict
from statistics import fmean, pstdev

STYLES = (
    "Candles",
    "Bars",
    "Line",
    "Area",
    "Baseline",
    "Heikin Ashi",
    "Hollow Candles",
    "Renko",
    "Kagi",
    "Point & Figure",
    "Line Break",
)
SCALES = ("linear", "percent", "indexed", "logarithmic")
RESOLUTIONS = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "1d": 86400, "1w": 604800}
RANGES = {"5y": 1826, "1y": 365, "6m": 183, "3m": 92, "1m": 31, "5d": 5, "1d": 1}


def sma(values, period=20):
    return [
        None if i + 1 < period else fmean(values[i + 1 - period : i + 1])
        for i in range(len(values))
    ]


def ema(values, period=20):
    result, current = [], None
    for i, value in enumerate(values):
        if i + 1 < period:
            result.append(None)
            continue
        current = (
            fmean(values[:period])
            if current is None
            else (value * 2 / (period + 1) + current * (1 - 2 / (period + 1)))
        )
        result.append(current)
    return result


def bollinger(values, period=20):
    middle = sma(values, period)
    return {
        "BOLL mid": middle,
        "BOLL upper": [
            None if m is None else m + 2 * pstdev(values[i + 1 - period : i + 1])
            for i, m in enumerate(middle)
        ],
        "BOLL lower": [
            None if m is None else m - 2 * pstdev(values[i + 1 - period : i + 1])
            for i, m in enumerate(middle)
        ],
    }


def rsi(values, period=14):
    out = [None] * len(values)
    if len(values) <= period:
        return out
    changes = [b - a for a, b in zip(values, values[1:])]
    gain = fmean(max(0, x) for x in changes[:period])
    loss = fmean(max(0, -x) for x in changes[:period])
    for i in range(period, len(values)):
        if i > period:
            gain = (gain * (period - 1) + max(0, changes[i - 1])) / period
            loss = (loss * (period - 1) + max(0, -changes[i - 1])) / period
        out[i] = 100 - 100 / (1 + gain / loss) if loss else (100.0 if gain else 50.0)
    return out


def macd(values):
    fast, slow = ema(values, 12), ema(values, 26)
    line = [None if b is None else a - b for a, b in zip(fast, slow)]
    available = [v for v in line if v is not None]
    signal = [None] * (len(values) - len(available)) + ema(available, 9)
    return {
        "MACD": line,
        "Signal": signal,
        "Histogram": [None if s is None else v - s for v, s in zip(line, signal)],
    }


def vwap(values, volumes):
    """Cumulative volume-weighted bucket mean, not trade VWAP or daily session VWAP."""
    total, weight, out = 0.0, 0.0, []
    for value, volume in zip(values, volumes, strict=True):
        if volume is not None and volume > 0:
            total += value * volume
            weight += volume
        out.append(total / weight if weight else None)
    return out


def scale(value, mode, base):
    if mode == "percent":
        return 100 * (value / base - 1)
    if mode == "indexed":
        return 100 * value / base
    if mode == "logarithmic":
        if value <= 0:
            raise ValueError("Logarithmic scale requires positive prices")
        return math.log10(value)
    return value


def mean_envelopes(rows):
    result, previous = [], None
    for r in rows:
        close = r["close"]
        opening = close if previous is None else previous
        result.append(
            {
                **r,
                "open": opening,
                "high": max(opening, close, r.get("high", close)),
                "low": min(opening, close, r.get("low", close)),
            }
        )
        previous = close
    return result


def aggregate(rows, seconds):
    """OHLC of observed bucket MEANS. This cannot recover trade OHLC."""
    groups = defaultdict(list)
    for r in rows:
        groups[r["timestamp"] // seconds * seconds].append(r)
    result = []
    for stamp, group in sorted(groups.items()):
        closes = [r["close"] for r in group]
        result.append(
            dict(
                timestamp=stamp,
                open=closes[0],
                close=closes[-1],
                high=max(closes),
                low=min(closes),
                volume=sum(r.get("volume", 0) or 0 for r in group),
            )
        )
    return result


def heikin_ashi(rows):
    out = []
    for r in rows:
        close = (r["open"] + r["high"] + r["low"] + r["close"]) / 4
        opening = (out[-1]["open"] + out[-1]["close"]) / 2 if out else (r["open"] + r["close"]) / 2
        out.append(
            {
                **r,
                "open": opening,
                "close": close,
                "high": max(r["high"], opening, close),
                "low": min(r["low"], opening, close),
            }
        )
    return out


def renko(values, box):
    """Close-only bricks, two-box reversal. Index maps each brick to its source bar."""
    if box <= 0:
        raise ValueError("Box size must be positive")
    if not values:
        return []
    level, direction, result = values[0], 0, []
    for i, price in enumerate(values[1:], 1):
        sign = 1 if price > level else -1
        distance = (price - level) * sign
        if direction and sign != direction:
            if distance < 2 * box:
                continue
            level += sign * box
        # Bound pathological user box sizes; never silently truncate a chart.
        count = int((price - level) * sign / box + 1e-9)
        if len(result) + count > 10000:
            raise ValueError("Box too small: more than 10,000 bricks; increase box size")
        for _ in range(count):
            new = level + sign * box
            result.append(
                dict(index=i, open=level, close=new, high=max(level, new), low=min(level, new))
            )
            level, direction = new, sign
    return result


def kagi(values, reversal):
    """Close-only Kagi legs; reverse only after the absolute reversal threshold."""
    if reversal <= 0:
        raise ValueError("Reversal must be positive")
    if not values:
        return []
    result = [dict(index=0, close=values[0], direction=0)]
    direction, extreme = 0, values[0]
    for i, price in enumerate(values[1:], 1):
        sign = 1 if price > extreme else -1
        if direction == 0 or sign == direction:
            if price != extreme:
                direction, extreme = sign, price
                result[-1] = dict(index=i, close=price, direction=direction)
        elif abs(price - extreme) >= reversal:
            direction, extreme = sign, price
            result.append(dict(index=i, close=price, direction=direction))
    return result


def point_figure(values, box, reversal=3):
    """Close-only P&F columns with fixed box and three-box reversals."""
    if box <= 0 or reversal < 1:
        raise ValueError("Positive box and reversal required")
    if not values:
        return []
    anchor = math.floor(values[0] / box) * box
    columns, direction, level = [], 0, anchor
    for i, price in enumerate(values[1:], 1):
        sign = 1 if price > level else -1
        steps = int(abs(price - level) / box + 1e-9)
        if not steps or (direction and sign != direction and steps < reversal):
            continue
        if not direction or sign != direction:
            columns.append(dict(index=i, open=level + sign * box, close=level, direction=sign))
        level += sign * steps * box
        direction = sign
        columns[-1].update(index=i, close=level)
    return columns


def line_break(values, count=3):
    lines = []
    if not values:
        return lines
    for i, price in enumerate(values[1:], 1):
        opening = lines[-1]["close"] if lines else values[0]
        recent = lines[-count:]
        hi = max((max(x["open"], x["close"]) for x in recent), default=opening)
        lo = min((min(x["open"], x["close"]) for x in recent), default=opening)
        direction = 1 if price > opening else -1
        same = bool(lines) and (lines[-1]["close"] > lines[-1]["open"]) == (direction > 0)
        if price != opening and (same or price > hi or price < lo):
            lines.append(
                dict(
                    index=i,
                    open=opening,
                    close=price,
                    high=max(price, opening),
                    low=min(price, opening),
                )
            )
    return lines


def treemap(items, width, height, x=0, y=0):
    """Deterministic binary treemap in terminal cells; no overlap and exact tiling."""
    items = [i for i in items if i.get("volume", 0) > 0]
    if not items or width < 1 or height < 1:
        return []
    if len(items) == 1 or width * height == 1:
        return [dict(x=x, y=y, width=width, height=height, item=items[0])]
    total = sum(i["volume"] for i in items)
    split, subtotal = 1, items[0]["volume"]
    while split < len(items) - 1 and subtotal < total / 2:
        subtotal += items[split]["volume"]
        split += 1
    horizontal = width >= height * 2 or height == 1
    extent = width if horizontal else height
    if extent < 2:
        horizontal, extent = not horizontal, height if horizontal else width
    cut = max(1, min(extent - 1, round(extent * subtotal / total)))
    if horizontal:
        return treemap(items[:split], cut, height, x, y) + treemap(
            items[split:], width - cut, height, x + cut, y
        )
    return treemap(items[:split], width, cut, x, y) + treemap(
        items[split:], width, height - cut, x, y + cut
    )


def collapse_labels(labels, low, high, height):
    """Group colliding y-axis labels; first label (last price) has priority."""
    grouped = {}
    for name, value in labels:
        row = round((high - value) / (high - low) * max(0, height - 1))
        row = max(0, min(height - 1, row))
        grouped.setdefault(row, []).append(name)
    return [dict(row=r, text=" / ".join(names)) for r, names in sorted(grouped.items())]


def comparison(series):
    """Exact shared timestamps only. No filling absent prices or claiming dividends."""
    if not series:
        return []
    shared = set.intersection(*(set(r["timestamp"] for r in rows) for rows in series.values()))
    times = sorted(shared)
    if not times:
        return []
    result = []
    for name, rows in series.items():
        lookup = {r["timestamp"]: r["close"] for r in rows}
        base = lookup[times[0]]
        result.append(dict(name=name, points=[[t, lookup[t] / base * 100] for t in times]))
    return result


def chart(
    rows,
    style="Line",
    mode="linear",
    indicators=(),
    invert=False,
    height=24,
    width=100,
    lock=False,
    fixed_bounds=None,
    box=None,
):
    """Prepare all geometry and studies for a rendering-only terminal client."""
    if style not in STYLES or mode not in SCALES:
        raise ValueError("Unknown style or scale")
    if not rows:
        return dict(lines=[], rects=[], glyphs=[], labels=[], panes=[], bounds=[0, 1], count=1)
    values = [r["close"] for r in rows]
    base = values[0]
    project = lambda v: scale(v, mode, base) * (-1 if invert else 1)
    box = box or max((max(values) - min(values)) / 30, abs(base) * 0.002, 0.01)
    transformed = rows
    if style == "Heikin Ashi":
        transformed = heikin_ashi(rows)
    elif style == "Renko":
        transformed = renko(values, box)
    elif style == "Kagi":
        transformed = kagi(values, box * 3)
    elif style == "Point & Figure":
        transformed = point_figure(values, box)
    elif style == "Line Break":
        transformed = line_break(values)
    lines, rects, glyphs, overlays, panes = [], [], [], {}, []

    def segment(x1, y1, x2, y2, color="cyan"):
        lines.append([x1, project(y1), x2, project(y2), color])

    previous = None
    event_style = style in ("Renko", "Kagi", "Point & Figure", "Line Break")
    for i, r in enumerate(transformed):
        c, o = r["close"], r.get("open", r["close"])
        color = "green" if c >= o else "red"
        if style in ("Line", "Area", "Baseline", "Kagi"):
            if previous is not None:
                if style == "Kagi":
                    segment(i - 1, previous, i, previous, color)
                    segment(i, previous, i, c, color)
                else:
                    segment(
                        i - 1,
                        previous,
                        i,
                        c,
                        "green"
                        if style == "Baseline" and c >= base
                        else "red"
                        if style == "Baseline"
                        else "cyan",
                    )
            if style in ("Area", "Baseline"):
                segment(
                    i,
                    base if style == "Baseline" else min(values),
                    i,
                    c,
                    "green" if c >= base else "red",
                )
        elif style == "Point & Figure":
            steps = round(abs(c - o) / box)
            if steps > 10000:
                raise ValueError("Box too small for P&F")
            for j in range(steps + 1):
                glyphs.append(
                    [
                        i,
                        project(o + (box * j if c >= o else -box * j)),
                        "X" if r["direction"] > 0 else "O",
                        "green" if r["direction"] > 0 else "red",
                    ]
                )
        else:
            h, low = r.get("high", max(o, c)), r.get("low", min(o, c))
            if style != "Bars":
                segment(i, low, i, h, color)
            if style == "Bars":
                # Close-only bars are one-dimensional range ticks, not invented OHLC.
                segment(i - 0.3, c, i + 0.3, c, "cyan")
            else:
                rects.append(
                    [
                        i - 0.3,
                        min(project(o), project(c)),
                        0.6,
                        abs(project(c) - project(o)),
                        color,
                        style != "Hollow Candles" or c < o,
                    ]
                )
        previous = c
    if "SMA" in indicators:
        overlays["SMA 20"] = sma(values)
    if "EMA" in indicators:
        overlays["EMA 20"] = ema(values)
    if "BOLL" in indicators:
        overlays.update(bollinger(values))
    if "VWAP" in indicators:
        overlays["VWAP bucket"] = vwap(values, [r.get("volume") for r in rows])
    study_labels = []
    for name, points in overlays.items():
        # Event charts map each study to the source bar that generated the event.
        plotted = [points[r["index"]] for r in transformed] if event_style else points
        for i in range(1, len(plotted)):
            if plotted[i - 1] is not None and plotted[i] is not None:
                segment(i - 1, plotted[i - 1], i, plotted[i], "yellow")
        if plotted and plotted[-1] is not None:
            study_labels.append((f"{name} {plotted[-1]:.2f}", project(plotted[-1])))
    if "RSI" in indicators:
        panes.append(dict(name="RSI 14", series={"RSI": rsi(values)}, bounds=[0, 100]))
    if "MACD" in indicators:
        panes.append(dict(name="MACD 12/26/9", series=macd(values)))
    for pane in panes:
        pane["points"] = {
            name: [[i, v] for i, v in enumerate(points) if v is not None]
            for name, points in pane.pop("series").items()
        }
        vals = [p[1] for ps in pane["points"].values() for p in ps]
        pane.setdefault("bounds", [min(vals + [0]), max(vals + [1])])
    bounds_values = [project(r[k]) for r in transformed for k in ("close", "high", "low") if k in r]
    bounds_values += [v for l in lines for v in (l[1], l[3])]
    lo, hi = min(bounds_values or [0]), max(bounds_values or [1])
    pad = max((hi - lo) * 0.08, abs(hi) * 0.00001, 0.0001)
    lo, hi = (lo - pad, hi + pad) if fixed_bounds is None else fixed_bounds
    count = max(1, len(transformed))
    if lock:
        span = abs(project(base + box) - project(base)) * count * height * 2 / max(1, width)
        mid = (lo + hi) / 2
        lo, hi = mid - max(span, 0.0001) / 2, mid + max(span, 0.0001) / 2
    high, low = max(values), min(values)
    labels = [
        (f"LAST {values[-1]:.2f}", project(values[-1])),
        (f"HIGH {high:.2f}", project(high)),
        (f"LOW {low:.2f}", project(low)),
    ] + study_labels
    ticks = []
    for j in range(5):
        y = hi - (hi - lo) * j / 4
        v = y * (-1 if invert else 1)
        ticks.append(
            f"{10 ** min(v, 300):.2f}"
            if mode == "logarithmic"
            else f"{v:.2f}{'%' if mode == 'percent' else ''}"
        )
    return dict(
        lines=lines,
        rects=rects,
        glyphs=glyphs,
        bounds=[lo, hi],
        count=count,
        labels=collapse_labels(labels, lo, hi, height),
        ticks=ticks,
        panes=panes,
        volume=[[i, r.get("volume", 0)] for i, r in enumerate(rows)],
        box_size=box,
        studies=list(overlays),
        event_axis=event_style,
    )

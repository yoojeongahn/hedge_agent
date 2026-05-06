# tests/test_chart.py
from pathlib import Path
import pandas as pd
import numpy as np
import pytest
from core.chart import generate_chart
from core.technicals import calculate_technicals


def make_df(n=120):
    prices = [100 + i * 0.3 + np.random.normal(0, 0.5) for i in range(n)]
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame({
        "Open": prices,
        "High": [p * 1.01 for p in prices],
        "Low": [p * 0.99 for p in prices],
        "Close": prices,
        "Volume": [1_000_000] * n,
    }, index=dates)


def test_chart_creates_file(tmp_path):
    df = make_df()
    tech = calculate_technicals(df, "TEST", "US")
    chart_path = generate_chart("TEST", "US", df, tech, output_dir=tmp_path)
    assert chart_path.exists()
    assert chart_path.suffix == ".png"
    assert chart_path.stat().st_size > 0


def test_chart_cleans_up_on_request(tmp_path):
    df = make_df()
    tech = calculate_technicals(df, "TEST", "US")
    chart_path = generate_chart("TEST", "US", df, tech, output_dir=tmp_path)
    chart_path.unlink()
    assert not chart_path.exists()


def test_chart_uses_ohlc(tmp_path):
    """캔들스틱 루프가 실제로 실행됨을 vlines 호출 횟수로 검증."""
    from unittest.mock import patch
    import matplotlib.axes
    rng = np.random.default_rng(42)
    n = 130
    closes = 100 + np.cumsum(rng.normal(0, 0.5, n))
    opens = closes * rng.uniform(0.99, 1.01, n)
    df = pd.DataFrame({
        "Open": opens,
        "High": np.maximum(opens, closes) * 1.005,
        "Low": np.minimum(opens, closes) * 0.995,
        "Close": closes,
        "Volume": [1_000_000] * n,
    }, index=pd.date_range("2025-01-01", periods=n, freq="B"))
    tech = calculate_technicals(df, "TEST", "US")

    real_vlines = matplotlib.axes.Axes.vlines
    with patch("matplotlib.axes.Axes.vlines", wraps=real_vlines) as mock_vlines:
        chart_path = generate_chart("TEST", "US", df, tech, output_dir=tmp_path)

    # chart_df = df.tail(126) → 126 candles → vlines called 126 times for wicks
    assert mock_vlines.call_count == 126
    assert chart_path.exists()
    assert chart_path.stat().st_size > 5000

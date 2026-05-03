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

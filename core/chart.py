# core/chart.py
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # GUI 없는 환경용
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import pandas as pd

from core.technicals import TechnicalsData

logger = logging.getLogger(__name__)

_COLORS = {
    "ma5": "#FF6B6B",
    "ma10": "#FFA07A",
    "ma20": "#4ECDC4",
    "ma60": "#45B7D1",
    "ma3m": "#FFD700",
    "ma6m": "#FF8C00",
    "ma12m": "#FF4500",
    "bb": "#95A5A6",
    "volume": "#5D6D7E",
    "vol_avg": "#F39C12",
    "rsi": "#8E44AD",
    "macd": "#2980B9",
    "signal": "#E74C3C",
    "hist_pos": "#27AE60",
    "hist_neg": "#E74C3C",
}


def generate_chart(
    code: str,
    market: str,
    df: pd.DataFrame,
    tech: TechnicalsData,
    output_dir: Path | None = None,
) -> Path:
    """4패널 차트(가격+MA+BB+피보, 거래량, RSI, MACD)를 PNG로 저장하고 Path 반환."""
    if output_dir is None:
        output_dir = Path("data")
    output_dir.mkdir(parents=True, exist_ok=True)

    chart_df = df.tail(126).copy()
    close = chart_df["Close"]
    volume = chart_df["Volume"]
    dates = chart_df.index

    fig = plt.figure(figsize=(12, 10), facecolor="#1C1C1C")
    gs = gridspec.GridSpec(4, 1, height_ratios=[3, 1, 1, 1], hspace=0.05)
    fig.suptitle(f"{code} ({market}) — {datetime.now().strftime('%Y-%m-%d')}",
                 color="white", fontsize=13, y=0.98)

    # Panel 1: 가격 + 일봉 MAs + BB + 월봉 MAs
    ax1 = fig.add_subplot(gs[0])
    ax1.set_facecolor("#1C1C1C")
    _bar_width = timedelta(hours=14)
    for idx, row in chart_df.iterrows():
        is_up = row["Close"] >= row["Open"]
        color = "#26A69A" if is_up else "#EF5350"
        body_bottom = min(row["Open"], row["Close"])
        body_height = max(abs(row["Close"] - row["Open"]), row["Close"] * 0.0002)
        ax1.bar(idx, body_height, bottom=body_bottom, color=color,
                width=_bar_width, alpha=0.9, linewidth=0)
        ax1.vlines(idx, row["Low"], row["High"], color=color, linewidth=0.5)

    for period, color, label in [
        (5, _COLORS["ma5"], "MA5"),
        (10, _COLORS["ma10"], "MA10"),
        (20, _COLORS["ma20"], "MA20"),
        (60, _COLORS["ma60"], "MA60"),
    ]:
        if len(df) >= period:
            ax1.plot(dates, df["Close"].rolling(period).mean().tail(126),
                     color=color, linewidth=0.8, alpha=0.8, label=label)

    if len(close) >= 20:
        rolling_mean = close.rolling(20).mean()
        rolling_std = close.rolling(20).std()
        ax1.fill_between(dates,
                         rolling_mean + 2 * rolling_std,
                         rolling_mean - 2 * rolling_std,
                         alpha=0.1, color=_COLORS["bb"], label="볼린저밴드")

    for period, color, label in [
        (63, _COLORS["ma3m"], "MA3M"),
        (126, _COLORS["ma6m"], "MA6M"),
        (252, _COLORS["ma12m"], "MA12M"),
    ]:
        if len(df) >= period:
            ax1.plot(dates, df["Close"].rolling(period).mean().tail(126),
                     color=color, linewidth=1.0, alpha=0.7, linestyle="--", label=label)

    ax1.legend(loc="upper left", fontsize=7, facecolor="#2C2C2C", labelcolor="white")
    ax1.set_ylabel("Price", color="white", fontsize=9)
    ax1.tick_params(colors="white", labelsize=7)
    for spine in ax1.spines.values():
        spine.set_color("#444444")
    plt.setp(ax1.get_xticklabels(), visible=False)

    # Panel 2: 거래량
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax2.set_facecolor("#1C1C1C")
    ax2.bar(dates, volume, color=_COLORS["volume"], alpha=0.7, width=0.8)
    if len(volume) >= 20:
        ax2.plot(dates, volume.rolling(20).mean(), color=_COLORS["vol_avg"],
                 linewidth=0.8, label="MA20")
    ax2.set_ylabel("Vol", color="white", fontsize=9)
    ax2.tick_params(colors="white", labelsize=7)
    for spine in ax2.spines.values():
        spine.set_color("#444444")
    plt.setp(ax2.get_xticklabels(), visible=False)

    # Panel 3: RSI
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    ax3.set_facecolor("#1C1C1C")
    if len(close) >= 15:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi_series = 100 - (100 / (1 + rs))
        ax3.plot(dates, rsi_series, color=_COLORS["rsi"], linewidth=0.8)
        ax3.axhline(70, color="red", linewidth=0.5, linestyle="--", alpha=0.7)
        ax3.axhline(30, color="lime", linewidth=0.5, linestyle="--", alpha=0.7)
        ax3.set_ylim(0, 100)
    ax3.set_ylabel("RSI", color="white", fontsize=9)
    ax3.tick_params(colors="white", labelsize=7)
    for spine in ax3.spines.values():
        spine.set_color("#444444")
    plt.setp(ax3.get_xticklabels(), visible=False)

    # Panel 4: MACD
    ax4 = fig.add_subplot(gs[3], sharex=ax1)
    ax4.set_facecolor("#1C1C1C")
    if len(close) >= 35:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        hist = macd_line - signal_line
        colors = [_COLORS["hist_pos"] if v >= 0 else _COLORS["hist_neg"] for v in hist]
        ax4.bar(dates, hist, color=colors, alpha=0.7, width=0.8)
        ax4.plot(dates, macd_line, color=_COLORS["macd"], linewidth=0.8, label="MACD")
        ax4.plot(dates, signal_line, color=_COLORS["signal"], linewidth=0.8, label="Signal")
        ax4.axhline(0, color="#444444", linewidth=0.5)
        ax4.legend(loc="upper left", fontsize=7, facecolor="#2C2C2C", labelcolor="white")
    ax4.set_ylabel("MACD", color="white", fontsize=9)
    ax4.tick_params(colors="white", labelsize=7)
    for spine in ax4.spines.values():
        spine.set_color("#444444")

    try:
        import matplotlib.dates as mdates
        ax4.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    except Exception:
        pass

    chart_path = output_dir / f"chart_{code}_{datetime.now().strftime('%Y%m%d')}.png"
    plt.savefig(chart_path, dpi=100, bbox_inches="tight", facecolor="#1C1C1C")
    plt.close(fig)
    return chart_path

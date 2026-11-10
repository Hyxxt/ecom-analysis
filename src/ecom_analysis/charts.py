"""生成复盘用图表。

配色沿用 dataviz 参考调色板：单一蓝色表示数值大小，红色只用于“目标线”这种
明确的状态提示；每张图只表达一件事，不使用双 Y 轴。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import PercentFormatter

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"
RED = "#d03b3b"
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

plt.rcParams.update(
    {
        "font.family": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": BASELINE,
        "axes.labelcolor": SECONDARY,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "text.color": INK,
        "axes.titlecolor": INK,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "font.size": 9.5,
    }
)


def _style_axis(ax: plt.Axes, grid_axis: str = "y") -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(BASELINE)
    ax.spines["bottom"].set_color(BASELINE)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def _footer(fig: plt.Figure, note: str = "数据为程序生成的模拟数据 · 28 天") -> None:
    fig.text(0.01, 0.005, note, color=MUTED, fontsize=7.5, ha="left", va="bottom")


def plot_acos_by_asin(asin_df: pd.DataFrame, path: Path) -> None:
    """横向条形图：比较各 ASIN 的 ACOS，并与 30% 目标线对照。"""
    data = asin_df.dropna(subset=["acos"]).sort_values("acos", ascending=True)
    fig, ax = plt.subplots(figsize=(8.4, 4.6), dpi=160)
    y = np.arange(len(data))
    ax.barh(y, data["acos"], height=0.56, color=BLUE, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(data["asin"], color=SECONDARY, fontsize=9)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_xlim(0, max(0.6, float(data["acos"].max()) * 1.18))
    ax.set_xlabel("ACOS = 广告花费 ÷ 广告销售额")
    ax.set_title("各 ASIN 的 ACOS：谁在赚钱，谁在烧钱", loc="left")
    ax.axvline(0.30, color=RED, linestyle=(0, (4, 3)), linewidth=1.4, zorder=4)
    ax.text(
        0.305,
        len(data) - 0.35,
        "目标线 30%",
        color=RED,
        fontsize=8,
        ha="left",
        va="top",
    )
    for yi, value in zip(y, data["acos"]):
        ax.text(
            value + 0.008,
            yi,
            "{:.1%}".format(value),
            va="center",
            ha="left",
            fontsize=9,
            color=SECONDARY,
        )
    _style_axis(ax, "x")
    _footer(fig)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(str(path), bbox_inches="tight")
    plt.close(fig)


def plot_spend_vs_sales(asin_df: pd.DataFrame, path: Path) -> None:
    """散点图：花费与销售额的关系，颜色深浅表示 ACOS。"""
    data = asin_df.dropna(subset=["acos"]).copy()
    fig, ax = plt.subplots(figsize=(8.4, 5.0), dpi=160)
    cmap = LinearSegmentedColormap.from_list("acos_blue", SEQUENTIAL)
    sizes = 50 + data["ad_orders"].astype(float) * 1.6
    scatter = ax.scatter(
        data["spend"],
        data["sales"],
        s=sizes,
        c=data["acos"],
        cmap=cmap,
        vmin=0,
        vmax=max(0.6, float(data["acos"].max())),
        edgecolors=SURFACE,
        linewidths=1.6,
        zorder=3,
    )
    label_offsets = {
        "B0DEMO001": (-14, -20, "right"),
        "B0DEMO002": (12, 14, "left"),
        "B0DEMO003": (28, -6, "left"),
        "B0DEMO004": (14, 18, "left"),
        "B0DEMO005": (12, 10, "left"),
        "B0DEMO006": (-10, 12, "right"),
    }
    for _, row in data.iterrows():
        dx, dy, align = label_offsets.get(row["asin"], (10, 8, "left"))
        ax.annotate(
            "{}  {:.1%}".format(row["asin"], row["acos"]),
            (row["spend"], row["sales"]),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=8.2,
            color=SECONDARY,
            ha=align,
            va="center",
        )
    ax.set_xlim(0, float(data["spend"].max()) * 1.18)
    ax.set_ylim(0, float(data["sales"].max()) * 1.16)
    ax.set_xlabel("广告花费（美元）")
    ax.set_ylabel("总销售额（美元）")
    ax.set_title("花费 vs 销售额：气泡越大，广告订单越多", loc="left")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda value, _: "${:,.0f}".format(value)))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda value, _: "${:,.0f}".format(value)))
    colorbar = fig.colorbar(scatter, ax=ax, pad=0.02)
    colorbar.set_label("ACOS（颜色越深越高）", color=SECONDARY, fontsize=8.5)
    colorbar.ax.tick_params(labelsize=8, colors=MUTED)
    colorbar.outline.set_edgecolor(BASELINE)
    _style_axis(ax, "both")
    _footer(fig)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(str(path), bbox_inches="tight")
    plt.close(fig)


def plot_weekly_trend(weekly: pd.DataFrame, path: Path) -> None:
    """两个小多图：CVR 与 ACOS 的周趋势，避免双 Y 轴。"""
    data = weekly.copy()
    fig, axes = plt.subplots(2, 1, figsize=(8.4, 5.8), dpi=160, sharex=True)
    labels = [pd.Timestamp(value).strftime("%m-%d") for value in data["week_start"]]

    ax1 = axes[0]
    ax1.plot(
        labels,
        data["cvr"],
        color=BLUE,
        linewidth=2,
        marker="o",
        markersize=5,
        markeredgecolor=SURFACE,
        markeredgewidth=1.4,
        zorder=3,
    )
    ax1.set_title("周 CVR：转化率是否稳定", loc="left")
    ax1.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax1.set_ylim(0, max(0.12, float(data["cvr"].max()) * 1.25))
    _annotate_last(ax1, labels, data["cvr"], "{:.1%}")

    ax2 = axes[1]
    ax2.plot(
        labels,
        data["acos"],
        color=BLUE,
        linewidth=2,
        marker="o",
        markersize=5,
        markeredgecolor=SURFACE,
        markeredgewidth=1.4,
        zorder=3,
    )
    ax2.axhline(0.30, color=RED, linestyle=(0, (4, 3)), linewidth=1.3, zorder=2)
    ax2.text(
        0,
        0.315,
        "目标 ACOS 30%",
        color=RED,
        fontsize=8,
        ha="left",
        va="bottom",
    )
    ax2.set_title("周 ACOS：广告效率是否恶化", loc="left")
    ax2.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax2.set_ylim(0, max(0.5, float(data["acos"].max()) * 1.18))
    _annotate_last(ax2, labels, data["acos"], "{:.1%}")

    for ax in axes:
        _style_axis(ax, "y")
    axes[1].set_xlabel("自然周起始（2026 年）")
    _footer(fig)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(str(path), bbox_inches="tight")
    plt.close(fig)


def _annotate_last(
    ax: plt.Axes, labels: list, values: pd.Series, fmt: str
) -> None:
    if len(values) == 0 or pd.isna(values.iloc[-1]):
        return
    ax.annotate(
        fmt.format(values.iloc[-1]),
        (labels[-1], values.iloc[-1]),
        xytext=(-6, 10),
        textcoords="offset points",
        ha="right",
        fontsize=9,
        color=SECONDARY,
    )


def generate_charts(asin_df: pd.DataFrame, weekly: pd.DataFrame, chart_dir: Path) -> Dict[str, Path]:
    chart_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "acos": chart_dir / "acos_by_asin.png",
        "scatter": chart_dir / "spend_vs_sales.png",
        "weekly": chart_dir / "weekly_trend.png",
    }
    plot_acos_by_asin(asin_df, paths["acos"])
    plot_spend_vs_sales(asin_df, paths["scatter"])
    plot_weekly_trend(weekly, paths["weekly"])
    return paths

"""把分析结果输出为 Markdown、HTML 和 Excel。"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def money(value: object) -> str:
    if value is None or pd.isna(value):
        return "—"
    return "${:,.2f}".format(float(value))


def pct(value: object, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "—"
    return "{:.{}%}".format(float(value), digits)


def number(value: object) -> str:
    if value is None or pd.isna(value):
        return "—"
    return "{:,.0f}".format(float(value))


def _row_or_none(df: pd.DataFrame, condition: Optional[pd.Series] = None) -> Optional[pd.Series]:
    data = df if condition is None else df[condition]
    if data.empty:
        return None
    return data.iloc[0]


def _conclusions(context: Dict[str, object]) -> List[str]:
    asin_df = context["asin"]  # type: ignore[assignment]
    keyword_df = context["keyword"]  # type: ignore[assignment]
    anomalies = context["anomalies"]  # type: ignore[assignment]
    overall = context["overall"]  # type: ignore[assignment]

    lines: List[str] = []
    ranked = asin_df[(asin_df["spend"] > 0) & asin_df["roas"].notna()].sort_values(
        "roas", ascending=False
    )
    best = ranked.iloc[0] if not ranked.empty else None
    if best is not None:
        best_ad_share = (
            float(best["ad_sales"]) / float(overall["ad_sales"])
            if float(overall["ad_sales"]) > 0
            else float("nan")
        )
        lines.append(
            "值得加预算：{}，ACOS {}、ROAS {:.2f}、CVR {}，贡献了店铺广告销售额的 {}。"
            "建议先小步加预算 20%–30%，观察一周 ACOS 是否仍在可接受区间。".format(
                best["asin"],
                pct(best["acos"]),
                float(best["roas"]),
                pct(best["cvr"]),
                pct(best_ad_share),
            )
        )

    with_spend = asin_df[asin_df["spend"] >= 100].copy()
    worst = _row_or_none(with_spend.sort_values("acos", ascending=False))
    if worst is None:
        worst = _row_or_none(asin_df.sort_values("acos", ascending=False))
    if worst is not None:
        lines.append(
            "需要降预算 / 查转化：{}，ACOS {}、花费 {}、CVR {}。"
            "先看搜索词和 Listing，再决定是降价、收词还是暂停。".format(
                worst["asin"],
                pct(worst["acos"]),
                money(worst["spend"]),
                pct(worst["cvr"]),
            )
        )

    wasted = keyword_df[(keyword_df["spend"] >= 30) & (keyword_df["ad_orders"] == 0)]
    wasted = wasted.sort_values("spend", ascending=False)
    if not wasted.empty:
        row = wasted.iloc[0]
        lines.append(
            "先止损的关键词：{}，花费 {}、0 个归因订单。"
            "建议加入否词或改精准匹配；本周期共有 {} 条异常/待复核记录。".format(
                row["keyword"], money(row["spend"]), len(anomalies)
            )
        )
    else:
        lines.append("本周期没有发现“有花费但零订单”的关键词；仍需持续看搜索词报告。")

    if not anomalies.empty:
        first = anomalies.iloc[0]
        lines.append(
            "最优先复核的异常：{}（{}，{}）。{}。".format(
                first["type"], first["object"], first["period"], first["action"]
            )
        )
    return lines


def _asin_rows(asin_df: pd.DataFrame) -> List[List[str]]:
    rows = []
    for _, row in asin_df.iterrows():
        rows.append(
            [
                str(row["asin"]),
                money(row["sales"]),
                money(row["spend"]),
                pct(row["acos"]),
                "{:.2f}".format(row["roas"]) if not pd.isna(row["roas"]) else "—",
                pct(row["cvr"]),
                pct(row["sales_share"]),
                str(row["advice"]),
            ]
        )
    return rows


def _campaign_rows(campaign_df: pd.DataFrame, limit: int = 8) -> List[List[str]]:
    rows = []
    for _, row in campaign_df.head(limit).iterrows():
        rows.append(
            [
                str(row["campaign"]),
                str(row["asin"]),
                money(row["spend"]),
                money(row["ad_sales"]),
                pct(row["acos"]),
                pct(row["ctr"]),
                money(row["cpc"]),
                pct(row["spend_share"]),
            ]
        )
    return rows


def _keyword_rows(keyword_df: pd.DataFrame, limit: int = 10) -> List[List[str]]:
    rows = []
    for _, row in keyword_df.head(limit).iterrows():
        rows.append(
            [
                str(row["keyword"]),
                str(row["campaign"]),
                money(row["spend"]),
                number(row["ad_orders"]),
                pct(row["acos"]),
                pct(row["ad_cvr"]),
                str(row["action"]),
            ]
        )
    return rows


def _weekly_rows(weekly: pd.DataFrame) -> List[List[str]]:
    rows = []
    for _, row in weekly.iterrows():
        rows.append(
            [
                pd.Timestamp(row["week_start"]).strftime("%Y-%m-%d"),
                money(row["sales"]),
                money(row["spend"]),
                pct(row["cvr"]),
                pct(row["acos"]),
                "{:.2f}".format(row["roas"]) if not pd.isna(row["roas"]) else "—",
            ]
        )
    return rows


def _anomaly_rows(anomalies: pd.DataFrame) -> List[List[str]]:
    rows = []
    for _, row in anomalies.iterrows():
        rows.append(
            [
                str(row["type"]),
                str(row["object"]),
                str(row["period"]),
                str(row["metric"]),
                str(row["detail"]),
                str(row["action"]),
            ]
        )
    return rows


def _quality_rows(quality: pd.DataFrame) -> List[List[str]]:
    rows = []
    for _, row in quality.iterrows():
        rows.append(
            [
                str(row["table"]),
                str(row["issue"]),
                number(row["rows"]),
                str(row["action"]),
            ]
        )
    return rows


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        cells = [str(cell).replace("|", "\\|").replace("\n", " ") for cell in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _lead_metrics(context: Dict[str, object]) -> Dict[str, str]:
    overall = context["overall"]  # type: ignore[assignment]
    return {
        "总销售额": money(overall["total_sales"]),
        "广告花费": money(overall["ad_spend"]),
        "ACOS": pct(overall["acos"]),
        "ROAS": "{:.2f}".format(overall["roas"]) if not pd.isna(overall["roas"]) else "—",
        "CVR": pct(overall["cvr"]),
        "TACOS": pct(overall["tacos"]),
    }


def write_markdown(context: Dict[str, object], path: Path) -> None:
    overall = context["overall"]  # type: ignore[assignment]
    coverage = context["coverage"]  # type: ignore[assignment]
    raw_counts = context["raw_counts"]  # type: ignore[assignment]
    asin_df = context["asin"]  # type: ignore[assignment]
    campaign_df = context["campaign"]  # type: ignore[assignment]
    keyword_df = context["keyword"]  # type: ignore[assignment]
    weekly = context["weekly"]  # type: ignore[assignment]
    anomalies = context["anomalies"]  # type: ignore[assignment]
    quality = context["quality"]  # type: ignore[assignment]
    conclusions = _conclusions(context)

    md: List[str] = []
    md.append("# 美区电商广告数据分析 Demo")
    md.append("")
    md.append(
        "> **数据说明**：本报告全部基于程序生成的模拟数据，不是真实店铺数据，"
        "也不代表任何真实品牌或平台。用途是演示完整的分析流程和可复核的结论。"
    )
    md.append("")
    md.append(
        "**分析周期**：{} 至 {}（{} 天）｜**ASIN**：{} 个｜**生成时间**：{}".format(
            coverage["start"],
            coverage["end"],
            coverage["days"],
            coverage["asins"],
            context["generated_at"],
        )
    )
    md.append("")
    md.append("## 1. 一句话结论")
    md.append("")
    md.append(
        "本周期总销售额 **{}**，广告花费 **{}**，广告归因销售额 **{}**，"
        "整体 **ACOS {} / ROAS {} / TACOS {} / CVR {}**。".format(
            money(overall["total_sales"]),
            money(overall["ad_spend"]),
            money(overall["ad_sales"]),
            pct(overall["acos"]),
            "{:.2f}".format(overall["roas"]) if not pd.isna(overall["roas"]) else "—",
            pct(overall["tacos"]),
            pct(overall["cvr"]),
        )
    )
    md.append("")
    for line in conclusions:
        md.append("- " + line)
    md.append("")
    md.append(
        "> ACOS 用“广告花费 ÷ 广告归因销售额”，CVR 用“订单数 ÷ 会话数”，"
        "TACOS 用“广告花费 ÷ 总销售额”。三个指标口径不同，不能混着解释。"
    )
    md.append("")

    md.append("## 2. 核心指标")
    md.append("")
    lead = _lead_metrics(context)
    md.append(_md_table(["指标", "数值"], [[key, value] for key, value in lead.items()]))
    md.append("")
    md.append(
        "补充：广告 CTR **{}**，CPC **{}**，广告 CVR **{}**，客单价 **{}**，"
        "广告销售额占总销售额 **{}**。".format(
            pct(overall["ctr"]),
            money(overall["cpc"]),
            pct(overall["ad_cvr"]),
            money(overall["aov"]),
            pct(overall["ad_sales_share"]),
        )
    )
    md.append("")

    md.append("## 3. ASIN 表现")
    md.append("")
    md.append(
        _md_table(
            ["ASIN", "销售额", "广告花费", "ACOS", "ROAS", "CVR", "销售占比", "建议"],
            _asin_rows(asin_df),
        )
    )
    md.append("")
    md.append("![各 ASIN 的 ACOS](charts/acos_by_asin.png)")
    md.append("")
    md.append("![广告花费与总销售额](charts/spend_vs_sales.png)")
    md.append("")

    md.append("## 4. 广告活动")
    md.append("")
    md.append(
        _md_table(
            ["广告活动", "ASIN", "花费", "广告销售额", "ACOS", "CTR", "CPC", "花费占比"],
            _campaign_rows(campaign_df),
        )
    )
    md.append("")

    md.append("## 5. 关键词动作")
    md.append("")
    md.append(
        _md_table(
            ["关键词", "广告活动", "花费", "订单", "ACOS", "广告 CVR", "动作"],
            _keyword_rows(keyword_df),
        )
    )
    md.append("")
    md.append(
        "> “加入否词”的规则是：本周期花费 ≥ $30 且归因订单为 0。"
        "这只是筛选候选，不是自动否定；落地前还要看搜索词和归因延迟。"
    )
    md.append("")

    md.append("## 6. 周趋势")
    md.append("")
    md.append(
        _md_table(
            ["周起始", "总销售额", "广告花费", "CVR", "ACOS", "ROAS"],
            _weekly_rows(weekly),
        )
    )
    md.append("")
    md.append(
        "> 自然周以周日为周末，首尾周可能不完整。整体 CVR 稳定不代表每个 ASIN 都稳定，"
        "ASIN 级的 CVR 下滑见异常表。"
    )
    md.append("")
    md.append("![周 CVR 与 ACOS](charts/weekly_trend.png)")
    md.append("")

    md.append("## 7. 异常与待复核")
    md.append("")
    if anomalies.empty:
        md.append("本周期未发现满足规则的异常。")
    else:
        md.append(
            _md_table(
                ["类型", "对象", "日期/周期", "指标", "说明", "建议"],
                _anomaly_rows(anomalies),
            )
        )
    md.append("")

    md.append("## 8. 数据质量")
    md.append("")
    md.append(
        "原始数据：销售日报 **{}** 行，广告日报 **{}** 行，关键词日报 **{}** 行。"
        "清洗后保留销售 **{}** 行、广告 **{}** 行、关键词 **{}** 行。".format(
            raw_counts["sales"],
            raw_counts["ads"],
            raw_counts["keywords"],
            len(context["sales"]),  # type: ignore[arg-type]
            len(context["ads"]),  # type: ignore[arg-type]
            len(context["keywords"]),  # type: ignore[arg-type]
        )
    )
    md.append("")
    if quality.empty:
        md.append("本周期没有记录到数据质量问题。")
    else:
        md.append(_md_table(["数据表", "问题", "行数", "处理"], _quality_rows(quality)))
    md.append("")
    md.append("主要清洗规则：")
    md.append("")
    md.append("- 日期兼容 `2026-10-01` 和 `2026/10/12`，无法解析的行剔除。")
    md.append("- ASIN 去空格并转大写；同日同 ASIN 重复保留最后一条。")
    md.append("- `$1,234.50`、千分位、百分号、括号负数统一转数值。")
    md.append("- 负数、点击大于曝光、关键指标缺失：剔除并记录。")
    md.append("- 会话数缺失：按同 ASIN 中位数填补；销量/销售额缺失：按 0 填补并记录。")
    md.append("- 广告表中销售表不存在的 ASIN：从广告分析中剔除，避免污染 ASIN 汇总。")
    md.append("")

    md.append("## 9. 口径与限制")
    md.append("")
    md.append("- 数据是 **28 天模拟数据**，没有真实平台 API、真实广告后台或真实财务口径。")
    md.append("- 总销售额来自销售表，广告销售额来自广告归因；两者天然存在归因差异。")
    md.append("- ACOS 高不一定立刻停投：新品、清库存、卡位等阶段可能有不同目标。")
    md.append("- 关键词“零订单”可能受归因延迟影响，落地前需回看 7–14 天。")
    md.append("- 本报告是分析练习，不构成真实经营建议。")
    md.append("")

    md.append("## 10. 如何复现")
    md.append("")
    md.append("```powershell")
    md.append("pip install -r requirements.txt")
    md.append("python scripts/generate_sample_data.py")
    md.append("python run.py")
    md.append("python -m pytest -q")
    md.append("```")
    md.append("")
    md.append("生成文件：`reports/report.md`、`reports/report.html`、`reports/summary.xlsx`、`reports/charts/`。")
    md.append("")

    path.write_text("\n".join(md), encoding="utf-8")


def _html_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    right_from: int = 1,
    right_cols: Optional[Sequence[int]] = None,
    empty_text: str = "暂无数据",
) -> str:
    if not rows:
        return '<p class="empty">{}</p>'.format(html.escape(empty_text))

    def is_numeric(index: int) -> bool:
        if right_cols is None:
            return index >= right_from
        return index in right_cols

    parts = ['<p class="scroll-hint">表格列较多，可左右滑动查看 →</p>']
    parts.append('<div class="table-wrap"><table>')
    parts.append("<thead><tr>")
    for index, header in enumerate(headers):
        cls = ' class="num"' if is_numeric(index) else ""
        parts.append("<th{}>{}</th>".format(cls, html.escape(str(header))))
    parts.append("</tr></thead><tbody>")
    for row in rows:
        parts.append("<tr>")
        for index, cell in enumerate(row):
            cls = ' class="num"' if is_numeric(index) else ""
            parts.append("<td{}>{}</td>".format(cls, html.escape(str(cell))))
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def write_html(context: Dict[str, object], path: Path) -> None:
    overall = context["overall"]  # type: ignore[assignment]
    coverage = context["coverage"]  # type: ignore[assignment]
    raw_counts = context["raw_counts"]  # type: ignore[assignment]
    asin_df = context["asin"]  # type: ignore[assignment]
    campaign_df = context["campaign"]  # type: ignore[assignment]
    keyword_df = context["keyword"]  # type: ignore[assignment]
    weekly = context["weekly"]  # type: ignore[assignment]
    anomalies = context["anomalies"]  # type: ignore[assignment]
    quality = context["quality"]  # type: ignore[assignment]
    conclusions = _conclusions(context)

    kpis = [
        ("总销售额", money(overall["total_sales"]), "销售表口径"),
        ("广告花费", money(overall["ad_spend"]), "广告后台口径"),
        ("ACOS", pct(overall["acos"]), "花费 ÷ 广告销售额"),
        ("ROAS", "{:.2f}".format(overall["roas"]) if not pd.isna(overall["roas"]) else "—", "广告销售额 ÷ 花费"),
        ("CVR", pct(overall["cvr"]), "订单 ÷ 会话"),
        ("TACOS", pct(overall["tacos"]), "花费 ÷ 总销售额"),
    ]
    kpi_html = "".join(
        '<div class="kpi"><span class="kpi-label">{}</span><strong>{}</strong><span class="kpi-note">{}</span></div>'.format(
            html.escape(label), html.escape(value), html.escape(note)
        )
        for label, value, note in kpis
    )

    conclusion_html = "".join("<li>{}</li>".format(html.escape(line)) for line in conclusions)
    asin_html = _html_table(
        ["ASIN", "销售额", "广告花费", "ACOS", "ROAS", "CVR", "销售占比", "建议"],
        _asin_rows(asin_df),
        right_cols=(1, 2, 3, 4, 5, 6),
    )
    campaign_html = _html_table(
        ["广告活动", "ASIN", "花费", "广告销售额", "ACOS", "CTR", "CPC", "花费占比"],
        _campaign_rows(campaign_df),
        right_cols=(2, 3, 4, 5, 6, 7),
    )
    keyword_html = _html_table(
        ["关键词", "广告活动", "花费", "订单", "ACOS", "广告 CVR", "动作"],
        _keyword_rows(keyword_df),
        right_cols=(2, 3, 4, 5),
    )
    weekly_html = _html_table(
        ["周起始", "总销售额", "广告花费", "CVR", "ACOS", "ROAS"],
        _weekly_rows(weekly),
        right_cols=(1, 2, 3, 4, 5),
    )
    anomaly_html = _html_table(
        ["类型", "对象", "日期/周期", "指标", "说明", "建议"],
        _anomaly_rows(anomalies),
        right_cols=(),
        empty_text="本周期未发现满足规则的异常。",
    )
    quality_html = _html_table(
        ["数据表", "问题", "行数", "处理"],
        _quality_rows(quality),
        right_cols=(2,),
        empty_text="本周期没有记录到数据质量问题。",
    )

    doc = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>美区电商广告复盘 · 模拟数据</title>
<style>
:root {{
  --surface: #fcfcfb;
  --page: #f9f9f7;
  --ink: #0b0b0b;
  --secondary: #52514e;
  --muted: #898781;
  --grid: #e1e0d9;
  --baseline: #c3c2b7;
  --blue: #2a78d6;
  --blue-dark: #184f95;
  --blue-wash: #edf5ff;
  --red: #d03b3b;
  --green: #0ca30c;
  --border: rgba(11, 11, 11, 0.10);
}}
* {{ box-sizing: border-box; }}
html, body {{ max-width: 100%; overflow-x: hidden; }}
body {{
  margin: 0;
  background: var(--page);
  color: var(--ink);
  font-family: system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
  line-height: 1.65;
}}
main {{ width: 100%; max-width: 1120px; margin: 0 auto; padding: 32px 20px 64px; }}
.hero {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 30px 34px;
  margin-bottom: 22px;
}}
.eyebrow {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }}
.pill {{
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  background: var(--blue-wash);
  color: var(--blue-dark);
}}
.pill.data {{ background: #fff6e6; color: #8a5a00; }}
h1 {{ margin: 0 0 8px; font-size: clamp(28px, 4vw, 44px); line-height: 1.15; letter-spacing: -0.02em; }}
.subtitle {{ margin: 0; color: var(--secondary); max-width: 760px; }}
.meta {{ margin-top: 18px; color: var(--muted); font-size: 13px; }}
section {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 26px 28px;
  margin-bottom: 18px;
  max-width: 100%;
}}
section h2 {{ margin: 0 0 6px; font-size: 20px; letter-spacing: -0.01em; }}
.section-note {{ margin: 0 0 18px; color: var(--muted); font-size: 13px; }}
.kpis {{ display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; }}
.kpi {{
  border: 1px solid var(--grid);
  border-radius: 12px;
  padding: 14px;
  background: #fff;
  min-width: 0;
}}
.kpi-label {{ display: block; color: var(--muted); font-size: 12px; }}
.kpi strong {{ display: block; font-size: clamp(18px, 1.9vw, 25px); line-height: 1.2; margin: 6px 0 3px; font-variant-numeric: tabular-nums; white-space: nowrap; letter-spacing: -0.02em; }}
.kpi-note {{ display: block; color: var(--muted); font-size: 11px; }}
.findings {{ margin: 0; padding-left: 20px; }}
.findings li {{ margin: 10px 0; }}
.findings li::marker {{ color: var(--blue); }}
.chart-grid {{ display: grid; grid-template-columns: 1fr; gap: 16px; }}
.chart-card {{ border: 1px solid var(--grid); border-radius: 12px; background: #fff; padding: 10px; }}
.chart-card img {{ width: 100%; height: auto; display: block; border-radius: 8px; }}
.chart-card.wide {{ grid-column: 1 / -1; }}
.scroll-hint {{ display: none; margin: 0 0 6px; color: var(--muted); font-size: 11px; }}
.table-wrap {{ width: 100%; max-width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; border: 1px solid var(--grid); border-radius: 12px; }}
table {{ width: 100%; min-width: 680px; border-collapse: collapse; font-size: 13px; white-space: nowrap; }}
th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--grid); text-align: left; vertical-align: top; }}
th {{ background: #f4f8fd; color: var(--secondary); font-size: 12px; font-weight: 700; position: sticky; top: 0; }}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
tbody tr:last-child td {{ border-bottom: 0; }}
tbody tr:hover {{ background: #fafcff; }}
.empty {{ color: var(--muted); margin: 0; }}
.quality {{ margin: 0; padding-left: 20px; color: var(--secondary); }}
.quality li {{ margin: 7px 0; }}
.limits {{ color: var(--secondary); }}
.limits li {{ margin: 7px 0; }}
code {{ background: #f2f1ed; border-radius: 5px; padding: 2px 5px; font-size: 0.92em; }}
footer {{ color: var(--muted); font-size: 12px; text-align: center; padding-top: 10px; }}
@media (max-width: 900px) {{
  .kpis {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
  .chart-grid {{ grid-template-columns: 1fr; }}
  section {{ padding: 22px 18px; }}
  .hero {{ padding: 24px 20px; }}
}}
@media (max-width: 560px) {{
  .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  main {{ padding: 18px 12px 40px; }}
  table {{ font-size: 12px; }}
  th, td {{ padding: 8px 10px; }}
  .scroll-hint {{ display: block; }}
}}
</style>
</head>
<body>
<main>
  <header class="hero">
    <div class="eyebrow">
      <span class="pill">Python · pandas · numpy</span>
      <span class="pill">数据清洗 → 指标 → 结论</span>
      <span class="pill data">模拟数据，非真实店铺</span>
    </div>
    <h1>美区电商广告复盘</h1>
    <p class="subtitle">把销售、广告和关键词三张日报表清洗成可复核的指标，找出该加预算的 ASIN、该止损的关键词和需要人工复核的异常。</p>
    <div class="meta">分析周期：{start} 至 {end}（{days} 天） · {asins} 个 ASIN · 生成于 {generated}</div>
  </header>

  <section>
    <h2>01 · 结论摘要</h2>
    <p class="section-note">先把钱花在哪、哪里有效、哪里需要停，讲成三句话。</p>
    <ul class="findings">{conclusions}</ul>
  </section>

  <section>
    <h2>02 · 核心指标</h2>
    <p class="section-note">ACOS、ROAS、CVR、TACOS 的分母不同，分开看，避免把“广告效率”和“店铺效率”混为一谈。</p>
    <div class="kpis">{kpis}</div>
  </section>

  <section>
    <h2>03 · ASIN 表现</h2>
    <p class="section-note">销售额为总销售额；ACOS 的分母是广告归因销售额。建议由规则生成，仅作分析起点。</p>
    {asin_table}
    <div class="chart-grid" style="margin-top:16px">
      <div class="chart-card"><a href="charts/acos_by_asin.png" target="_blank" rel="noopener"><img src="charts/acos_by_asin.png" alt="各 ASIN 的 ACOS 条形图" loading="lazy"></a></div>
      <div class="chart-card"><a href="charts/spend_vs_sales.png" target="_blank" rel="noopener"><img src="charts/spend_vs_sales.png" alt="广告花费与总销售额散点图" loading="lazy"></a></div>
      <div class="chart-card wide"><a href="charts/weekly_trend.png" target="_blank" rel="noopener"><img src="charts/weekly_trend.png" alt="周 CVR 与 ACOS 趋势图" loading="lazy"></a></div>
    </div>
  </section>

  <section>
    <h2>04 · 广告活动</h2>
    <p class="section-note">按花费从高到低排序，先看花得最多的活动是否也在贡献销售额。</p>
    {campaign_table}
  </section>

  <section>
    <h2>05 · 关键词动作</h2>
    <p class="section-note">“加入否词”的筛选条件是花费 ≥ $30 且归因订单为 0；落地前还要看搜索词和归因延迟。</p>
    {keyword_table}
  </section>

  <section>
    <h2>06 · 周趋势</h2>
    <p class="section-note">按自然周汇总，观察 CVR 和 ACOS 是否出现结构性变化，而不是被单日波动带偏。</p>
    {weekly_table}
  </section>

  <section>
    <h2>07 · 异常与待复核</h2>
    <p class="section-note">异常只代表“值得查”，不等于“已经确认原因”。</p>
    {anomaly_table}
  </section>

  <section>
    <h2>08 · 数据质量</h2>
    <p class="section-note">原始数据：销售 {raw_sales} 行、广告 {raw_ads} 行、关键词 {raw_keywords} 行；清洗后分别保留 {clean_sales}、{clean_ads}、{clean_keywords} 行。</p>
    {quality_table}
    <ul class="quality">
      <li>日期兼容 <code>2026-10-01</code> / <code>2026/10/12</code>；ASIN 去空格并转大写。</li>
      <li>同日同 ASIN 重复保留最后一条；<code>$1,234.50</code>、千分位、括号负数统一转数值。</li>
      <li>负数、点击大于曝光、关键指标缺失：剔除并记录；会话缺失按 ASIN 中位数填补。</li>
      <li>广告表中销售表不存在的 ASIN：从广告分析中剔除，避免污染 ASIN 汇总。</li>
    </ul>
  </section>

  <section>
    <h2>09 · 口径与限制</h2>
    <ul class="limits">
      <li>数据是 <strong>28 天模拟数据</strong>，没有真实平台 API、真实广告后台或真实财务口径。</li>
      <li>总销售额来自销售表，广告销售额来自广告归因，两者天然存在归因差异。</li>
      <li>ACOS 高不一定立刻停投；新品、清库存、卡位等阶段可能有不同目标。</li>
      <li>关键词“零订单”可能受归因延迟影响，落地前需回看 7–14 天。</li>
      <li>本报告是分析练习，不构成真实经营建议。</li>
    </ul>
  </section>

  <footer>由 Python 脚本生成 · 数据全部为模拟 · 可复现：<code>python scripts/generate_sample_data.py</code> + <code>python run.py</code></footer>
</main>
</body>
</html>
""".format(
        start=coverage["start"],
        end=coverage["end"],
        days=coverage["days"],
        asins=coverage["asins"],
        generated=context["generated_at"],
        conclusions=conclusion_html,
        kpis=kpi_html,
        asin_table=asin_html,
        campaign_table=campaign_html,
        keyword_table=keyword_html,
        weekly_table=weekly_html,
        anomaly_table=anomaly_html,
        raw_sales=raw_counts["sales"],
        raw_ads=raw_counts["ads"],
        raw_keywords=raw_counts["keywords"],
        clean_sales=len(context["sales"]),  # type: ignore[arg-type]
        clean_ads=len(context["ads"]),  # type: ignore[arg-type]
        clean_keywords=len(context["keywords"]),  # type: ignore[arg-type]
        quality_table=quality_html,
    )
    path.write_text(doc, encoding="utf-8")


def _write_excel_sheet(
    writer: pd.ExcelWriter,
    df: pd.DataFrame,
    sheet_name: str,
    percent_cols: Sequence[str] = (),
    money_cols: Sequence[str] = (),
    integer_cols: Sequence[str] = (),
    ratio_cols: Sequence[str] = (),
    auto_filter: bool = True,
) -> None:
    df.to_excel(writer, sheet_name=sheet_name, index=False)
    ws = writer.sheets[sheet_name]
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A2"
    if auto_filter and len(df) > 0:
        ws.auto_filter.ref = ws.dimensions

    header_fill = PatternFill("solid", fgColor="2A78D6")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF", size=10)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            cell.alignment = Alignment(vertical="top")

    for col_name in percent_cols:
        if col_name not in df.columns:
            continue
        col_index = list(df.columns).index(col_name) + 1
        for row_index in range(2, len(df) + 2):
            ws.cell(row=row_index, column=col_index).number_format = "0.0%"

    for col_name in money_cols:
        if col_name not in df.columns:
            continue
        col_index = list(df.columns).index(col_name) + 1
        for row_index in range(2, len(df) + 2):
            ws.cell(row=row_index, column=col_index).number_format = '"$"#,##0.00'

    for col_name in integer_cols:
        if col_name not in df.columns:
            continue
        col_index = list(df.columns).index(col_name) + 1
        for row_index in range(2, len(df) + 2):
            ws.cell(row=row_index, column=col_index).number_format = "#,##0"

    for col_name in ratio_cols:
        if col_name not in df.columns:
            continue
        col_index = list(df.columns).index(col_name) + 1
        for row_index in range(2, len(df) + 2):
            ws.cell(row=row_index, column=col_index).number_format = "0.00"

    for column_cells in ws.columns:
        letter = get_column_letter(column_cells[0].column)
        max_len = max(
            len(str(cell.value)) for cell in column_cells if cell.value is not None
        )
        ws.column_dimensions[letter].width = min(36, max(10, max_len * 1.35 + 2))

    ws.row_dimensions[1].height = 24


def write_excel(context: Dict[str, object], path: Path) -> None:
    overall = context["overall"]  # type: ignore[assignment]
    asin_df = context["asin"]  # type: ignore[assignment]
    campaign_df = context["campaign"]  # type: ignore[assignment]
    keyword_df = context["keyword"]  # type: ignore[assignment]
    weekly = context["weekly"]  # type: ignore[assignment]
    anomalies = context["anomalies"]  # type: ignore[assignment]
    quality = context["quality"]  # type: ignore[assignment]
    coverage = context["coverage"]  # type: ignore[assignment]

    overview_rows = [
        ["总销售额", overall["total_sales"], "销售表口径"],
        ["广告花费", overall["ad_spend"], "广告后台口径"],
        ["广告归因销售额", overall["ad_sales"], "广告后台口径"],
        ["ACOS", overall["acos"], "广告花费 ÷ 广告销售额"],
        ["ROAS", overall["roas"], "广告销售额 ÷ 广告花费"],
        ["TACOS", overall["tacos"], "广告花费 ÷ 总销售额"],
        ["CVR", overall["cvr"], "订单数 ÷ 会话数"],
        ["CTR", overall["ctr"], "点击 ÷ 曝光"],
        ["CPC", overall["cpc"], "花费 ÷ 点击"],
        ["客单价 AOV", overall["aov"], "销售额 ÷ 订单数"],
        ["总订单数", overall["total_units"], "销售表口径"],
        ["广告订单数", overall["ad_orders"], "广告归因口径"],
    ]
    overview = pd.DataFrame(overview_rows, columns=["指标", "数值", "说明"])

    asin_out = asin_df[
        [
            "asin",
            "sales",
            "units",
            "spend",
            "ad_sales",
            "acos",
            "roas",
            "cvr",
            "ctr",
            "cpc",
            "sales_share",
            "advice",
        ]
    ].rename(
        columns={
            "asin": "ASIN",
            "sales": "总销售额",
            "units": "订单数",
            "spend": "广告花费",
            "ad_sales": "广告销售额",
            "acos": "ACOS",
            "roas": "ROAS",
            "cvr": "CVR",
            "ctr": "CTR",
            "cpc": "CPC",
            "sales_share": "销售占比",
            "advice": "建议",
        }
    )
    campaign_out = campaign_df[
        ["campaign", "asin", "spend", "ad_sales", "acos", "roas", "ctr", "cpc", "spend_share"]
    ].rename(
        columns={
            "campaign": "广告活动",
            "asin": "ASIN",
            "spend": "花费",
            "ad_sales": "广告销售额",
            "acos": "ACOS",
            "roas": "ROAS",
            "ctr": "CTR",
            "cpc": "CPC",
            "spend_share": "花费占比",
        }
    )
    keyword_out = keyword_df[
        ["keyword", "campaign", "match_type", "spend", "ad_orders", "acos", "roas", "ad_cvr", "action"]
    ].rename(
        columns={
            "keyword": "关键词",
            "campaign": "广告活动",
            "match_type": "匹配方式",
            "spend": "花费",
            "ad_orders": "订单",
            "acos": "ACOS",
            "roas": "ROAS",
            "ad_cvr": "广告 CVR",
            "action": "动作",
        }
    )
    weekly_out = weekly[
        ["week_start", "sales", "spend", "ad_sales", "cvr", "ctr", "acos", "roas"]
    ].rename(
        columns={
            "week_start": "周起始",
            "sales": "总销售额",
            "spend": "广告花费",
            "ad_sales": "广告销售额",
            "cvr": "CVR",
            "ctr": "CTR",
            "acos": "ACOS",
            "roas": "ROAS",
        }
    )
    weekly_out["周起始"] = pd.to_datetime(weekly_out["周起始"]).dt.strftime("%Y-%m-%d")

    anomaly_out = anomalies.rename(
        columns={
            "type": "类型",
            "object": "对象",
            "period": "日期/周期",
            "metric": "指标",
            "detail": "说明",
            "action": "建议",
        }
    )
    quality_out = quality.rename(
        columns={"table": "数据表", "issue": "问题", "rows": "行数", "action": "处理"}
    )

    info = pd.DataFrame(
        [
            ["项目", "美区电商广告数据分析 Demo"],
            ["数据性质", "程序生成的模拟数据，不是真实店铺数据"],
            ["分析周期", "{} 至 {}（{} 天）".format(coverage["start"], coverage["end"], coverage["days"])],
            ["ASIN 数量", coverage["asins"]],
            ["生成时间", context["generated_at"]],
            ["指标口径", "ACOS=花费/广告销售额；ROAS=广告销售额/花费；CVR=订单/会话；TACOS=花费/总销售额"],
            ["使用限制", "仅用于作品集演示和面试讲解，不构成真实经营建议"],
        ],
        columns=["字段", "内容"],
    )

    with pd.ExcelWriter(str(path), engine="openpyxl") as writer:
        overview.to_excel(writer, sheet_name="总览", index=False)
        ws = writer.sheets["总览"]
        ws.sheet_view.showGridLines = False
        ws.freeze_panes = "A2"
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF", size=10)
            cell.fill = PatternFill("solid", fgColor="2A78D6")
            cell.alignment = Alignment(horizontal="center")
        for row_index in range(2, len(overview) + 2):
            label = str(overview.iloc[row_index - 2]["指标"])
            cell = ws.cell(row=row_index, column=2)
            if label in {"ACOS", "TACOS", "CVR", "CTR"}:
                cell.number_format = "0.0%"
            elif label == "ROAS":
                cell.number_format = "0.00"
            elif label in {"总订单数", "广告订单数"}:
                cell.number_format = "#,##0"
            else:
                cell.number_format = '"$"#,##0.00'
        for column_cells in ws.columns:
            letter = get_column_letter(column_cells[0].column)
            max_len = max(len(str(cell.value)) for cell in column_cells if cell.value is not None)
            ws.column_dimensions[letter].width = min(48, max(14, max_len * 1.4 + 2))
        ws.row_dimensions[1].height = 24

        _write_excel_sheet(
            writer,
            asin_out,
            "ASIN",
            percent_cols=("ACOS", "CVR", "CTR", "销售占比"),
            money_cols=("总销售额", "广告花费", "广告销售额", "CPC"),
            integer_cols=("订单数",),
            ratio_cols=("ROAS",),
        )
        _write_excel_sheet(
            writer,
            campaign_out,
            "广告活动",
            percent_cols=("ACOS", "CTR", "花费占比"),
            money_cols=("花费", "广告销售额", "CPC"),
            ratio_cols=("ROAS",),
        )
        _write_excel_sheet(
            writer,
            keyword_out,
            "关键词",
            percent_cols=("ACOS", "广告 CVR"),
            money_cols=("花费",),
            integer_cols=("订单",),
            ratio_cols=("ROAS",),
        )
        _write_excel_sheet(
            writer,
            weekly_out,
            "周趋势",
            percent_cols=("CVR", "CTR", "ACOS"),
            money_cols=("总销售额", "广告花费", "广告销售额"),
            ratio_cols=("ROAS",),
        )
        _write_excel_sheet(writer, anomaly_out, "异常", auto_filter=False)
        _write_excel_sheet(writer, quality_out, "数据质量", integer_cols=("行数",), auto_filter=False)
        _write_excel_sheet(writer, info, "说明", auto_filter=False)

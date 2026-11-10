"""一键运行：python run.py

默认读取 data/raw，输出到 reports/ 和 data/processed/。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from ecom_analysis.pipeline import run_pipeline  # noqa: E402


def main() -> None:
    raw_dir = ROOT / "data" / "raw"
    reports_dir = ROOT / "reports"
    context = run_pipeline(raw_dir, reports_dir)

    overall = context["overall"]
    coverage = context["coverage"]
    print("分析完成：{} 至 {}，{} 个 ASIN".format(coverage["start"], coverage["end"], coverage["asins"]))
    print(
        "总销售额 ${:,.2f} | 广告花费 ${:,.2f} | ACOS {:.1%} | ROAS {:.2f} | CVR {:.1%}".format(
            overall["total_sales"],
            overall["ad_spend"],
            overall["acos"],
            overall["roas"],
            overall["cvr"],
        )
    )
    print("异常/待复核：{} 条".format(len(context["anomalies"])))
    print("报告：{}".format(reports_dir / "report.html"))
    print("Excel：{}".format(reports_dir / "summary.xlsx"))
    print("图表：{}".format(reports_dir / "charts"))


if __name__ == "__main__":
    main()

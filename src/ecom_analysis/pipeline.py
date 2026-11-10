"""分析流水线：读取原始 CSV → 清洗 → 汇总 → 图表 → 报告。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict

import pandas as pd

from .charts import generate_charts
from .cleaning import clean_ads, clean_keywords, clean_sales
from .metrics import (
    asin_summary,
    campaign_summary,
    detect_anomalies,
    keyword_summary,
    overall_metrics,
    weekly_trend,
)
from .report import write_excel, write_html, write_markdown

RAW_FILES = {
    "sales": "sales_daily.csv",
    "ads": "ads_daily.csv",
    "keywords": "keyword_daily.csv",
}


def load_raw(raw_dir: Path) -> Dict[str, pd.DataFrame]:
    raw: Dict[str, pd.DataFrame] = {}
    for key, filename in RAW_FILES.items():
        path = raw_dir / filename
        if not path.exists():
            raise FileNotFoundError(
                "找不到 {}。请先运行：python scripts/generate_sample_data.py".format(path)
            )
        raw[key] = pd.read_csv(str(path), dtype=str, keep_default_na=False)
    return raw


def run_pipeline(raw_dir: Path, out_dir: Path) -> Dict[str, object]:
    raw = load_raw(raw_dir)
    raw_counts = {key: len(df) for key, df in raw.items()}

    sales, sales_log = clean_sales(raw["sales"])
    valid_asins = set(sales["asin"].unique())
    ads, ads_log = clean_ads(raw["ads"], valid_asins=valid_asins)
    keywords, keyword_log = clean_keywords(raw["keywords"], valid_asins=valid_asins)

    quality = pd.DataFrame(
        sales_log + ads_log + keyword_log,
        columns=["table", "issue", "rows", "action"],
    )

    overall = overall_metrics(sales, ads)
    asin_df = asin_summary(sales, ads)
    campaign_df = campaign_summary(ads)
    keyword_df = keyword_summary(keywords)
    weekly = weekly_trend(sales, ads)
    anomalies = detect_anomalies(sales, ads, asin_df, keyword_df)

    processed_dir = out_dir.parent / "data" / "processed"
    chart_dir = out_dir / "charts"
    processed_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)

    sales.to_csv(str(processed_dir / "cleaned_sales.csv"), index=False, encoding="utf-8-sig")
    ads.to_csv(str(processed_dir / "cleaned_ads.csv"), index=False, encoding="utf-8-sig")
    keywords.to_csv(
        str(processed_dir / "cleaned_keywords.csv"), index=False, encoding="utf-8-sig"
    )
    asin_df.to_csv(str(processed_dir / "asin_summary.csv"), index=False, encoding="utf-8-sig")
    keyword_df.to_csv(
        str(processed_dir / "keyword_summary.csv"), index=False, encoding="utf-8-sig"
    )
    weekly.to_csv(str(processed_dir / "weekly_trend.csv"), index=False, encoding="utf-8-sig")
    anomalies.to_csv(str(processed_dir / "anomalies.csv"), index=False, encoding="utf-8-sig")
    quality.to_csv(str(processed_dir / "data_quality.csv"), index=False, encoding="utf-8-sig")

    context: Dict[str, object] = {
        "sales": sales,
        "ads": ads,
        "keywords": keywords,
        "overall": overall,
        "asin": asin_df,
        "campaign": campaign_df,
        "keyword": keyword_df,
        "weekly": weekly,
        "anomalies": anomalies,
        "quality": quality,
        "raw_counts": raw_counts,
        "coverage": {
            "start": sales["date"].min().strftime("%Y-%m-%d"),
            "end": sales["date"].max().strftime("%Y-%m-%d"),
            "days": int(sales["date"].nunique()),
            "asins": int(sales["asin"].nunique()),
        },
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    charts = generate_charts(asin_df, weekly, chart_dir)
    context["charts"] = charts

    write_markdown(context, out_dir / "report.md")
    write_html(context, out_dir / "report.html")
    write_excel(context, out_dir / "summary.xlsx")
    return context

"""生成可复现的模拟原始数据。

数据全部是虚构的：6 个虚构 ASIN、6 个虚构广告活动、28 天（2026-10-01 起）。
脚本故意写入重复、货币字符串、负数、缺失值、点击大于曝光、未知 ASIN 等脏数据，
用来演示清洗流程；这些行不是真实业务数据。
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20261110
START = date(2026, 10, 1)
DAYS = 28

ASINS = [
    {
        "asin": "B0DEMO001",
        "sku": "DEMO-COFFEE-01",
        "price": 25.99,
        "sessions": 420,
        "cvr": 0.095,
        "buy_box": 97.0,
        "returns": 0.8,
        "campaign": "SP-Auto-Coffee",
        "cpc": 0.55,
        "impressions_per_click": 18,
    },
    {
        "asin": "B0DEMO002",
        "sku": "DEMO-PET-01",
        "price": 18.99,
        "sessions": 300,
        "cvr": 0.075,
        "buy_box": 93.0,
        "returns": 2.0,
        "campaign": "SP-Auto-Pet",
        "cpc": 0.55,
        "impressions_per_click": 16,
    },
    {
        "asin": "B0DEMO003",
        "sku": "DEMO-CAMP-01",
        "price": 32.50,
        "sessions": 180,
        "cvr": 0.045,
        "buy_box": 88.0,
        "returns": 3.5,
        "campaign": "SP-Manual-Camping",
        "cpc": 0.72,
        "impressions_per_click": 14,
    },
    {
        "asin": "B0DEMO004",
        "sku": "DEMO-SILICONE-01",
        "price": 15.99,
        "sessions": 520,
        "cvr": 0.110,
        "buy_box": 99.0,
        "returns": 0.5,
        "campaign": "SBV-Silicone",
        "cpc": 0.30,
        "impressions_per_click": 22,
    },
    {
        "asin": "B0DEMO005",
        "sku": "DEMO-YOGA-01",
        "price": 21.50,
        "sessions": 260,
        "cvr": 0.060,
        "buy_box": 95.0,
        "returns": 1.5,
        "campaign": "SP-Auto-Yoga",
        "cpc": 0.38,
        "impressions_per_click": 17,
    },
    {
        "asin": "B0DEMO006",
        "sku": "DEMO-STAND-01",
        "price": 12.99,
        "sessions": 150,
        "cvr": 0.085,
        "buy_box": 91.0,
        "returns": 2.2,
        "campaign": "SP-Auto-Stand",
        "cpc": 0.42,
        "impressions_per_click": 15,
    },
]

# (关键词, 花费占比, 广告销售额占比, 匹配方式)
# 002 的 “pet hair remover” 故意设置成 65% 花费、0 销售，用来演示否词。
KEYWORD_SPLITS = {
    "B0DEMO001": [
        ("coffee filter cup", 0.55, 0.55, "BROAD"),
        ("portable coffee maker", 0.45, 0.45, "PHRASE"),
    ],
    "B0DEMO002": [
        ("pet hair remover", 0.65, 0.00, "BROAD"),
        ("pet brush for shedding", 0.35, 1.00, "PHRASE"),
    ],
    "B0DEMO003": [
        ("camping lantern rechargeable", 0.45, 0.60, "BROAD"),
        ("led camping light", 0.55, 0.40, "PHRASE"),
    ],
    "B0DEMO004": [
        ("silicone storage bag", 0.55, 0.55, "BROAD"),
        ("reusable food bag", 0.45, 0.45, "PHRASE"),
    ],
    "B0DEMO005": [
        ("yoga stretching strap", 0.60, 0.40, "BROAD"),
        ("stretch strap for flexibility", 0.40, 0.60, "PHRASE"),
    ],
    "B0DEMO006": [
        ("phone stand desk", 0.50, 0.50, "BROAD"),
        ("adjustable phone holder", 0.50, 0.50, "PHRASE"),
    ],
}


def generate() -> None:
    rng = np.random.default_rng(SEED)
    sales_rows = []
    ads_rows = []
    keyword_rows = []

    for day_index in range(DAYS):
        current_day = START + timedelta(days=day_index)
        weekday = current_day.weekday()
        weekday_factor = 1.0
        if weekday >= 5:
            weekday_factor = 1.12
        elif weekday == 0:
            weekday_factor = 0.95
        elif weekday == 4:
            weekday_factor = 1.06
        trend_factor = 1.0 + 0.05 * (day_index / DAYS)

        for config in ASINS:
            asin = config["asin"]
            price = float(config["price"])

            sessions = int(
                round(
                    float(config["sessions"])
                    * weekday_factor
                    * trend_factor
                    * max(0.70, min(1.30, float(rng.normal(1.0, 0.09))))
                )
            )
            sessions = max(40, sessions)

            cvr = float(config["cvr"]) * max(
                0.82, min(1.18, float(rng.normal(1.0, 0.08)))
            )
            # 002 从第 15 天开始连续 14 天转化率减半，制造“ACOS 恶化 + CVR 下滑”
            if asin == "B0DEMO002" and 14 <= day_index < 28:
                cvr *= 0.48
            cvr = max(0.008, min(0.22, cvr))
            units = max(0, int(round(sessions * cvr)))
            sales = round(units * price, 2)

            buy_box = round(
                min(100.0, max(80.0, float(config["buy_box"]) + float(rng.normal(0, 0.9)))),
                1,
            )
            returns = min(units, int(rng.poisson(float(config["returns"]))))

            clicks = int(round(sessions * 0.36 * max(0.85, min(1.15, float(rng.normal(1.0, 0.07))))))
            clicks = max(1, min(sessions, clicks))
            impressions = max(
                clicks,
                int(round(clicks * float(config["impressions_per_click"]) * max(0.80, min(1.20, float(rng.normal(1.0, 0.10)))))),
            )
            cpc = max(0.15, float(config["cpc"]) * max(0.88, min(1.12, float(rng.normal(1.0, 0.06)))))
            spend = round(clicks * cpc, 2)
            attributed_orders = max(
                0,
                min(
                    clicks,
                    int(round(units * 0.42 * max(0.85, min(1.15, float(rng.normal(1.0, 0.10)))))),
                ),
            )
            attributed_sales = round(attributed_orders * price, 2)

            # 001 在第 17 天出现“花费尖峰 + 零归因订单”
            if asin == "B0DEMO001" and day_index == 16:
                clicks = min(sessions, clicks + 90)
                impressions = clicks * 18
                spend = round(spend * 3.2, 2)
                attributed_orders = 0
                attributed_sales = 0.0

            sales_rows.append(
                {
                    "date": current_day.isoformat(),
                    "asin": asin,
                    "sku": config["sku"],
                    "sessions": sessions,
                    "units_ordered": units,
                    "ordered_product_sales": sales,
                    "buy_box_percentage": buy_box,
                    "returns": returns,
                    "currency": "USD",
                }
            )
            ads_rows.append(
                {
                    "date": current_day.isoformat(),
                    "asin": asin,
                    "campaign": config["campaign"],
                    "impressions": impressions,
                    "clicks": clicks,
                    "spend": spend,
                    "attributed_sales": attributed_sales,
                    "attributed_orders": attributed_orders,
                }
            )

            for keyword, spend_share, sales_share, match_type in KEYWORD_SPLITS[asin]:
                keyword_clicks = int(round(clicks * spend_share))
                keyword_impressions = max(
                    keyword_clicks, int(round(impressions * spend_share))
                )
                keyword_rows.append(
                    {
                        "date": current_day.isoformat(),
                        "campaign": config["campaign"],
                        "keyword": keyword,
                        "match_type": match_type,
                        "impressions": keyword_impressions,
                        "clicks": keyword_clicks,
                        "spend": round(spend * spend_share, 2),
                        "attributed_sales": round(attributed_sales * sales_share, 2),
                        "attributed_orders": int(round(attributed_orders * sales_share)),
                    }
                )

    sales_df = pd.DataFrame(sales_rows)
    ads_df = pd.DataFrame(ads_rows)
    keyword_df = pd.DataFrame(keyword_rows)

    # ---- 故意注入脏数据：每一类都对应 cleaning.py 里的一条规则 ----
    sales_df = pd.concat([sales_df, sales_df.iloc[[5]]], ignore_index=True)
    sales_df.loc[20, "asin"] = " b0demo003 "          # 前后空格 + 小写
    sales_df.loc[30, "units_ordered"] = -3            # 负数
    sales_df.loc[30, "ordered_product_sales"] = -77.97
    sales_df.loc[40, "sessions"] = ""                 # 缺失会话
    sales_df.loc[50, "date"] = "2026/10/12"           # 混合日期格式
    sales_df.loc[60, "ordered_product_sales"] = ""    # 缺失销售额

    ads_df = pd.concat([ads_df, ads_df.iloc[[10]]], ignore_index=True)
    ads_df.loc[20, "spend"] = "$123.45"               # 货币字符串
    ads_df.loc[30, "impressions"] = 100                # 点击 > 曝光
    ads_df.loc[30, "clicks"] = 150
    ads_df.loc[40, "spend"] = ""                       # 缺失花费
    ads_df.loc[50, "asin"] = "B0UNKNOWN"               # 销售表不存在的 ASIN
    ads_df.loc[50, "campaign"] = "SP-Unknown"

    keyword_df = pd.concat([keyword_df, keyword_df.iloc[[15]]], ignore_index=True)
    keyword_df.loc[25, "spend"] = "$12.30"             # 货币字符串
    keyword_df.loc[35, "attributed_orders"] = ""       # 缺失订单

    raw_dir = Path(__file__).resolve().parents[1] / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    sales_df.to_csv(raw_dir / "sales_daily.csv", index=False, encoding="utf-8")
    ads_df.to_csv(raw_dir / "ads_daily.csv", index=False, encoding="utf-8")
    keyword_df.to_csv(raw_dir / "keyword_daily.csv", index=False, encoding="utf-8")

    print("已生成模拟数据：")
    print("  销售日报 {} 行".format(len(sales_df)))
    print("  广告日报 {} 行".format(len(ads_df)))
    print("  关键词日报 {} 行".format(len(keyword_df)))
    print("目录：{}".format(raw_dir))


if __name__ == "__main__":
    generate()

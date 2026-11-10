"""指标计算、维度汇总与异常识别。"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd


def _safe_scalar(numerator: float, denominator: float) -> float:
    if denominator is None or pd.isna(denominator) or float(denominator) == 0:
        return float("nan")
    return float(numerator) / float(denominator)


def safe_divide_series(numerator: pd.Series, denominator: object) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    if np.isscalar(denominator):
        if pd.isna(denominator) or float(denominator) == 0:
            return pd.Series(np.nan, index=num.index, dtype="float64")
        return num / float(denominator)
    den = pd.to_numeric(denominator, errors="coerce").replace({0: np.nan})
    return num.div(den)


def overall_metrics(sales: pd.DataFrame, ads: pd.DataFrame) -> Dict[str, float]:
    """计算店铺级核心指标。"""
    total_sales = float(sales["ordered_product_sales"].sum())
    total_units = int(sales["units_ordered"].sum())
    total_sessions = int(sales["sessions"].sum())
    ad_spend = float(ads["spend"].sum())
    ad_sales = float(ads["attributed_sales"].sum())
    ad_orders = int(ads["attributed_orders"].sum())
    impressions = int(ads["impressions"].sum())
    clicks = int(ads["clicks"].sum())

    return {
        "total_sales": total_sales,
        "total_units": total_units,
        "total_sessions": total_sessions,
        "cvr": _safe_scalar(total_units, total_sessions),
        "aov": _safe_scalar(total_sales, total_units),
        "ad_spend": ad_spend,
        "ad_sales": ad_sales,
        "ad_orders": ad_orders,
        "impressions": impressions,
        "clicks": clicks,
        "ctr": _safe_scalar(clicks, impressions),
        "cpc": _safe_scalar(ad_spend, clicks),
        "ad_cvr": _safe_scalar(ad_orders, clicks),
        "acos": _safe_scalar(ad_spend, ad_sales),
        "roas": _safe_scalar(ad_sales, ad_spend),
        "tacos": _safe_scalar(ad_spend, total_sales),
        "ad_sales_share": _safe_scalar(ad_sales, total_sales),
    }


def _asin_advice(row: pd.Series) -> str:
    spend = float(row.get("spend", 0) or 0)
    acos = row.get("acos", np.nan)
    cvr = row.get("cvr", np.nan)
    ad_sales = float(row.get("ad_sales", 0) or 0)

    if spend <= 0:
        return "无广告"
    if ad_sales <= 0 and spend >= 10:
        return "暂停 / 查归因"
    if not pd.isna(acos) and acos > 0.40 and spend >= 100:
        return "降预算，查 Listing"
    if not pd.isna(cvr) and cvr < 0.04:
        return "先修转化"
    if not pd.isna(acos) and acos <= 0.20 and not pd.isna(cvr) and cvr >= 0.06:
        return "加预算"
    return "维持观察"


def asin_summary(sales: pd.DataFrame, ads: pd.DataFrame) -> pd.DataFrame:
    """按 ASIN 汇总销售和广告指标。"""
    sales_agg = (
        sales.groupby("asin", as_index=False)
        .agg(
            sessions=("sessions", "sum"),
            units=("units_ordered", "sum"),
            sales=("ordered_product_sales", "sum"),
        )
    )
    ads_agg = (
        ads.groupby("asin", as_index=False)
        .agg(
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            spend=("spend", "sum"),
            ad_sales=("attributed_sales", "sum"),
            ad_orders=("attributed_orders", "sum"),
        )
    )
    out = sales_agg.merge(ads_agg, on="asin", how="outer")
    numeric_cols = [
        "sessions",
        "units",
        "sales",
        "impressions",
        "clicks",
        "spend",
        "ad_sales",
        "ad_orders",
    ]
    out[numeric_cols] = out[numeric_cols].fillna(0)

    out["cvr"] = safe_divide_series(out["units"], out["sessions"])
    out["aov"] = safe_divide_series(out["sales"], out["units"])
    out["ctr"] = safe_divide_series(out["clicks"], out["impressions"])
    out["cpc"] = safe_divide_series(out["spend"], out["clicks"])
    out["ad_cvr"] = safe_divide_series(out["ad_orders"], out["clicks"])
    out["acos"] = safe_divide_series(out["spend"], out["ad_sales"])
    out["roas"] = safe_divide_series(out["ad_sales"], out["spend"])
    out["sales_share"] = safe_divide_series(out["sales"], out["sales"].sum())
    out["spend_share"] = safe_divide_series(out["spend"], out["spend"].sum())
    if out.empty:
        # pandas 2.x 对空表 apply 会返回 DataFrame，不能直接赋给单列
        out["advice"] = pd.Series(dtype="object")
    else:
        out["advice"] = out.apply(_asin_advice, axis=1)

    return out.sort_values(["sales", "asin"], ascending=[False, True]).reset_index(drop=True)


def campaign_summary(ads: pd.DataFrame) -> pd.DataFrame:
    out = (
        ads.groupby(["campaign", "asin"], as_index=False)
        .agg(
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            spend=("spend", "sum"),
            ad_sales=("attributed_sales", "sum"),
            ad_orders=("attributed_orders", "sum"),
        )
    )
    out["ctr"] = safe_divide_series(out["clicks"], out["impressions"])
    out["cpc"] = safe_divide_series(out["spend"], out["clicks"])
    out["ad_cvr"] = safe_divide_series(out["ad_orders"], out["clicks"])
    out["acos"] = safe_divide_series(out["spend"], out["ad_sales"])
    out["roas"] = safe_divide_series(out["ad_sales"], out["spend"])
    out["spend_share"] = safe_divide_series(out["spend"], out["spend"].sum())
    return out.sort_values(["spend", "campaign"], ascending=[False, True]).reset_index(drop=True)


def _keyword_action(row: pd.Series) -> str:
    spend = float(row.get("spend", 0) or 0)
    orders = int(row.get("ad_orders", 0) or 0)
    acos = row.get("acos", np.nan)

    if spend >= 30 and orders == 0:
        return "加入否词"
    if not pd.isna(acos) and acos > 0.40 and spend >= 50:
        return "降价 / 收词"
    if not pd.isna(acos) and acos < 0.20 and orders >= 5:
        return "加预算"
    return "继续观察"


def keyword_summary(keywords: pd.DataFrame) -> pd.DataFrame:
    out = (
        keywords.groupby(["keyword", "campaign", "match_type"], as_index=False)
        .agg(
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            spend=("spend", "sum"),
            ad_sales=("attributed_sales", "sum"),
            ad_orders=("attributed_orders", "sum"),
        )
    )
    out["ctr"] = safe_divide_series(out["clicks"], out["impressions"])
    out["cpc"] = safe_divide_series(out["spend"], out["clicks"])
    out["ad_cvr"] = safe_divide_series(out["ad_orders"], out["clicks"])
    out["acos"] = safe_divide_series(out["spend"], out["ad_sales"])
    out["roas"] = safe_divide_series(out["ad_sales"], out["spend"])
    if out.empty:
        out["action"] = pd.Series(dtype="object")
    else:
        out["action"] = out.apply(_keyword_action, axis=1)
    return out.sort_values(["spend", "keyword"], ascending=[False, True]).reset_index(drop=True)


def weekly_trend(sales: pd.DataFrame, ads: pd.DataFrame) -> pd.DataFrame:
    """按自然周（周日为周末）汇总销售和广告指标。"""
    s = sales.copy()
    a = ads.copy()
    s["week_start"] = s["date"].dt.to_period("W-SUN").dt.start_time
    a["week_start"] = a["date"].dt.to_period("W-SUN").dt.start_time

    sales_weekly = (
        s.groupby("week_start", as_index=False)
        .agg(
            sessions=("sessions", "sum"),
            units=("units_ordered", "sum"),
            sales=("ordered_product_sales", "sum"),
        )
    )
    ads_weekly = (
        a.groupby("week_start", as_index=False)
        .agg(
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            spend=("spend", "sum"),
            ad_sales=("attributed_sales", "sum"),
            ad_orders=("attributed_orders", "sum"),
        )
    )
    out = sales_weekly.merge(ads_weekly, on="week_start", how="outer").sort_values("week_start")
    numeric_cols = [
        "sessions",
        "units",
        "sales",
        "impressions",
        "clicks",
        "spend",
        "ad_sales",
        "ad_orders",
    ]
    out[numeric_cols] = out[numeric_cols].fillna(0)
    out["cvr"] = safe_divide_series(out["units"], out["sessions"])
    out["ctr"] = safe_divide_series(out["clicks"], out["impressions"])
    out["cpc"] = safe_divide_series(out["spend"], out["clicks"])
    out["acos"] = safe_divide_series(out["spend"], out["ad_sales"])
    out["roas"] = safe_divide_series(out["ad_sales"], out["spend"])
    return out.reset_index(drop=True)


def detect_anomalies(
    sales: pd.DataFrame,
    ads: pd.DataFrame,
    asin_df: pd.DataFrame,
    keyword_df: pd.DataFrame,
) -> pd.DataFrame:
    """识别值得人工复核的异常，不自动下结论。"""
    records: List[Dict[str, object]] = []
    period_label = "本周期 {} 天".format(int(sales["date"].nunique()))

    # 1) 单日花费尖峰且没有归因订单
    ads_daily = ads.copy()
    ads_daily["asin_median_spend"] = ads_daily.groupby("asin")["spend"].transform("median")
    spikes = ads_daily[
        (ads_daily["asin_median_spend"] > 0)
        & (ads_daily["spend"] >= ads_daily["asin_median_spend"] * 2.5)
        & (ads_daily["spend"] >= 20)
        & (ads_daily["attributed_orders"] == 0)
    ]
    for _, row in spikes.iterrows():
        multiple = row["spend"] / row["asin_median_spend"]
        records.append(
            {
                "type": "广告花费异常",
                "object": "{} / {}".format(row["asin"], row["campaign"]),
                "period": row["date"].strftime("%Y-%m-%d"),
                "metric": "花费 ${:,.2f}，订单 0".format(row["spend"]),
                "detail": "单日花费为同 ASIN 中位数的 {:.1f} 倍，但没有归因订单".format(multiple),
                "action": "先核对广告后台与归因延迟；当天降预算，避免继续空烧",
            }
        )

    # 2) ASIN 整体 ACOS 过高
    high_acos = asin_df[(asin_df["acos"] > 0.40) & (asin_df["spend"] >= 100)]
    for _, row in high_acos.iterrows():
        records.append(
            {
                "type": "ASIN ACOS 偏高",
                "object": row["asin"],
                "period": period_label,
                "metric": "ACOS {:.1%}，花费 ${:,.2f}".format(row["acos"], row["spend"]),
                "detail": "CVR {:.1%}，广告销售额 ${:,.2f}".format(row["cvr"], row["ad_sales"]),
                "action": "降预算并检查关键词、价格、评分和 Listing 转化",
            }
        )

    # 3) ASIN 周 CVR 环比大幅下滑
    weekly_asin = (
        sales.assign(week_start=sales["date"].dt.to_period("W-SUN").dt.start_time)
        .groupby(["asin", "week_start"], as_index=False)
        .agg(sessions=("sessions", "sum"), units=("units_ordered", "sum"))
    )
    weekly_asin["cvr"] = safe_divide_series(weekly_asin["units"], weekly_asin["sessions"])
    weekly_asin = weekly_asin.sort_values(["asin", "week_start"])
    weekly_asin["prev_cvr"] = weekly_asin.groupby("asin")["cvr"].shift(1)
    drops = weekly_asin[
        (weekly_asin["prev_cvr"] > 0.03)
        & (weekly_asin["cvr"] < weekly_asin["prev_cvr"] * 0.70)
    ]
    for _, row in drops.iterrows():
        change = row["cvr"] / row["prev_cvr"] - 1
        records.append(
            {
                "type": "CVR 环比下滑",
                "object": row["asin"],
                "period": "{} 起的一周".format(row["week_start"].strftime("%Y-%m-%d")),
                "metric": "{:.1%} → {:.1%}".format(row["prev_cvr"], row["cvr"]),
                "detail": "周 CVR 环比变化 {:.0%}".format(change),
                "action": "排查库存、价格、差评、配送时效和广告流量结构",
            }
        )

    # 4) 有花费但零订单的关键词
    wasted_keywords = keyword_df[
        (keyword_df["spend"] >= 30) & (keyword_df["ad_orders"] == 0)
    ]
    for _, row in wasted_keywords.head(10).iterrows():
        records.append(
            {
                "type": "关键词浪费",
                "object": row["keyword"],
                "period": period_label,
                "metric": "花费 ${:,.2f}，订单 0".format(row["spend"]),
                "detail": "广告活动：{}，点击 {} 次".format(row["campaign"], row["clicks"]),
                "action": "加入否词或转为精准匹配，先止损再测试",
            }
        )

    if not records:
        return pd.DataFrame(
            columns=["type", "object", "period", "metric", "detail", "action"]
        )
    return pd.DataFrame(records)

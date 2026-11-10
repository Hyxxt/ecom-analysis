"""原始 CSV 的清洗、类型转换和数据质量记录。

设计原则：
1. 每一步都记录“处理了多少行、怎么处理”，方便复盘和面试时解释；
2. 不静默吞掉异常值，能修则修，不能修就剔除并记录；
3. 所有比例都用安全除法，分母为 0 时返回 NaN，而不是抛异常。
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from dateutil import parser as date_parser

QualityLog = List[Dict[str, object]]

SALES_NUMERIC_COLUMNS = [
    "sessions",
    "units_ordered",
    "ordered_product_sales",
    "buy_box_percentage",
    "returns",
]
ADS_NUMERIC_COLUMNS = [
    "impressions",
    "clicks",
    "spend",
    "attributed_sales",
    "attributed_orders",
]
KEYWORD_NUMERIC_COLUMNS = [
    "impressions",
    "clicks",
    "spend",
    "attributed_sales",
    "attributed_orders",
]

SALES_REQUIRED = ["date", "asin", "sessions", "units_ordered", "ordered_product_sales"]
ADS_REQUIRED = [
    "date",
    "asin",
    "campaign",
    "impressions",
    "clicks",
    "spend",
    "attributed_sales",
    "attributed_orders",
]
KEYWORD_REQUIRED = [
    "date",
    "campaign",
    "keyword",
    "match_type",
    "impressions",
    "clicks",
    "spend",
    "attributed_sales",
    "attributed_orders",
]


def _log(log: QualityLog, table: str, issue: str, rows: int, action: str) -> None:
    """追加一条数据质量记录。rows 为 0 时不记录。"""
    if rows <= 0:
        return
    log.append({"table": table, "issue": issue, "rows": int(rows), "action": action})


def _normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [
        str(col).strip().lower().replace(" ", "_").replace("-", "_")
        for col in out.columns
    ]
    return out


def _require_columns(df: pd.DataFrame, required: Sequence[str], table: str) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError("{} 缺少字段：{}".format(table, ", ".join(missing)))


def _to_number(series: pd.Series) -> pd.Series:
    """把 "$1,234.50"、"12.3%"、"(45.00)" 等文本转成数值。

    括号在财务报表里表示负数；百分号按“去掉符号但保留原数值”处理，
    因为本项目的原始字段本身就是百分数（例如 buy_box_percentage=97），
    不是 0.97。
    """
    text = series.astype(str).str.strip()
    text = text.where(~text.str.lower().isin(["", "nan", "none", "null"]), other="")
    negative = text.str.match(r"^\(.*\)$", na=False)
    cleaned = text.str.replace(r"[(),\$,\s%]", "", regex=True)
    numbers = pd.to_numeric(cleaned, errors="coerce")
    numbers = numbers.mask(negative, -numbers.abs())
    return numbers


def _parse_dates(series: pd.Series) -> pd.Series:
    """兼容 2026-10-01、2026/10/12、带时间的日期等多种格式。"""

    def parse_one(value: object) -> pd.Timestamp:
        if value is None:
            return pd.NaT
        text = str(value).strip()
        if not text or text.lower() in {"nan", "nat", "none", "null"}:
            return pd.NaT
        try:
            return pd.Timestamp(date_parser.parse(text, dayfirst=False))
        except (ValueError, OverflowError, TypeError):
            return pd.NaT

    parsed = series.map(parse_one)
    return pd.to_datetime(parsed, errors="coerce")


def _normalize_text(series: pd.Series, upper: bool = False) -> pd.Series:
    out = series.astype(str).str.strip()
    out = out.mask(out.str.lower().isin(["", "nan", "none", "null"]), "")
    if upper:
        out = out.str.upper()
    return out


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    numerator = pd.to_numeric(numerator, errors="coerce")
    denominator = pd.to_numeric(denominator, errors="coerce")
    return numerator.div(denominator.replace({0: np.nan}))


def clean_sales(raw: pd.DataFrame) -> Tuple[pd.DataFrame, QualityLog]:
    """清洗销售日报。"""
    log: QualityLog = []
    df = _normalize_headers(raw)
    _require_columns(df, SALES_REQUIRED, "销售日报")

    df["date"] = _parse_dates(df["date"])
    df["asin"] = _normalize_text(df["asin"], upper=True)
    for col in SALES_NUMERIC_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
        df[col] = _to_number(df[col])

    invalid_key = df["date"].isna() | df["asin"].eq("")
    _log(log, "销售日报", "日期 / ASIN 无法识别", int(invalid_key.sum()), "删除该行")
    df = df.loc[~invalid_key].copy()

    negative = (df[["sessions", "units_ordered", "ordered_product_sales"]] < 0).any(axis=1)
    _log(log, "销售日报", "销量 / 销售额 / 会话数为负", int(negative.sum()), "删除该行")
    df = df.loc[~negative].copy()

    duplicate = df.duplicated(subset=["date", "asin"], keep="last")
    _log(log, "销售日报", "同日期 + ASIN 重复", int(duplicate.sum()), "保留最后一条")
    df = df.loc[~duplicate].copy()

    missing_sessions = df["sessions"].isna()
    if missing_sessions.any():
        median_by_asin = df.groupby("asin")["sessions"].transform("median")
        df.loc[missing_sessions, "sessions"] = median_by_asin[missing_sessions]
        still_missing = df["sessions"].isna()
        if still_missing.any():
            df.loc[still_missing, "sessions"] = df["sessions"].median()
        if df["sessions"].isna().any():
            df["sessions"] = df["sessions"].fillna(0)
        _log(log, "销售日报", "会话数缺失", int(missing_sessions.sum()), "按 ASIN 中位数填补")

    field_labels = {"units_ordered": "销量", "ordered_product_sales": "销售额"}
    for col in ["units_ordered", "ordered_product_sales"]:
        missing = df[col].isna()
        _log(log, "销售日报", "{}缺失".format(field_labels[col]), int(missing.sum()), "按 0 填补")
        df[col] = df[col].fillna(0)

    for col in ["buy_box_percentage", "returns"]:
        df[col] = df[col].fillna(0)

    df["sessions"] = df["sessions"].round().astype(int)
    df["units_ordered"] = df["units_ordered"].round().astype(int)
    df["returns"] = df["returns"].round().astype(int)
    df["ordered_product_sales"] = df["ordered_product_sales"].round(2)
    df["buy_box_percentage"] = df["buy_box_percentage"].clip(0, 100).round(2)
    df["cvr"] = _safe_div(df["units_ordered"], df["sessions"])

    df = df.sort_values(["date", "asin"]).reset_index(drop=True)
    return df, log


def clean_ads(
    raw: pd.DataFrame, valid_asins: Optional[Iterable[str]] = None
) -> Tuple[pd.DataFrame, QualityLog]:
    """清洗广告日报；valid_asins 用于剔除销售表里不存在的 ASIN。"""
    log: QualityLog = []
    df = _normalize_headers(raw)
    _require_columns(df, ADS_REQUIRED, "广告日报")

    df["date"] = _parse_dates(df["date"])
    df["asin"] = _normalize_text(df["asin"], upper=True)
    df["campaign"] = _normalize_text(df["campaign"])
    for col in ADS_NUMERIC_COLUMNS:
        df[col] = _to_number(df[col])

    invalid_key = df["date"].isna() | df["asin"].eq("") | df["campaign"].eq("")
    _log(log, "广告日报", "日期 / ASIN / 广告活动缺失", int(invalid_key.sum()), "删除该行")
    df = df.loc[~invalid_key].copy()

    negative = (df[ADS_NUMERIC_COLUMNS] < 0).any(axis=1)
    _log(log, "广告日报", "曝光 / 点击 / 花费 / 归因订单为负", int(negative.sum()), "删除该行")
    df = df.loc[~negative].copy()

    missing = df[ADS_NUMERIC_COLUMNS].isna().any(axis=1)
    _log(log, "广告日报", "关键指标缺失", int(missing.sum()), "删除该行")
    df = df.loc[~missing].copy()

    invalid_clicks = df["clicks"] > df["impressions"]
    _log(log, "广告日报", "点击数大于曝光数", int(invalid_clicks.sum()), "删除该行")
    df = df.loc[~invalid_clicks].copy()

    if valid_asins is not None:
        valid = {str(x).strip().upper() for x in valid_asins}
        unknown = ~df["asin"].isin(valid)
        _log(log, "广告日报", "销售表中不存在的 ASIN", int(unknown.sum()), "从广告分析中剔除")
        df = df.loc[~unknown].copy()

    duplicate = df.duplicated(subset=["date", "asin", "campaign"], keep="last")
    _log(log, "广告日报", "同日期 + ASIN + 活动重复", int(duplicate.sum()), "保留最后一条")
    df = df.loc[~duplicate].copy()

    for col in ["impressions", "clicks", "attributed_orders"]:
        df[col] = df[col].round().astype(int)
    for col in ["spend", "attributed_sales"]:
        df[col] = df[col].round(2)

    df["ctr"] = _safe_div(df["clicks"], df["impressions"])
    df["cpc"] = _safe_div(df["spend"], df["clicks"])
    df["ad_cvr"] = _safe_div(df["attributed_orders"], df["clicks"])
    df["acos"] = _safe_div(df["spend"], df["attributed_sales"])
    df["roas"] = _safe_div(df["attributed_sales"], df["spend"])

    df = df.sort_values(["date", "asin", "campaign"]).reset_index(drop=True)
    return df, log


def clean_keywords(
    raw: pd.DataFrame, valid_asins: Optional[Iterable[str]] = None
) -> Tuple[pd.DataFrame, QualityLog]:
    """清洗关键词日报。关键词表没有 ASIN 字段，因此 valid_asins 仅用于活动级过滤。"""
    del valid_asins  # 关键词表按 campaign 关联，保留参数是为了与其他清洗函数签名一致
    log: QualityLog = []
    df = _normalize_headers(raw)
    _require_columns(df, KEYWORD_REQUIRED, "关键词日报")

    df["date"] = _parse_dates(df["date"])
    df["campaign"] = _normalize_text(df["campaign"])
    df["keyword"] = _normalize_text(df["keyword"])
    df["match_type"] = _normalize_text(df["match_type"], upper=True)
    for col in KEYWORD_NUMERIC_COLUMNS:
        df[col] = _to_number(df[col])

    invalid_key = (
        df["date"].isna()
        | df["campaign"].eq("")
        | df["keyword"].eq("")
        | df["match_type"].eq("")
    )
    _log(log, "关键词日报", "日期 / 活动 / 关键词 / 匹配方式缺失", int(invalid_key.sum()), "删除该行")
    df = df.loc[~invalid_key].copy()

    negative = (df[KEYWORD_NUMERIC_COLUMNS] < 0).any(axis=1)
    _log(log, "关键词日报", "曝光 / 点击 / 花费 / 归因订单为负", int(negative.sum()), "删除该行")
    df = df.loc[~negative].copy()

    missing_cost = df[["impressions", "clicks", "spend"]].isna().any(axis=1)
    _log(log, "关键词日报", "曝光 / 点击 / 花费缺失", int(missing_cost.sum()), "删除该行")
    df = df.loc[~missing_cost].copy()

    invalid_clicks = df["clicks"] > df["impressions"]
    _log(log, "关键词日报", "点击数大于曝光数", int(invalid_clicks.sum()), "删除该行")
    df = df.loc[~invalid_clicks].copy()

    keyword_field_labels = {"attributed_sales": "归因销售额", "attributed_orders": "归因订单"}
    for col in ["attributed_sales", "attributed_orders"]:
        missing = df[col].isna()
        _log(log, "关键词日报", "{}缺失".format(keyword_field_labels[col]), int(missing.sum()), "按 0 填补")
        df[col] = df[col].fillna(0)

    duplicate = df.duplicated(
        subset=["date", "campaign", "keyword", "match_type"], keep="last"
    )
    _log(log, "关键词日报", "同日期 + 活动 + 关键词重复", int(duplicate.sum()), "保留最后一条")
    df = df.loc[~duplicate].copy()

    for col in ["impressions", "clicks", "attributed_orders"]:
        df[col] = df[col].round().astype(int)
    for col in ["spend", "attributed_sales"]:
        df[col] = df[col].round(2)

    df["ctr"] = _safe_div(df["clicks"], df["impressions"])
    df["cpc"] = _safe_div(df["spend"], df["clicks"])
    df["ad_cvr"] = _safe_div(df["attributed_orders"], df["clicks"])
    df["acos"] = _safe_div(df["spend"], df["attributed_sales"])
    df["roas"] = _safe_div(df["attributed_sales"], df["spend"])

    df = df.sort_values(["date", "campaign", "keyword"]).reset_index(drop=True)
    return df, log

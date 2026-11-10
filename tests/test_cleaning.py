import pandas as pd

from ecom_analysis.cleaning import _to_number, clean_ads, clean_sales


def test_number_parsing_handles_currency_and_negative_parentheses():
    parsed = _to_number(pd.Series(["$1,234.50", "(45.00)", "12.3%", ""]))
    assert parsed.iloc[0] == 1234.50
    assert parsed.iloc[1] == -45.00
    assert parsed.iloc[2] == 12.3
    assert pd.isna(parsed.iloc[3])


def test_clean_sales_deduplicates_normalizes_and_imputes():
    raw = pd.DataFrame(
        [
            {
                "date": "2026-10-01",
                "asin": " b0demo001 ",
                "sessions": "100",
                "units_ordered": "5",
                "ordered_product_sales": "$129.95",
            },
            {
                "date": "2026/10/02",
                "asin": "B0DEMO001",
                "sessions": "",
                "units_ordered": "6",
                "ordered_product_sales": "155.94",
            },
            {
                "date": "2026-10-01",
                "asin": "B0DEMO001",
                "sessions": "100",
                "units_ordered": "5",
                "ordered_product_sales": "129.95",
            },
            {
                "date": "2026-10-03",
                "asin": "B0DEMO002",
                "sessions": "80",
                "units_ordered": "-1",
                "ordered_product_sales": "-25.99",
            },
            {
                "date": "not-a-date",
                "asin": "B0DEMO002",
                "sessions": "70",
                "units_ordered": "2",
                "ordered_product_sales": "51.98",
            },
        ]
    )

    clean, log = clean_sales(raw)

    assert len(clean) == 2
    assert set(clean["asin"]) == {"B0DEMO001"}
    assert clean["sessions"].tolist() == [100, 100]
    assert clean.loc[clean["date"] == pd.Timestamp("2026-10-01"), "ordered_product_sales"].iloc[0] == 129.95
    issues = {entry["issue"] for entry in log}
    assert "同日期 + ASIN 重复" in issues
    assert "日期 / ASIN 无法识别" in issues
    assert "销量 / 销售额 / 会话数为负" in issues
    assert "会话数缺失" in issues


def test_clean_ads_parses_currency_and_drops_invalid_rows():
    base = {
        "date": "2026-10-01",
        "asin": "B0DEMO001",
        "campaign": "SP-Test",
        "impressions": "1000",
        "clicks": "100",
        "spend": "$123.45",
        "attributed_sales": "300.00",
        "attributed_orders": "10",
    }
    raw = pd.DataFrame(
        [
            base,
            dict(base),  # 完全重复
            dict(base, impressions="100", clicks="150"),  # 点击 > 曝光
            dict(base, asin="B0UNKNOWN"),  # 销售表不存在
            dict(base, spend=""),  # 花费缺失
        ]
    )

    clean, log = clean_ads(raw, valid_asins={"B0DEMO001"})

    assert len(clean) == 1
    assert clean.iloc[0]["spend"] == 123.45
    assert clean.iloc[0]["acos"] == 123.45 / 300.0
    issues = {entry["issue"] for entry in log}
    assert "同日期 + ASIN + 活动重复" in issues
    assert "点击数大于曝光数" in issues
    assert "销售表中不存在的 ASIN" in issues
    assert "关键指标缺失" in issues

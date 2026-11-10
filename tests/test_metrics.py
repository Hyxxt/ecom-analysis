import pandas as pd

from ecom_analysis.metrics import (
    asin_summary,
    detect_anomalies,
    keyword_summary,
    overall_metrics,
    safe_divide_series,
)


def _sales():
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-10-01"),
                "asin": "A",
                "sessions": 100,
                "units_ordered": 10,
                "ordered_product_sales": 200.0,
            },
            {
                "date": pd.Timestamp("2026-10-02"),
                "asin": "A",
                "sessions": 100,
                "units_ordered": 10,
                "ordered_product_sales": 200.0,
            },
            {
                "date": pd.Timestamp("2026-10-01"),
                "asin": "B",
                "sessions": 50,
                "units_ordered": 1,
                "ordered_product_sales": 20.0,
            },
        ]
    )


def _ads():
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-10-01"),
                "asin": "A",
                "campaign": "SP-A",
                "impressions": 1000,
                "clicks": 100,
                "spend": 30.0,
                "attributed_sales": 150.0,
                "attributed_orders": 8,
            },
            {
                "date": pd.Timestamp("2026-10-01"),
                "asin": "B",
                "campaign": "SP-B",
                "impressions": 500,
                "clicks": 20,
                "spend": 10.0,
                "attributed_sales": 0.0,
                "attributed_orders": 0,
            },
        ]
    )


def test_overall_metrics():
    result = overall_metrics(_sales(), _ads())

    assert result["total_sales"] == 420.0
    assert result["total_units"] == 21
    assert result["total_sessions"] == 250
    assert round(result["cvr"], 4) == 0.084
    assert result["ad_spend"] == 40.0
    assert result["ad_sales"] == 150.0
    assert round(result["acos"], 4) == round(40.0 / 150.0, 4)
    assert round(result["roas"], 4) == 3.75
    assert round(result["tacos"], 4) == round(40.0 / 420.0, 4)


def test_asin_summary_and_advice():
    result = asin_summary(_sales(), _ads()).set_index("asin")

    assert result.loc["A", "acos"] == 30.0 / 150.0
    assert result.loc["A", "roas"] == 5.0
    assert result.loc["A", "cvr"] == 0.1
    assert result.loc["A", "advice"] == "加预算"
    assert pd.isna(result.loc["B", "acos"])
    assert result.loc["B", "advice"] == "暂停 / 查归因"


def test_keyword_summary_flags_zero_order_spend():
    keywords = pd.DataFrame(
        [
            {
                "keyword": "waste word",
                "campaign": "SP-A",
                "match_type": "BROAD",
                "impressions": 1000,
                "clicks": 100,
                "spend": 80.0,
                "attributed_sales": 0.0,
                "attributed_orders": 0,
            },
            {
                "keyword": "good word",
                "campaign": "SP-A",
                "match_type": "PHRASE",
                "impressions": 1000,
                "clicks": 50,
                "spend": 30.0,
                "attributed_sales": 300.0,
                "attributed_orders": 10,
            },
        ]
    )

    result = keyword_summary(keywords).set_index("keyword")

    assert result.loc["waste word", "action"] == "加入否词"
    assert result.loc["good word", "action"] == "加预算"


def test_detect_anomalies_finds_spend_spike():
    sales = _sales()
    ads = _ads()
    ads = pd.concat(
        [
            ads,
            pd.DataFrame(
                [
                    {
                        "date": pd.Timestamp("2026-10-02"),
                        "asin": "A",
                        "campaign": "SP-A",
                        "impressions": 2000,
                        "clicks": 200,
                        "spend": 30.0,
                        "attributed_sales": 150.0,
                        "attributed_orders": 8,
                    },
                    {
                        "date": pd.Timestamp("2026-10-03"),
                        "asin": "A",
                        "campaign": "SP-A",
                        "impressions": 2000,
                        "clicks": 200,
                        "spend": 30.0,
                        "attributed_sales": 150.0,
                        "attributed_orders": 8,
                    },
                    {
                        "date": pd.Timestamp("2026-10-04"),
                        "asin": "A",
                        "campaign": "SP-A",
                        "impressions": 3000,
                        "clicks": 300,
                        "spend": 300.0,
                        "attributed_sales": 0.0,
                        "attributed_orders": 0,
                    },
                ]
            ),
        ],
        ignore_index=True,
    )
    result = detect_anomalies(
        sales,
        ads,
        asin_summary(sales, ads),
        keyword_summary(
            pd.DataFrame(
                columns=[
                    "keyword",
                    "campaign",
                    "match_type",
                    "impressions",
                    "clicks",
                    "spend",
                    "attributed_sales",
                    "attributed_orders",
                ]
            )
        ),
    )

    assert not result.empty
    assert "广告花费异常" in set(result["type"])


def test_safe_divide_series_accepts_scalar_denominator():
    result = safe_divide_series(pd.Series([10.0, 0.0]), 10.0)
    assert result.tolist() == [1.0, 0.0]
    assert safe_divide_series(pd.Series([10.0]), 0.0).isna().all()

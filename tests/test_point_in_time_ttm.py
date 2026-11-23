import pytest
from src.fundamentals.ttm_builder import PointInTimeTTMBuilder

def test_pit_ttm_extended_metrics():
    # 4 quarters of non-financial company
    q_stmts = [
        {"period_end_date": "2024-03-31", "filing_date": "2024-05-10", "revenue": 1000.0, "ebitda": 250.0, "net_profit": 150.0, "total_debt": 200.0, "total_equity": 800.0, "shares_outstanding": 100.0, "reporting_basis": "CONSOLIDATED"},
        {"period_end_date": "2023-12-31", "filing_date": "2024-01-20", "revenue": 950.0, "ebitda": 240.0, "net_profit": 140.0, "total_debt": 210.0, "total_equity": 750.0, "shares_outstanding": 100.0, "reporting_basis": "CONSOLIDATED"},
        {"period_end_date": "2023-09-30", "filing_date": "2023-10-25", "revenue": 900.0, "ebitda": 230.0, "net_profit": 130.0, "total_debt": 220.0, "total_equity": 700.0, "shares_outstanding": 100.0, "reporting_basis": "CONSOLIDATED"},
        {"period_end_date": "2023-06-30", "filing_date": "2023-07-28", "revenue": 850.0, "ebitda": 210.0, "net_profit": 120.0, "total_debt": 230.0, "total_equity": 650.0, "shares_outstanding": 100.0, "reporting_basis": "CONSOLIDATED"},
    ]

    # As of date after Q4 filing
    ratios = PointInTimeTTMBuilder.compute_ratios(
        symbol="TESTCO",
        as_of_date="2024-06-01",
        close_price=50.0,
        quarterly_statements=q_stmts,
        sector="Capital Goods"
    )

    # 1. P/E: TTM PAT = 150+140+130+120 = 540. Shares = 100 -> EPS = 5.4. Close = 50 -> PE = 50 / 5.4 = 9.26
    assert ratios["ttm_pe"].status == "VALID"
    assert ratios["ttm_pe"].value == pytest.approx(9.26, rel=1e-2)

    # 2. P/B: Latest equity = 800. Shares = 100 -> BVPS = 8.0. Close = 50 -> PB = 50 / 8 = 6.25
    assert ratios["pb_ratio"].status == "VALID"
    assert ratios["pb_ratio"].value == pytest.approx(6.25, rel=1e-2)

    # 3. Debt to Equity: Latest debt = 200, Equity = 800 -> 0.25
    assert ratios["debt_to_equity"].status == "VALID"
    assert ratios["debt_to_equity"].value == pytest.approx(0.25, rel=1e-2)

    # 4. EV/EBITDA: Market cap = 50 * 100 = 5000. Debt = 200. EV = 5200. TTM EBITDA = 250+240+230+210 = 930. EV/EBITDA = 5200 / 930 = 5.59
    assert ratios["ev_ebitda"].status == "VALID"
    assert ratios["ev_ebitda"].value == pytest.approx(5.59, rel=1e-2)

    # 5. ROCE: Capital employed = 800 + 200 = 1000. EBIT ~ 930 * 0.85 = 790.5. ROCE = (790.5 / 1000) * 100 = 79.05%
    assert ratios["roce_pct"].status == "VALID"
    assert ratios["roce_pct"].value == pytest.approx(79.05, rel=1e-2)


def test_pit_financial_sector_not_applicable():
    # Financial company (Bank)
    ratios = PointInTimeTTMBuilder.compute_ratios(
        symbol="TESTBANK",
        as_of_date="2024-06-01",
        close_price=100.0,
        quarterly_statements=[],
        sector="Banking"
    )
    assert ratios["debt_to_equity"].status == "NOT_APPLICABLE"
    assert ratios["ev_ebitda"].status == "NOT_APPLICABLE"
    assert ratios["roce_pct"].status == "NOT_APPLICABLE"

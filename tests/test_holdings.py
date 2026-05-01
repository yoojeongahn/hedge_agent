import pytest
import textwrap
from pathlib import Path
from core.holdings import load_holdings, HoldingPosition

SAMPLE_YAML = textwrap.dedent("""
    positions:
      - code: "005930"
        name: "삼성전자"
        market: KR
        quantity: 100
        avg_price: 68000
        broker: "KB증권"
      - code: "AAPL"
        name: "Apple"
        market: US
        quantity: 10
        avg_price: 180.0
        broker: "토스증권"
    cash:
      KRW: 5000000
      USD: 1000
""")

def test_load_valid_yaml(tmp_path):
    f = tmp_path / "holdings.yaml"
    f.write_text(SAMPLE_YAML, encoding="utf-8")
    h = load_holdings(f)
    assert len(h.positions) == 2
    assert h.cash_krw == 5000000
    assert h.cash_usd == 1000

def test_filter_by_market(tmp_path):
    f = tmp_path / "holdings.yaml"
    f.write_text(SAMPLE_YAML, encoding="utf-8")
    h = load_holdings(f)
    kr = [p for p in h.positions if p.market == "KR"]
    us = [p for p in h.positions if p.market == "US"]
    assert len(kr) == 1 and kr[0].code == "005930"
    assert len(us) == 1 and us[0].code == "AAPL"

def test_missing_required_field_raises(tmp_path):
    bad = textwrap.dedent("""
        positions:
          - code: "005930"
            name: "삼성전자"
            market: KR
            quantity: 100
            # avg_price 누락
        cash:
          KRW: 0
          USD: 0
    """)
    f = tmp_path / "holdings.yaml"
    f.write_text(bad, encoding="utf-8")
    with pytest.raises(ValueError, match="avg_price"):
        load_holdings(f)

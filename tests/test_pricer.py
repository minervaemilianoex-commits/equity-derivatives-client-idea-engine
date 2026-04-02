from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.engine.pricer import bs_option_price, option_intrinsic_value


def test_option_intrinsic_value_call():
    assert option_intrinsic_value("call", 110, 100) == 10.0


def test_option_intrinsic_value_put():
    assert option_intrinsic_value("put", 90, 100) == 10.0


def test_bs_option_price_positive():
    price = bs_option_price(
        option_type="call",
        spot=100,
        strike=100,
        maturity_years=30 / 365,
        risk_free_rate=0.02,
        dividend_yield=0.00,
        sigma=0.20,
    )
    assert price > 0
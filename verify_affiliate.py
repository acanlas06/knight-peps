import math
import os
import tempfile

# Keep verification data out of the repo while importing server.py.
os.environ.setdefault("KL_DATA_DIR", tempfile.mkdtemp(prefix="kl-affiliate-test-"))

import server  # noqa: E402


def sample_payload(code="AC"):
    return {
        "email": "buyer@example.com",
        "name": "Buyer Example",
        "phone": "555-0100",
        "shippingMethod": "Shipping by arrangement",
        "paymentPreference": "Zelle after confirmation",
        "affiliateCode": code,
        "shippingAddress": {
            "name": "Buyer Example",
            "street": "123 Test Lane",
            "city": "Austin",
            "state": "TX",
            "zip": "78701",
            "country": "US",
        },
        "items": [
            {"slug": "retatrutide", "name": "Retatrutide", "size": "10mg", "qty": 2, "unitPrice": 50},
        ],
    }


def assert_close(actual, expected):
    assert math.isclose(actual, expected, rel_tol=0, abs_tol=0.01), (actual, expected)


def test_ac_affiliate_code_applies_15_percent_discount():
    order, error = server.sanitise_order(sample_payload(" ac "))
    assert error is None
    assert order["affiliate"]["code"] == "AC"
    assert order["affiliate"]["percent"] == 15
    assert_close(order["subtotal"], 100)
    assert_close(order["discountAmount"], 15)
    assert_close(order["total"], 85)


def test_tgomez_affiliate_code_applies_15_percent_discount():
    order, error = server.sanitise_order(sample_payload(" tgomez "))
    assert error is None
    assert order["affiliate"]["code"] == "TGOMEZ"
    assert order["affiliate"]["percent"] == 15
    assert_close(order["subtotal"], 100)
    assert_close(order["discountAmount"], 15)
    assert_close(order["total"], 85)


def test_admin_stats_tracks_referral_units_and_sales():
    order, error = server.sanitise_order(sample_payload("TGOMEZ"))
    assert error is None
    order["orderNumber"] = "KL-TEST"
    rows = {"KL-TEST": dict(order, token_hash="not-public")}
    original_load_orders = server.load_orders
    try:
        server.load_orders = lambda: rows
        stats = server.admin_stats()
    finally:
        server.load_orders = original_load_orders
    referral = {r["code"]: r for r in stats["referrals"]}["TGOMEZ"]
    assert referral["orderCount"] == 1
    assert referral["unitsOrdered"] == 2
    assert_close(referral["subtotal"], 100)
    assert_close(referral["discountAmount"], 15)
    assert_close(referral["total"], 85)
    assert_close(referral["unpaidTotal"], 85)


def test_unknown_affiliate_code_is_rejected():
    order, error = server.sanitise_order(sample_payload("NOPE"))
    assert order is None
    assert error == "invalid_affiliate_code"


def test_blank_affiliate_code_leaves_total_unchanged():
    order, error = server.sanitise_order(sample_payload(""))
    assert error is None
    assert order.get("affiliate") is None
    assert_close(order["subtotal"], 100)
    assert_close(order["discountAmount"], 0)
    assert_close(order["total"], 100)


if __name__ == "__main__":
    tests = [
        test_ac_affiliate_code_applies_15_percent_discount,
        test_tgomez_affiliate_code_applies_15_percent_discount,
        test_admin_stats_tracks_referral_units_and_sales,
        test_unknown_affiliate_code_is_rejected,
        test_blank_affiliate_code_leaves_total_unchanged,
    ]
    for test in tests:
        test()
    print("affiliate verification passed")

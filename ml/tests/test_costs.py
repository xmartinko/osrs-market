import pytest

from osrs_ml.costs import TaxPolicy, execution_price, sale_proceeds, tax_per_item


@pytest.mark.parametrize(
    "price,tax",
    [
        (0, 0),
        (49, 0),
        (50, 1),
        (51, 1),
        (99, 1),
        (100, 2),
        (149, 2),
        (249_999_999, 4_999_999),
        (250_000_000, 5_000_000),
        (3_200_000_000, 5_000_000),
    ],
)
def test_verified_tax_boundaries(price, tax):
    assert tax_per_item(price) == tax


def test_round_per_item_before_quantity_and_cap_per_item():
    assert sale_proceeds(99, 10) == 980
    assert sale_proceeds(3_200_000_000, 3) == 9_585_000_000


def test_wiki_boundary_and_exemptions_configurable():
    assert tax_per_item(50, TaxPolicy(exempt_through_gp=49)) == 1
    assert tax_per_item(50, TaxPolicy(exempt_through_gp=50)) == 0
    assert tax_per_item(10000, TaxPolicy(exempt_item_ids=(42,)), item_id=42) == 0


def test_integer_slippage():
    assert execution_price(101, 1, buy=True) == 102
    assert execution_price(101, 1, buy=False) == 100
    assert execution_price(3_200_000_000, 10, buy=True) == 3_203_200_000


@pytest.mark.parametrize("price", [-1, 1.5])
def test_invalid_price(price):
    with pytest.raises(ValueError):
        tax_per_item(price)


@pytest.mark.parametrize("buy", [True, False])
def test_bps_on_cheap_items_are_not_a_per_unit_tick(buy):
    from osrs_ml.costs import integer_lots, price_target

    costs = []
    for bps in (5, 10, 30):
        target = price_target(3, bps, buy=buy)
        lots = integer_lots(target, 10_000, buy=buy)
        assert sum(q for _, q in lots) == 10_000
        assert all(type(p) is int and p >= 1 for p, _ in lots)
        gross = sum(p * q for p, q in lots)
        costs.append((gross - 30_000) * (1 if buy else -1))
    assert costs == [15, 30, 90]
    # A labelled tick stress has the large cost the old "5 bps" actually charged.
    lots = integer_lots(price_target(3, 0, buy=buy, ticks=1), 10_000, buy=buy)
    assert abs(sum(p * q for p, q in lots) - 30_000) == 10_000


@pytest.mark.parametrize("reference", [0, -1, 1.5, float("inf"), float("nan"), True])
def test_corrected_prices_reject_invalid_references(reference):
    from osrs_ml.costs import UntradeablePrice, price_target

    with pytest.raises(UntradeablePrice, match="invalid_reference_price"):
        price_target(reference, 5, buy=True)


@pytest.mark.parametrize("bps,ticks", [(5, 0), (0, 1), (10_000, 0)])
def test_price_below_one_is_untradeable_not_clamped(bps, ticks):
    from osrs_ml.costs import UntradeablePrice, price_target

    with pytest.raises(UntradeablePrice, match="untradeable_at_granularity"):
        price_target(1, bps, buy=False, ticks=ticks)


def test_lot_rounding_is_bounded_per_opportunity_and_large_prices_are_exact():
    from osrs_ml.costs import integer_lots, price_target

    for price in (1, 3, 49, 50, 101, 3_200_000_000):
        for quantity in (1, 3, 137, 10_001):
            for buy in (True, False):
                if price == 1 and not buy:
                    continue
                target = price_target(price, 5, buy=buy)
                lots = integer_lots(target, quantity, buy=buy)
                gross = sum(p * q for p, q in lots)
                cost = (gross - price * quantity) * (1 if buy else -1)
                residual = price * quantity * 5 - cost * 10_000
                assert 0 <= residual < 10_000
                assert sum(q for _, q in lots) == quantity
                assert all(p >= 1 and q > 0 for p, q in lots)

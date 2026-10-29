import pytest
from osrs_ml.costs import TaxPolicy, execution_price, sale_proceeds, tax_per_item


@pytest.mark.parametrize(
    "price,tax",
    [
        (0, 0),
        (49, 0),
        (50, 0),
        (51, 1),
        (99, 1),
        (100, 2),
        (149, 2),
        (249_999_999, 4_999_999),
        (250_000_000, 5_000_000),
        (3_200_000_000, 5_000_000),
    ],
)
def test_requested_tax_boundaries(price, tax):
    assert tax_per_item(price) == tax


def test_round_per_item_before_quantity_and_cap_per_item():
    assert sale_proceeds(99, 10) == 980
    assert sale_proceeds(3_200_000_000, 3) == 9_585_000_000


def test_wiki_boundary_and_exemptions_configurable():
    assert tax_per_item(50, TaxPolicy(exempt_through_gp=49)) == 1
    assert tax_per_item(10000, TaxPolicy(exempt_item_ids=(42,)), item_id=42) == 0


def test_integer_slippage():
    assert execution_price(101, 1, buy=True) == 102
    assert execution_price(101, 1, buy=False) == 100
    assert execution_price(3_200_000_000, 10, buy=True) == 3_203_200_000


@pytest.mark.parametrize("price", [-1, 1.5])
def test_invalid_price(price):
    with pytest.raises(ValueError):
        tax_per_item(price)

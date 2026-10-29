"""Integer GP arithmetic. Tax is floored and capped PER ITEM, then multiplied."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TaxPolicy:
    rate_bps: int = 200
    exempt_through_gp: int = 50  # Requested boundary; use 49 for the Wiki boundary.
    cap_gp: int = 5_000_000
    exempt_item_ids: tuple[int, ...] = ()

    def __post_init__(self):
        if not 0 <= self.rate_bps <= 10_000 or min(self.exempt_through_gp, self.cap_gp) < 0:
            raise ValueError("Invalid tax policy")


DEFAULT_TAX = TaxPolicy()


def tax_per_item(sale_gp: int, policy: TaxPolicy = DEFAULT_TAX, item_id: int = 0) -> int:
    if not isinstance(sale_gp, int) or sale_gp < 0:
        raise ValueError("Price must be a nonnegative integer")
    if sale_gp <= policy.exempt_through_gp or item_id in policy.exempt_item_ids:
        return 0
    return min(sale_gp * policy.rate_bps // 10_000, policy.cap_gp)


def sale_proceeds(
    sale_gp: int, quantity: int, policy: TaxPolicy = DEFAULT_TAX, item_id: int = 0
) -> int:
    if not isinstance(quantity, int) or quantity < 0:
        raise ValueError("Quantity must be a nonnegative integer")
    return (sale_gp - tax_per_item(sale_gp, policy, item_id)) * quantity


def execution_price(price_gp: int, adverse_bps: int, *, buy: bool) -> int:
    if price_gp < 0 or not 0 <= adverse_bps <= 10_000:
        raise ValueError("Invalid execution cost")
    # Round against the trader on both sides, using integers even above 2**31.
    return (
        (price_gp * (10_000 + adverse_bps) + 9999) // 10_000
        if buy
        else price_gp * (10_000 - adverse_bps) // 10_000
    )


def net_return(
    buy_gp: int, sell_gp: int, policy: TaxPolicy = DEFAULT_TAX, item_id: int = 0
) -> float:
    return sale_proceeds(sell_gp, 1, policy, item_id) / buy_gp - 1

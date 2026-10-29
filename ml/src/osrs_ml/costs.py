"""Integer GP arithmetic. Tax is floored and capped PER ITEM, then multiplied."""

from dataclasses import dataclass
from numbers import Integral


@dataclass(frozen=True)
class TaxPolicy:
    rate_bps: int = 200
    exempt_through_gp: int = 49  # Jagex 2025-05-29: UNDER 50; exactly 50 pays 1 gp.
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
    """Legacy adverse per-unit rounding. ONLY for reproducing superseded v1 runs."""
    if price_gp < 0 or not 0 <= adverse_bps <= 10_000:
        raise ValueError("Invalid execution cost")
    # Round against the trader on both sides, using integers even above 2**31.
    return (
        (price_gp * (10_000 + adverse_bps) + 9999) // 10_000
        if buy
        else price_gp * (10_000 - adverse_bps) // 10_000
    )


class UntradeablePrice(ValueError):
    """An explicit failed price opportunity, never a zero-price fill."""


def price_target(price_gp: int, adverse_bps: int, *, buy: bool, ticks: int = 0) -> int:
    """Exact target unit price in ten-thousandths of a GP (no rounding)."""
    if isinstance(price_gp, bool) or not isinstance(price_gp, Integral) or price_gp < 1:
        raise UntradeablePrice("invalid_reference_price")
    if type(adverse_bps) is not int or not 0 <= adverse_bps <= 10_000:
        raise ValueError("Invalid bps cost")
    if type(ticks) is not int or ticks < 0:
        raise ValueError("Invalid tick stress")
    adjustment = int(price_gp) * adverse_bps + ticks * 10_000
    target = int(price_gp) * 10_000 + (adjustment if buy else -adjustment)
    if target < 10_000:
        raise UntradeablePrice("untradeable_at_granularity")
    return target


def integer_lots(
    target: int, quantity: int, *, buy: bool, denominator: int = 10_000
) -> list[tuple[int, int]]:
    """Allocate a target mean to legal GP lots, rounding <1 GP toward zero cost.

    This deterministic notional-cost distribution is hypothetical, not observed
    trade prints or a calibrated fill probability. No per-unit adverse rounding.
    """
    if denominator <= 0 or target < denominator:
        raise UntradeablePrice("untradeable_at_granularity")
    if type(quantity) is not int or quantity < 0:
        raise ValueError("Invalid lot quantity")
    low, remainder = divmod(target, denominator)
    # Buy gross rounds down, sale gross rounds up: residual cost is explicit.
    high_units = (quantity * remainder + (0 if buy else denominator - 1)) // denominator
    return [(p, q) for p, q in ((low, quantity - high_units), (low + 1, high_units)) if q]


def net_return(
    buy_gp: int, sell_gp: int, policy: TaxPolicy = DEFAULT_TAX, item_id: int = 0
) -> float:
    return sale_proceeds(sell_gp, 1, policy, item_id) / buy_gp - 1

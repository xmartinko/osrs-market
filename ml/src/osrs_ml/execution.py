from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionAssumptions:
    name: str
    participation_bps: int
    slippage_bps: int
    latency_seconds: int
    max_freshness_seconds: int
    buy_timeout_seconds: int = 1800
    terminal_haircut_bps: int = 100
    unknown_interval_seconds: int = 300
    allow_unknown_metadata: bool = False
    freshness_basis: str = "upper_bound"
    passive_prices: bool = False
    queue_fill_bps: int = 10_000
    price_model: str = "integer_lots_v2"
    adverse_ticks: int = 0

    def __post_init__(self):
        if self.price_model not in ("integer_lots_v2", "legacy_v1"):
            raise ValueError("Unknown execution price model")
        if type(self.adverse_ticks) is not int or self.adverse_ticks < 0:
            raise ValueError("Tick stress must be a nonnegative integer")
        if self.price_model == "legacy_v1" and self.adverse_ticks:
            raise ValueError("Legacy replay has no separate tick stress")
        if self.freshness_basis not in ("lower_bound", "upper_bound"):
            raise ValueError("Freshness basis must be lower_bound or upper_bound")
        if not 0 < self.participation_bps <= 10_000:
            raise ValueError("Invalid participation")
        if not 0 < self.queue_fill_bps <= 10_000:
            raise ValueError("Invalid queue fill assumption")
        if not 0 <= self.slippage_bps <= 10_000 or not 0 <= self.terminal_haircut_bps <= 10_000:
            raise ValueError("Invalid price adjustment")
        if min(self.latency_seconds, self.max_freshness_seconds) < 0:
            raise ValueError("Invalid time constraint")
        if min(self.buy_timeout_seconds, self.unknown_interval_seconds) <= 0:
            raise ValueError("Intervals must be positive")


PRESETS = {
    "optimistic": ExecutionAssumptions(
        "optimistic", 1000, 0, 0, 1800, terminal_haircut_bps=0, freshness_basis="lower_bound"
    ),
    "moderate": ExecutionAssumptions("moderate", 200, 10, 300, 900),
    "conservative": ExecutionAssumptions(
        "conservative", 50, 30, 600, 300, terminal_haircut_bps=300
    ),
}


@dataclass(frozen=True)
class PortfolioPolicy:
    initial_cash_gp: int = 10_000_000
    offer_slots: int = 8
    allocation_bps: int = 1000
    holding_seconds: int = 3600
    minimum_score: float = 0.0

    def __post_init__(self):
        if min(self.initial_cash_gp, self.offer_slots, self.holding_seconds) <= 0:
            raise ValueError("Portfolio amounts must be positive")
        if not 0 < self.allocation_bps <= 10_000:
            raise ValueError("Invalid allocation")


DEFAULT_PORTFOLIO = PortfolioPolicy()

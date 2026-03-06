"""Abstract base class for option selling strategies."""
from abc import ABC, abstractmethod

from shared.models import StrategyScreen, StrikeCandidate


class BaseStrategy(ABC):
    name: str = ""           # "Covered Call"
    slug: str = ""           # "covered_call"
    required_position: str | None = None  # "long_stock" or None

    @abstractmethod
    async def screen(
        self,
        symbol: str,
        price: float,
        calls: list[dict],
        puts: list[dict],
        summary: dict,
    ) -> StrategyScreen:
        """Screen strikes and return ranked candidates."""
        ...

    def passes_filter(self, summary: dict) -> bool:
        """Optional pre-filter. Override to skip screening when conditions are poor."""
        return True

    def _make_candidate(
        self,
        strike_data: dict,
        option_type: str,
        capital_required: float,
    ) -> StrikeCandidate | None:
        """Helper to build a StrikeCandidate from raw strike data."""
        bid = strike_data.get("bid", 0)
        ask = strike_data.get("ask", 0)
        mid = (bid + ask) / 2 if (bid + ask) > 0 else 0
        delta = abs(strike_data.get("delta", 0))
        dte = strike_data.get("dte", 0)

        if mid <= 0 or dte <= 0 or capital_required <= 0:
            return None

        spread_quality = (ask - bid) / mid if mid > 0 else 1.0
        prob_otm = 1 - delta
        annualized = (mid * 100 / capital_required) * (365 / dte)

        return StrikeCandidate(
            strike=strike_data["strike"],
            expiration=strike_data.get("expiration", ""),
            option_type=option_type,
            delta=strike_data.get("delta", 0),
            mid_price=round(mid, 2),
            bid=bid,
            ask=ask,
            prob_otm=round(prob_otm, 4),
            spread_quality=round(spread_quality, 4),
            annualized_return=round(annualized, 4),
            capital_required=round(capital_required, 2),
            dte=dte,
            volume=strike_data.get("volume", 0),
            open_interest=strike_data.get("open_interest", 0),
        )

"""Covered Call strategy screener."""
from strategies.base import BaseStrategy
from shared.models import StrategyScreen


class CoveredCallStrategy(BaseStrategy):
    name = "Covered Call"
    slug = "covered_call"
    required_position = "long_stock"

    def passes_filter(self, summary: dict) -> bool:
        # Skip if IV is very low — not worth selling
        iv_pct = summary.get("iv_percentile")
        if iv_pct is not None and iv_pct < 0.20:
            return False
        return True

    async def screen(
        self,
        symbol: str,
        price: float,
        calls: list[dict],
        puts: list[dict],
        summary: dict,
    ) -> StrategyScreen:
        candidates = []
        earnings_nearby = summary.get("earnings", {}).get("earnings_nearby", False)

        for c in calls:
            delta = c.get("delta", 0)
            # OTM calls have positive delta; we want delta 0.20-0.35
            if not (0.15 <= abs(delta) <= 0.40):
                continue

            bid = c.get("bid", 0)
            ask = c.get("ask", 0)
            mid = (bid + ask) / 2
            if mid <= 0:
                continue

            # Capital required = 100 shares at current price
            capital = price * 100

            candidate = self._make_candidate(c, "CALL", capital)
            if candidate is None:
                continue

            # Filter: spread quality
            if candidate.spread_quality > 0.20:
                continue

            # Filter: minimum annualized return
            if candidate.annualized_return < 0.08:
                continue

            candidates.append(candidate)

        # Sort by annualized return descending
        candidates.sort(key=lambda x: x.annualized_return, reverse=True)

        return StrategyScreen(
            strategy_name=self.name,
            strategy_slug=self.slug,
            candidates=candidates[:5],  # Top 5
        )

"""Cash-Secured Put strategy screener."""
from strategies.base import BaseStrategy
from shared.models import StrategyScreen


class CashSecuredPutStrategy(BaseStrategy):
    name = "Cash-Secured Put"
    slug = "cash_secured_put"
    required_position = None  # Only needs cash

    def passes_filter(self, summary: dict) -> bool:
        # Skip if IV is very low
        iv_pct = summary.get("iv_percentile")
        if iv_pct is not None and iv_pct < 0.25:
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

        for p in puts:
            delta = p.get("delta", 0)
            # OTM puts have negative delta; we want |delta| 0.15-0.35
            if not (0.15 <= abs(delta) <= 0.40):
                continue

            bid = p.get("bid", 0)
            ask = p.get("ask", 0)
            mid = (bid + ask) / 2
            if mid <= 0:
                continue

            # Capital required = strike × 100 (cash to secure the put)
            strike = p.get("strike", 0)
            if strike <= 0:
                continue
            capital = strike * 100

            candidate = self._make_candidate(p, "PUT", capital)
            if candidate is None:
                continue

            # Filter: spread quality
            if candidate.spread_quality > 0.20:
                continue

            # Filter: minimum annualized return
            if candidate.annualized_return < 0.06:
                continue

            candidates.append(candidate)

        # Sort by annualized return descending
        candidates.sort(key=lambda x: x.annualized_return, reverse=True)

        return StrategyScreen(
            strategy_name=self.name,
            strategy_slug=self.slug,
            candidates=candidates[:5],  # Top 5
        )

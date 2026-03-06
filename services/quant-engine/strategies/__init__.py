"""Strategy registry. Add new strategies here."""
from strategies.base import BaseStrategy
from strategies.covered_call import CoveredCallStrategy
from strategies.cash_secured_put import CashSecuredPutStrategy

# All registered strategies — scheduler iterates this list
STRATEGIES: list[BaseStrategy] = [
    CoveredCallStrategy(),
    CashSecuredPutStrategy(),
]

__all__ = ["STRATEGIES", "BaseStrategy"]

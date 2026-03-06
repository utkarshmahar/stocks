from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class OptionLeg(BaseModel):
    action: str  # SELL or BUY
    strike: float
    type: str  # PUT or CALL
    expiry: str


class Recommendation(BaseModel):
    symbol: str
    strategy: str
    legs: list[OptionLeg]
    max_profit: float
    max_loss: float
    probability_estimate: float
    capital_required: float
    reasoning_summary: str
    risk_flags: list[str] = []
    risk_approved: Optional[bool] = None
    risk_notes: Optional[str] = None
    status: str = "pending"
    generated_at: datetime = datetime.utcnow()


class QuantSummary(BaseModel):
    symbol: str
    current_price: float
    iv_percentile: Optional[float] = None
    iv_rank: Optional[float] = None
    put_call_skew: Optional[float] = None
    term_structure: Optional[str] = None  # contango / backwardation
    unusual_activity: bool = False
    volume_oi_ratio: Optional[float] = None
    timestamp: datetime = datetime.utcnow()


class PortfolioPosition(BaseModel):
    symbol: str
    quantity: float
    avg_price: float
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    cost_basis: Optional[float] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    total_premium_collected: float = 0.0
    adjusted_cost_basis: Optional[float] = None
    effective_cost_per_share: Optional[float] = None
    asset_type: str = "EQUITY"


class StockQuote(BaseModel):
    symbol: str
    price: float
    bid: float = 0.0
    ask: float = 0.0
    change: float = 0.0
    percent_change: float = 0.0
    volume: int = 0
    high: float = 0.0
    low: float = 0.0
    open: float = 0.0
    timestamp: Optional[datetime] = None


class OptionContract(BaseModel):
    symbol: str
    option_type: str  # CALL or PUT
    strike: float
    expiration: str
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    mark: float = 0.0
    volume: int = 0
    open_interest: int = 0
    implied_volatility: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0
    in_the_money: bool = False
    days_to_expiration: int = 0


class OptionsChain(BaseModel):
    symbol: str
    underlying: StockQuote
    calls: list[OptionContract] = []
    puts: list[OptionContract] = []
    timestamp: Optional[datetime] = None


class RiskDecision(BaseModel):
    approved: bool
    risk_notes: str
    flags: list[str] = []


class FundamentalReport(BaseModel):
    symbol: str
    report_type: str
    intrinsic_value: Optional[float] = None
    current_price: Optional[float] = None
    upside_percent: Optional[float] = None
    ai_narrative: Optional[str] = None
    report_data: dict = {}
    created_at: datetime = datetime.utcnow()


# ---- Quant Engine V2 Models ----

class EarningsInfo(BaseModel):
    earnings_nearby: bool = False
    earnings_date: Optional[str] = None
    days_until_earnings: Optional[int] = None


class StrikeCandidate(BaseModel):
    strike: float
    expiration: str
    option_type: str  # CALL or PUT
    delta: float
    mid_price: float
    bid: float = 0.0
    ask: float = 0.0
    prob_otm: float  # 1 - |delta|
    spread_quality: float  # (ask - bid) / mid, lower is better
    annualized_return: float  # (premium / capital) * (365 / dte)
    capital_required: float
    dte: int
    volume: int = 0
    open_interest: int = 0


class StrategyScreen(BaseModel):
    strategy_name: str  # "Covered Call", "Cash-Secured Put"
    strategy_slug: str  # "covered_call", "cash_secured_put"
    candidates: list[StrikeCandidate] = []


class QuantSummaryV2(BaseModel):
    symbol: str
    current_price: float
    # IV metrics
    iv_percentile: Optional[float] = None
    iv_rank: Optional[float] = None
    current_iv: Optional[float] = None
    iv_trend: Optional[float] = None  # slope: positive = rising
    # Flow metrics
    put_call_skew: Optional[float] = None
    volume_oi_ratio: Optional[float] = None
    unusual_activity: bool = False
    total_call_volume: int = 0
    total_put_volume: int = 0
    total_call_oi: int = 0
    total_put_oi: int = 0
    # Market regime
    vix_level: Optional[float] = None
    expected_weekly_move: Optional[float] = None
    expected_move_pct: Optional[float] = None
    # Earnings
    earnings: EarningsInfo = EarningsInfo()
    # Strategy screens
    strategy_screens: list[StrategyScreen] = []
    # Meta
    computed_at: datetime = datetime.utcnow()
    source: str = "scheduler"  # "scheduler" or "on_demand"

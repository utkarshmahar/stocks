# Cash-Secured Put Strategy

## Overview
Sell a put option while holding enough cash to buy 100 shares if assigned. Generates income; if assigned, you acquire stock at a discount.

## Setup
- **Position required**: Cash equal to strike × 100
- **Action**: SELL 1 OTM put

## Ideal Conditions
- IV percentile > 40 (rich premium)
- Bullish or neutral outlook on underlying
- Willing to own the stock at the strike price
- No earnings within DTE window (unless intentional)

## Strike Selection Criteria
- Delta: 0.20 to 0.35 (65-80% probability OTM)
- DTE: 14-45 days
- Bid-ask spread < 10% of mid price
- Annualized return > 10%
- Strike at or below support levels preferred

## Risk Flags
- Earnings within DTE → risk of gap below strike
- IV rank < 20 → low premium environment
- Delta > 0.40 → high assignment probability

## Max Profit
Premium received

## Max Loss
Strike price × 100 minus premium received (stock goes to zero)

## Quant Filters Used
- `iv_percentile`, `iv_rank` — premium richness
- `earnings_nearby` — gap risk
- `spread_quality` — liquidity
- `delta` — probability of expiring OTM
- `put_call_skew` — elevated put IV = higher CSP premium

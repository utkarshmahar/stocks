# Covered Call Strategy

## Overview
Sell a call option against 100 shares of stock you already own. Generates income from premium while capping upside.

## Setup
- **Position required**: Long 100 shares of underlying
- **Action**: SELL 1 OTM call

## Ideal Conditions
- IV percentile > 30 (higher premium)
- Neutral to slightly bullish outlook
- No earnings within DTE window (unless intentional)
- Stock in consolidation or mild uptrend

## Strike Selection Criteria
- Delta: -0.20 to -0.35 (70-80% probability OTM)
- DTE: 14-45 days (optimal theta decay)
- Bid-ask spread < 10% of mid price
- Annualized return > 12%

## Risk Flags
- Earnings within DTE → risk of gap above strike
- IV rank < 20 → low premium, poor risk/reward
- Delta > -0.40 → too close to ATM, high assignment risk

## Max Profit
Premium received (capped)

## Max Loss
Stock drops to zero minus premium received (same as holding stock, slightly offset)

## Quant Filters Used
- `iv_percentile`, `iv_rank` — premium quality
- `earnings_nearby` — avoid surprise gaps
- `spread_quality` — execution cost
- `delta` — probability of staying OTM

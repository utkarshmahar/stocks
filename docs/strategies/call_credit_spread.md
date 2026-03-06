# Call Credit Spread Strategy

## Overview
Sell a lower-strike call and buy a higher-strike call at the same expiration. Defined-risk bearish strategy.

## Setup
- **Action**: SELL 1 OTM call (short leg), BUY 1 further OTM call (long leg)
- **Same expiration** for both legs

## Ideal Conditions
- IV percentile > 40
- Bearish or neutral outlook
- Credit received > 1/3 of spread width

## Strike Selection Criteria
- Short leg delta: -0.20 to -0.30
- Spread width: $2-$10
- DTE: 21-45 days
- Min credit: 30% of width

## Risk Flags
- Earnings within DTE (gap up risk)
- Strong uptrend momentum
- Low liquidity on either leg

## Max Profit
Net credit received

## Max Loss
Spread width - credit received

## Future Implementation
This strategy will be added after put credit spreads are validated.

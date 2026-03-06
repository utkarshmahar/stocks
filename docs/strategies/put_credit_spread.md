# Put Credit Spread Strategy

## Overview
Sell a higher-strike put and buy a lower-strike put at the same expiration. Defined-risk bullish strategy that profits from time decay and the underlying staying above the short strike.

## Setup
- **Action**: SELL 1 OTM put (short leg), BUY 1 further OTM put (long leg)
- **Same expiration** for both legs

## Ideal Conditions
- IV percentile > 40
- Bullish or neutral outlook
- Credit received > 1/3 of spread width (favorable risk/reward)

## Strike Selection Criteria
- Short leg delta: 0.20-0.30
- Spread width: $2-$10 depending on underlying price
- DTE: 21-45 days
- Min credit: 30% of width

## Risk Flags
- Earnings between legs or within DTE
- Very narrow spread (high commission impact)
- Low volume/OI on either leg

## Max Profit
Net credit received

## Max Loss
Spread width - credit received

## Future Implementation
This strategy will be added after the covered call and cash-secured put strategies are validated.

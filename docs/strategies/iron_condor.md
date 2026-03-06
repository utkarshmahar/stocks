# Iron Condor Strategy

## Overview
Combination of a put credit spread and a call credit spread on the same underlying and expiration. Profits from the underlying staying within a range.

## Setup
- **Action**: SELL 1 OTM put + BUY 1 further OTM put + SELL 1 OTM call + BUY 1 further OTM call
- **Same expiration** for all four legs

## Ideal Conditions
- IV percentile > 50 (high premium environment)
- Neutral/range-bound outlook
- No earnings within DTE
- Low expected move relative to wing width

## Strike Selection Criteria
- Short put delta: 0.15-0.20
- Short call delta: -0.15 to -0.20
- Equal wing widths preferred
- DTE: 30-45 days
- Combined credit > 1/3 of one side's width

## Risk Flags
- Earnings within DTE
- VIX trending sharply higher (regime shift)
- Strong directional momentum
- Wide bid-ask on any leg

## Max Profit
Combined net credit from both spreads

## Max Loss
Width of wider spread minus total credit received

## Future Implementation
This strategy will be added after individual credit spreads are validated.

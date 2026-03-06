# Quant Metrics Reference

## IV Percentile
**What**: Percentage of days in the lookback period where IV was lower than current IV.
**Calculation**: `count(historical_iv < current_iv) / total_days`
**Lookback**: 30 days (hourly aggregation)
**Use**: IV percentile > 50 = premium is historically rich. Good for selling.

## IV Rank
**What**: Where current IV falls relative to the 30-day min/max range.
**Calculation**: `(current_iv - min_iv) / (max_iv - min_iv)`
**Range**: 0.0 to 1.0
**Use**: IV rank > 0.5 = IV closer to its recent high. Complements percentile.

## IV Trend
**What**: Direction of IV over the last 5 days.
**Calculation**: Linear regression slope of daily average IV (numpy polyfit degree 1).
**Values**: Positive = IV rising, Negative = IV falling
**Use**: Rising IV → wait before selling. Falling IV → good entry for premium sellers.

## Put/Call Skew
**What**: Ratio of average put IV to average call IV.
**Calculation**: `mean(put_iv) / mean(call_iv)`
**Use**: Skew > 1.0 = puts are more expensive (demand for downside protection). Good for selling puts.

## Volume/OI Ratio
**What**: Today's total option volume relative to open interest.
**Calculation**: `total_volume / total_open_interest`
**Use**: Ratio > 1.5 = unusual activity flag. May indicate informed trading.

## Expected Weekly Move
**What**: Market-implied price range for the next week.
**Calculation**: ATM straddle price (nearest weekly expiry call bid + put bid).
**Use**: Helps size spread widths and set strike distances.

## VIX Level
**What**: CBOE Volatility Index — market-wide fear gauge.
**Source**: Fetched from Schwab quote API for `$VIX.X` or similar.
**Levels**: <15 = low vol, 15-25 = normal, 25-35 = elevated, >35 = crisis
**Use**: Market regime context. High VIX = rich premiums but higher risk.

## Spread Quality
**What**: How tight the bid-ask spread is relative to the option's mid price.
**Calculation**: `(ask - bid) / mid_price`
**Range**: 0.0 to 1.0 (lower is better)
**Use**: Spread quality < 0.10 = good liquidity. > 0.20 = poor, avoid.

## Annualized Return
**What**: The premium received, annualized based on DTE and capital at risk.
**Calculation**: `(premium / capital_required) * (365 / dte)`
**Use**: Compare opportunities across different DTEs and underlyings.

## Probability OTM
**What**: Estimated chance the option expires out of the money.
**Calculation**: Derived from delta: `prob_otm ≈ 1 - |delta|`
**Use**: Higher prob_otm = safer trade, lower premium.

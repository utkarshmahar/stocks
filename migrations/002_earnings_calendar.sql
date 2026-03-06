-- Earnings calendar for manual overrides and fallback when API is unavailable
CREATE TABLE IF NOT EXISTS earnings_calendar (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    earnings_date DATE NOT NULL,
    confirmed BOOLEAN DEFAULT FALSE,
    source VARCHAR(30) DEFAULT 'manual',  -- manual, schwab_api, scraped
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, earnings_date)
);

CREATE INDEX idx_earnings_symbol ON earnings_calendar(symbol);
CREATE INDEX idx_earnings_date ON earnings_calendar(earnings_date);

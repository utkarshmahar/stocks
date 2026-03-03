-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Watchlist: tracked symbols
CREATE TABLE IF NOT EXISTS watchlist (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL UNIQUE,
    active BOOLEAN DEFAULT TRUE,
    added_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed default watchlist
INSERT INTO watchlist (symbol) VALUES ('PANW'), ('QCOM'), ('CSCO')
ON CONFLICT (symbol) DO NOTHING;

-- AI-generated trade recommendations
CREATE TABLE IF NOT EXISTS recommendations (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    strategy VARCHAR(50) NOT NULL,
    legs JSONB NOT NULL,
    max_profit NUMERIC(12,2),
    max_loss NUMERIC(12,2),
    probability_estimate NUMERIC(5,4),
    capital_required NUMERIC(12,2),
    reasoning_summary TEXT,
    risk_flags JSONB DEFAULT '[]',
    risk_approved BOOLEAN,
    risk_notes TEXT,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, taken, ignored, paper_traded
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    outcome JSONB
);

CREATE INDEX idx_recommendations_symbol ON recommendations(symbol);
CREATE INDEX idx_recommendations_status ON recommendations(status);

-- Portfolio positions synced from Schwab
CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    quantity NUMERIC(12,4) NOT NULL,
    avg_price NUMERIC(12,4) NOT NULL,
    current_price NUMERIC(12,4),
    market_value NUMERIC(14,2),
    cost_basis NUMERIC(14,2),
    pnl NUMERIC(14,2),
    pnl_percent NUMERIC(8,4),
    asset_type VARCHAR(20) DEFAULT 'EQUITY',
    last_synced TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, asset_type)
);

-- Sold options premium tracking
CREATE TABLE IF NOT EXISTS premium_collections (
    id SERIAL PRIMARY KEY,
    underlying_symbol VARCHAR(10) NOT NULL,
    option_symbol VARCHAR(50),
    strategy VARCHAR(50),
    premium_collected NUMERIC(12,2) NOT NULL,
    contracts INTEGER DEFAULT 1,
    open_date TIMESTAMPTZ NOT NULL,
    close_date TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'open',  -- open, closed, expired, assigned
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_premium_underlying ON premium_collections(underlying_symbol);

-- Fundamental analysis reports
CREATE TABLE IF NOT EXISTS fundamental_reports (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    report_type VARCHAR(30) NOT NULL,  -- dcf, cash_flow, full_analysis
    report_data JSONB NOT NULL,
    ai_narrative TEXT,
    intrinsic_value NUMERIC(12,2),
    current_price NUMERIC(12,2),
    upside_percent NUMERIC(8,2),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reports_symbol ON fundamental_reports(symbol);

-- EDGAR filing embeddings for RAG
CREATE TABLE IF NOT EXISTS filing_embeddings (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    filing_type VARCHAR(10) NOT NULL,  -- 10-K, 10-Q
    filing_date DATE NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(1024),
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_filing_symbol ON filing_embeddings(symbol);
CREATE INDEX idx_filing_embedding ON filing_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Full audit trail
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    service VARCHAR(50) NOT NULL,
    action VARCHAR(100) NOT NULL,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_service ON audit_log(service);
CREATE INDEX idx_audit_created ON audit_log(created_at);

-- Agent configuration
CREATE TABLE IF NOT EXISTS agent_config (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) NOT NULL UNIQUE,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed default agent config
INSERT INTO agent_config (key, value, description) VALUES
    ('risk_tolerance', '"moderate"', 'Risk tolerance: conservative, moderate, aggressive'),
    ('dte_range', '{"min": 14, "max": 60}', 'Days to expiration range for options'),
    ('delta_range', '{"min": 0.15, "max": 0.35}', 'Delta range for selling options'),
    ('strategies_enabled', '["put_credit_spread", "cash_secured_put", "covered_call", "iron_condor"]', 'Enabled option strategies'),
    ('max_position_pct', '5', 'Max position size as % of portfolio'),
    ('max_sector_pct', '20', 'Max sector exposure as % of portfolio')
ON CONFLICT (key) DO NOTHING;

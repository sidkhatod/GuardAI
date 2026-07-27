CREATE TABLE IF NOT EXISTS agents (
    agent_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    declared_task TEXT NOT NULL,
    declared_intent_vector FLOAT8[],
    base_spend_cap NUMERIC NOT NULL,
    merchant_category_scope TEXT[],
    status TEXT NOT NULL DEFAULT 'active',
    current_epoch INTEGER NOT NULL DEFAULT 1,
    k1 NUMERIC NOT NULL DEFAULT 2.0,
    k2 NUMERIC NOT NULL DEFAULT 3.0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS capability_tokens (
    token_id UUID PRIMARY KEY,
    agent_id UUID REFERENCES agents(agent_id),
    scope TEXT NOT NULL,
    requires_dual_control BOOLEAN NOT NULL DEFAULT false,
    dual_control_approved_by TEXT,
    combined_and_valid BOOLEAN DEFAULT false,
    issued_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    epoch_at_issue INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    entry_id BIGSERIAL PRIMARY KEY,
    agent_id UUID REFERENCES agents(agent_id),
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    policy_version TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_dependencies (
    consumer_agent_id UUID REFERENCES agents(agent_id),
    producer_agent_id UUID REFERENCES agents(agent_id),
    context_ref TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (consumer_agent_id, producer_agent_id, context_ref)
);

CREATE TABLE IF NOT EXISTS pending_approvals (
    approval_id UUID PRIMARY KEY,
    agent_id UUID REFERENCES agents(agent_id),
    request_payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    operator_session_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

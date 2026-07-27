import React, { useContext, useState, useEffect } from 'react';
import { DashboardContext } from '../context/DashboardContext';
import { API_BASE } from '../config';


// Renders the pseudo-Cedar policy as a read-only display for a given agent
function CedarPolicyBlock({ agent }) {
  if (!agent) return null;
  const scopes = agent.merchant_category_scope || [];
  const cap = parseFloat(agent.base_spend_cap).toFixed(2);

  const cedarText = `// Cedar Policy — Agent: ${agent.name}
// Policy Version: v1.0

permit (
  principal == Agent::"${agent.name}",
  action in [
    PaymentAction::"initiate_transfer",
    PaymentAction::"query_balance"
  ],
  resource in [${scopes.map(s => `\n    MerchantCategory::"${s}"`).join(',')}
  ]
)
when {
  // Effective cap is computed dynamically:
  //   effective_cap = base_cap * intent_multiplier * loss_ratio_multiplier
  //   intent_multiplier  = exp(-k1 * divergence_score)  [k1 = ${parseFloat(agent.k1 ?? 2.0).toFixed(2)}]
  //   loss_ratio_multi   = exp(-k2 * loss_ratio)        [k2 = ${parseFloat(agent.k2 ?? 3.0).toFixed(2)}]
  //
  // Configured base cap:  $${cap}
  context.amount <= principal.effective_cap &&
  context.epoch == principal.current_epoch
};

forbid (
  principal == Agent::"${agent.name}",
  action,
  resource
)
unless {
  context.epoch == principal.current_epoch
};`;

  return (
    <div style={{ marginTop: '2rem' }}>
      <h3 style={{ color: 'var(--text-heading)', marginBottom: '0.75rem', fontSize: '1rem' }}>
        Effective Cedar Policy (read-only)
      </h3>
      <pre style={{
        background: '#1e1e2e',
        color: '#cdd6f4',
        borderRadius: 'var(--radius-sm)',
        padding: '1.25rem',
        overflowX: 'auto',
        fontSize: '0.8rem',
        lineHeight: '1.6',
        fontFamily: 'var(--font-mono)',
        margin: 0,
        border: '1px solid #313244'
      }}>
        {cedarText.split('\n').map((line, i) => {
          let color = '#cdd6f4';
          if (line.trimStart().startsWith('//')) color = '#6c7086';
          else if (line.includes('permit') || line.includes('forbid')) color = '#cba6f7';
          else if (line.includes('principal') || line.includes('action') || line.includes('resource')) color = '#89b4fa';
          else if (line.includes('when') || line.includes('unless')) color = '#fab387';
          else if (line.includes('MerchantCategory') || line.includes('PaymentAction') || line.includes('Agent::')) color = '#a6e3a1';
          return <span key={i} style={{ color, display: 'block' }}>{line}</span>;
        })}
      </pre>
    </div>
  );
}

export function PolicyConfig() {
  const { state, dispatch } = useContext(DashboardContext);
  const [selectedAgentId, setSelectedAgentId] = useState('');
  const [form, setForm] = useState({ base_spend_cap: '', merchant_category_scope: '', k1: '', k2: '' });
  const [saveStatus, setSaveStatus] = useState(null); // null | 'saving' | 'success' | 'error'

  const selectedAgent = state.agents.find(a => a.agent_id === selectedAgentId);

  // Populate form when agent is selected
  useEffect(() => {
    if (selectedAgent) {
      setForm({
        base_spend_cap: parseFloat(selectedAgent.base_spend_cap).toFixed(2),
        merchant_category_scope: (selectedAgent.merchant_category_scope || []).join(', '),
        k1: parseFloat(selectedAgent.k1 ?? 2.0).toFixed(2),
        k2: parseFloat(selectedAgent.k2 ?? 3.0).toFixed(2),
      });
      setSaveStatus(null);
    }
  }, [selectedAgentId]);

  const handleSave = async () => {
    if (!selectedAgentId) return;
    setSaveStatus('saving');
    try {
      const body = {
        base_spend_cap: parseFloat(form.base_spend_cap),
        merchant_category_scope: form.merchant_category_scope.split(',').map(s => s.trim()).filter(Boolean),
        k1: parseFloat(form.k1),
        k2: parseFloat(form.k2),
      };
      const resp = await fetch(`${API_BASE}/agents/${selectedAgentId}/policy`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error('Failed');

      // Refresh agents list so the UI reflects new values
      const agentsRes = await fetch(`${API_BASE}/agents`);
      if (agentsRes.ok) {
        const agents = await agentsRes.json();
        dispatch({ type: 'SET_AGENTS', payload: agents });
      }
      setSaveStatus('success');
    } catch (err) {
      console.error(err);
      setSaveStatus('error');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      
      {/* Header */}
      <div className="card">
        <h2 style={{ marginBottom: '0.25rem' }}>Policy Configuration</h2>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Edit per-agent spend caps, merchant scopes, and envelope constants. Changes take effect on the next action request. All updates are written to the immutable ledger.
        </p>
      </div>

      {/* Agent Selector + Form */}
      <div className="card">
        <div style={{ marginBottom: '1.5rem' }}>
          <label className="policy-label">Select Agent</label>
          <select
            className="policy-select"
            value={selectedAgentId}
            onChange={e => setSelectedAgentId(e.target.value)}
          >
            <option value="">— Choose an agent —</option>
            {state.agents.map(a => (
              <option key={a.agent_id} value={a.agent_id}>
                {a.name} ({a.status})
              </option>
            ))}
          </select>
        </div>

        {selectedAgent && (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '1.5rem' }}>
              <div>
                <label className="policy-label">Base Spend Cap ($)</label>
                <input
                  className="policy-input"
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.base_spend_cap}
                  onChange={e => setForm(f => ({ ...f, base_spend_cap: e.target.value }))}
                />
                <div className="policy-hint">The raw cap before multipliers are applied.</div>
              </div>
              <div>
                <label className="policy-label">Merchant Category Scope</label>
                <input
                  className="policy-input"
                  type="text"
                  value={form.merchant_category_scope}
                  onChange={e => setForm(f => ({ ...f, merchant_category_scope: e.target.value }))}
                  placeholder="e.g. data, analytics, cloud"
                />
                <div className="policy-hint">Comma-separated list of allowed merchant categories.</div>
              </div>
              <div>
                <label className="policy-label">K1 — Intent Divergence Sensitivity</label>
                <input
                  className="policy-input"
                  type="number"
                  min="0"
                  step="0.1"
                  value={form.k1}
                  onChange={e => setForm(f => ({ ...f, k1: e.target.value }))}
                />
                <div className="policy-hint">Higher K1 = more aggressive cap reduction when agent drifts from declared intent. Default: 2.0</div>
              </div>
              <div>
                <label className="policy-label">K2 — Loss Ratio Sensitivity</label>
                <input
                  className="policy-input"
                  type="number"
                  min="0"
                  step="0.1"
                  value={form.k2}
                  onChange={e => setForm(f => ({ ...f, k2: e.target.value }))}
                />
                <div className="policy-hint">Higher K2 = steeper cap reduction as agent's failure rate increases. Default: 3.0</div>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <button className="btn-primary" onClick={handleSave} disabled={saveStatus === 'saving'}>
                {saveStatus === 'saving' ? 'Saving...' : 'Save & Reload Policy'}
              </button>
              {saveStatus === 'success' && (
                <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>
                  ✓ Policy updated and logged to ledger.
                </span>
              )}
              {saveStatus === 'error' && (
                <span style={{ color: 'var(--color-danger)', fontWeight: 600 }}>
                  ✗ Save failed. Check backend logs.
                </span>
              )}
            </div>

            <CedarPolicyBlock agent={{
              ...selectedAgent,
              base_spend_cap: form.base_spend_cap || selectedAgent.base_spend_cap,
              merchant_category_scope: form.merchant_category_scope.split(',').map(s => s.trim()).filter(Boolean),
              k1: form.k1 || selectedAgent.k1,
              k2: form.k2 || selectedAgent.k2,
            }} />
          </>
        )}
      </div>
    </div>
  );
}

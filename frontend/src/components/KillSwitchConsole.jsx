import React, { useContext, useState } from 'react';
import { DashboardContext } from '../context/DashboardContext';
import { API_BASE } from '../config';


export function KillSwitchConsole() {
  const { state } = useContext(DashboardContext);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleEmergencyStop = async () => {
    setLoading(true);
    try {
      await fetch(`${API_BASE}/fleet/emergency-stop`, {
        method: 'POST'
      });
      setShowConfirm(false);
    } catch (err) {
      console.error("Emergency stop failed:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleRevokeAgent = async (agentId) => {
    try {
      await fetch(`${API_BASE}/agents/${agentId}/revoke`, {
        method: 'POST'
      });
    } catch (err) {
      console.error("Failed to revoke agent:", err);
    }
  };

  // Filter ledger for cascade/ops events
  const opsEvents = state.ledger.filter(entry => 
    ['agent_revoked', 'agent_quarantined', 'fleet_emergency_stop', 'action_denied'].includes(entry.event_type) && 
    (entry.event_type !== 'action_denied' || (entry.event_data && entry.event_data.reason && entry.event_data.reason.includes('mismatch')))
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      
      {/* Top Banner: Global Epoch & Emergency Stop */}
      <div className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderColor: 'var(--color-danger-light)', background: '#fffafa' }}>
        <div>
          <h2 style={{ color: 'var(--color-danger)', marginBottom: '0.25rem' }}>Global Security Context</h2>
          <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Current Fleet Epoch: <strong className="mono" style={{ color: 'var(--text-heading)', fontSize: '1.25rem' }}>{state.global_epoch}</strong></div>
        </div>
        
        <div>
          {!showConfirm ? (
            <button 
              style={{ background: 'var(--color-danger)', color: 'white', border: 'none', padding: '1rem 2rem', borderRadius: '8px', fontSize: '1.25rem', fontWeight: 700, cursor: 'pointer', boxShadow: '0 4px 12px rgba(244, 67, 54, 0.4)' }}
              onClick={() => setShowConfirm(true)}
            >
              EMERGENCY STOP (ALL AGENTS)
            </button>
          ) : (
            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
              <span style={{ color: 'var(--color-danger)', fontWeight: 600 }}>Are you absolutely sure?</span>
              <button 
                className="btn-danger" 
                onClick={handleEmergencyStop}
                disabled={loading}
                style={{ padding: '0.75rem 1.5rem', fontWeight: 700 }}
              >
                {loading ? 'EXECUTING...' : 'YES, HALT FLEET'}
              </button>
              <button 
                style={{ background: 'transparent', border: '1px solid var(--border-color)', padding: '0.75rem 1.5rem', borderRadius: 'var(--radius-sm)', cursor: 'pointer', color: 'var(--text-primary)' }}
                onClick={() => setShowConfirm(false)}
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '2rem' }}>
        {/* Cascade Log Feed */}
        <div className="card">
          <h3 style={{ marginBottom: '1rem', color: 'var(--text-heading)' }}>Real-time Operations Log</h3>
          <div className="log-feed">
            {opsEvents.length === 0 ? (
              <div style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '2rem' }}>No operational events recorded in this session.</div>
            ) : (
              opsEvents.map((entry, idx) => {
                const date = new Date(entry.created_at).toLocaleTimeString();
                let msg = entry.event_type;
                if (entry.event_type === 'agent_quarantined') msg = `Agent Quarantined: Producer revoked`;
                if (entry.event_type === 'agent_revoked') msg = `Agent Revoked manually`;
                if (entry.event_type === 'fleet_emergency_stop') msg = `GLOBAL EMERGENCY STOP TRIGGERED`;
                if (entry.event_type === 'action_denied') msg = `Action Denied: Epoch mismatch`;
                
                return (
                  <div key={idx} style={{ display: 'flex', gap: '1rem', borderBottom: '1px solid #333', paddingBottom: '0.5rem' }}>
                    <span style={{ color: '#58a6ff' }}>[{date}]</span>
                    <span style={{ color: '#d2a8ff', width: '280px', flexShrink: 0 }}>{entry.agent_id}</span>
                    <span style={{ color: entry.event_type === 'fleet_emergency_stop' ? '#ff7b72' : '#a9b7c6' }}>{msg}</span>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Individual Agent Revoke List */}
        <div className="card">
          <h3 style={{ marginBottom: '1rem', color: 'var(--text-heading)' }}>Targeted Revocation</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {state.agents.map(agent => (
              <div key={agent.agent_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem', background: 'var(--bg-body)', borderRadius: 'var(--radius-sm)' }}>
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.9rem' }}>{agent.name}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }} className="mono">{agent.status.toUpperCase()}</div>
                </div>
                <button 
                  className="btn-danger"
                  onClick={() => handleRevokeAgent(agent.agent_id)}
                  disabled={agent.status === 'revoked'}
                  style={{ opacity: agent.status === 'revoked' ? 0.5 : 1, fontSize: '0.75rem', padding: '0.4rem 0.75rem' }}
                >
                  Revoke
                </button>
              </div>
            ))}
            {state.agents.length === 0 && (
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>No active agents.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import { API_BASE } from '../config';


export function AgentCard({ agent, lastHeartbeat }) {
  const [isAlive, setIsAlive] = useState(false);

  useEffect(() => {
    // Check heartbeat freshness every second
    const interval = setInterval(() => {
      if (!lastHeartbeat) {
        setIsAlive(false);
      } else {
        // If heartbeat was within the last 15 seconds, consider it alive
        const diff = Date.now() - new Date(lastHeartbeat).getTime();
        setIsAlive(diff < 15000);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [lastHeartbeat]);

  const handleRevoke = async () => {
    try {
      await fetch(`${API_BASE}/agents/${agent.agent_id}/revoke`, {
        method: 'POST'
      });
    } catch (err) {
      console.error("Failed to revoke agent:", err);
    }
  };

  const getStatusBadgeClass = (status) => {
    if (status === 'active') return 'badge-active';
    if (status === 'quarantined') return 'badge-quarantined';
    return 'badge-revoked';
  };

  // Safe defaults if envelope stats not yet broadcasted
  const effectiveCap = agent.effective_cap ?? agent.base_spend_cap;
  const intentMultiplier = agent.intent_multiplier ?? 1.0;
  const lossRatioMultiplier = agent.loss_ratio_multiplier ?? 1.0;

  return (
    <div className="card">
      <div className="card-title">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span className={`heartbeat-dot ${isAlive ? 'heartbeat-alive' : 'heartbeat-dead'}`}></span>
          <span style={{ fontWeight: 600 }}>{agent.name}</span>
        </div>
        <span className={`badge ${getStatusBadgeClass(agent.status)}`}>
          {agent.status}
        </span>
      </div>
      
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1.5rem', marginTop: '1rem' }}>
        <div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '0.25rem', fontWeight: 600 }}>Effective Cap</div>
          <div className="mono" style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-heading)' }}>
            ${parseFloat(effectiveCap).toFixed(2)}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Intent Mult: <span className="mono">{intentMultiplier.toFixed(2)}x</span></div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Loss Ratio Mult: <span className="mono">{lossRatioMultiplier.toFixed(2)}x</span></div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Base Cap: <span className="mono">${parseFloat(agent.base_spend_cap).toFixed(0)}</span></div>
        </div>
      </div>
      
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-color)', paddingTop: '1rem' }}>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>ID: {agent.agent_id.substring(0, 8)}...</div>
        <button 
          className="btn-danger" 
          onClick={handleRevoke}
          disabled={agent.status === 'revoked'}
          style={{ opacity: agent.status === 'revoked' ? 0.5 : 1, padding: '0.4rem 0.75rem', fontSize: '0.8rem' }}
        >
          Revoke
        </button>
      </div>
    </div>
  );
}

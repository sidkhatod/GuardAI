import React, { useContext, useState, useRef, useEffect } from 'react';
import { DashboardContext } from '../context/DashboardContext';
import { API_BASE } from '../config';


export function LedgerViewer() {
  const { state, dispatch } = useContext(DashboardContext);
  const [verificationStatus, setVerificationStatus] = useState(null); // null, 'valid', 'invalid'
  const [mismatchDetails, setMismatchDetails] = useState(null);
  const [loading, setLoading] = useState(false);
  const tableRef = useRef(null);
  
  // Format the payload intelligently so it isn't just raw JSON
  const summarizePayload = (type, payload) => {
    if (payload.tampered) return <span style={{color: 'red', fontWeight: 'bold'}}>[TAMPERED DATA]</span>;
    
    switch (type) {
      case 'agent_registered':
        return `Task: ${payload.declared_task}`;
      case 'action_requested':
        return `Token: ${payload.token_id?.substring(0,8)}... Action: ${payload.action_type}`;
      case 'action_approved':
        return `Token: ${payload.token_id?.substring(0,8)}... Split Auth Approved`;
      case 'action_resolved':
        return `Token: ${payload.token_id?.substring(0,8)}... Success: ${payload.success}`;
      case 'fleet_emergency_stop':
        return `Global Epoch Incremented`;
      case 'agent_revoked':
      case 'agent_quarantined':
        return `Status updated to ${type.split('_')[1]}`;
      default:
        return JSON.stringify(payload).substring(0, 50) + '...';
    }
  };

  const handleVerify = async () => {
    setLoading(true);
    setVerificationStatus(null);
    setMismatchDetails(null);
    try {
      const resp = await fetch(`${API_BASE}/ledger/verify`, { method: 'POST' });
      const data = await resp.json();
      
      if (data.valid) {
        setVerificationStatus('valid');
      } else {
        setVerificationStatus('invalid');
        setMismatchDetails({
          entryId: data.first_mismatch_entry_id,
          expected: data.expected_hash,
          actual: data.actual_hash
        });
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSimulateTamper = async () => {
    try {
      await fetch(`${API_BASE}/ledger/simulate-tamper`, { method: 'POST' });
      // Reset verification state since we just tampered with it
      setVerificationStatus(null);
      // Fetch latest ledger to visibly show the payload change
      const ledgerRes = await fetch(`${API_BASE}/ledger`);
      if (ledgerRes.ok) {
        const ledger = await ledgerRes.json();
        dispatch({ type: 'SET_LEDGER', payload: ledger });
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Scroll to tampered row if invalid
  useEffect(() => {
    if (verificationStatus === 'invalid' && mismatchDetails?.entryId) {
      const row = document.getElementById(`entry-${mismatchDetails.entryId}`);
      if (row) {
        row.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [verificationStatus, mismatchDetails]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', height: '100%' }}>
      
      {/* Header Controls */}
      <div className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ marginBottom: '0.25rem', color: 'var(--text-heading)' }}>Immutable Ledger</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', margin: 0 }}>
            Cryptographically chained events tracking every fleet action.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <button className="btn-secondary" onClick={handleSimulateTamper}>
            Simulate Tamper
          </button>
          <button className="btn-primary" onClick={handleVerify} disabled={loading}>
            {loading ? 'Verifying...' : 'Verify Chain'}
          </button>
        </div>
      </div>

      {/* Verification Banners */}
      {verificationStatus === 'valid' && (
        <div className="verification-banner banner-valid">
          <div>
            <div style={{ fontWeight: 700, fontSize: '1.1rem' }}>Chain Verified Successfully</div>
            <div style={{ fontSize: '0.9rem' }}>All cryptographic hashes match. The ledger is intact and untampered.</div>
          </div>
          <span style={{ fontSize: '1.5rem' }}>✓</span>
        </div>
      )}

      {verificationStatus === 'invalid' && mismatchDetails && (
        <div className="verification-banner banner-invalid">
          <div>
            <div style={{ fontWeight: 700, fontSize: '1.1rem' }}>⚠️ CRYPTOGRAPHIC VERIFICATION FAILED</div>
            <div style={{ fontSize: '0.9rem', marginTop: '0.5rem' }}>
              Tampering detected at <strong>Entry ID {mismatchDetails.entryId}</strong>
            </div>
            <div className="mono" style={{ fontSize: '0.8rem', marginTop: '0.5rem', opacity: 0.9 }}>
              Expected: {mismatchDetails.expected}<br/>
              Actual Hash: {mismatchDetails.actual}
            </div>
          </div>
        </div>
      )}

      {/* Ledger Table */}
      <div className="card" style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', padding: 0 }}>
        <div style={{ overflowY: 'auto', flex: 1 }} ref={tableRef}>
          <table className="data-table">
            <thead style={{ position: 'sticky', top: 0, backgroundColor: 'var(--bg-surface)', zIndex: 1, boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
              <tr>
                <th>ID</th>
                <th>Timestamp</th>
                <th>Agent</th>
                <th>Event Type</th>
                <th>Payload Summary</th>
              </tr>
            </thead>
            <tbody>
              {state.ledger.map(entry => {
                const isTampered = verificationStatus === 'invalid' && mismatchDetails?.entryId === entry.entry_id;
                
                return (
                  <tr 
                    key={entry.entry_id} 
                    id={`entry-${entry.entry_id}`}
                    className={isTampered ? 'tampered-row' : ''}
                  >
                    <td>{entry.entry_id}</td>
                    <td>{new Date(entry.created_at).toLocaleString()}</td>
                    <td>
                      {entry.agent_id ? (
                        <span title={entry.agent_id}>{entry.agent_id.substring(0, 8)}...</span>
                      ) : (
                        <span style={{ color: 'var(--text-secondary)' }}>System</span>
                      )}
                    </td>
                    <td>
                      <span style={{ 
                        backgroundColor: 'var(--bg-body)', 
                        padding: '0.25rem 0.5rem', 
                        borderRadius: '4px',
                        fontSize: '0.8rem'
                      }}>
                        {entry.event_type}
                      </span>
                    </td>
                    <td>{summarizePayload(entry.event_type, entry.payload)}</td>
                  </tr>
                );
              })}
              {state.ledger.length === 0 && (
                <tr>
                  <td colSpan="5" style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-secondary)' }}>
                    No ledger entries found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

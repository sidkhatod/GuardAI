import React, { useContext, useState, useEffect, useRef } from 'react';
import { DashboardContext } from '../context/DashboardContext';
import { API_BASE } from '../config';


const TARGET = 460_000_000;

function formatDollars(n) {
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(2)}B`;
  if (n >= 1_000_000)     return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)         return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

// Animated odometer-style counter
function Counter({ value, color, frozen }) {
  const [display, setDisplay] = useState(value);
  const rafRef = useRef(null);
  const prevRef = useRef(value);

  useEffect(() => {
    if (frozen) { setDisplay(value); return; }
    const start = prevRef.current;
    const end   = value;
    const duration = 120;
    const startTime = performance.now();

    const animate = (now) => {
      const progress = Math.min((now - startTime) / duration, 1);
      setDisplay(start + (end - start) * progress);
      if (progress < 1) rafRef.current = requestAnimationFrame(animate);
      else prevRef.current = end;
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [value, frozen]);

  const pct = Math.min((display / TARGET) * 100, 100);

  return (
    <div style={{ width: '100%' }}>
      <div style={{
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 'clamp(2rem, 5vw, 3.5rem)',
        fontWeight: 700,
        color,
        letterSpacing: '-1px',
        lineHeight: 1,
        textShadow: frozen ? 'none' : `0 0 30px ${color}55`,
        transition: 'color 0.3s'
      }}>
        {formatDollars(display)}
      </div>
      <div style={{ marginTop: '0.75rem', height: '6px', background: '#e3e8ef', borderRadius: '3px', overflow: 'hidden' }}>
        <div style={{
          height: '100%',
          width: `${pct}%`,
          background: color,
          borderRadius: '3px',
          transition: 'width 0.12s linear',
          boxShadow: frozen ? 'none' : `0 0 8px ${color}88`
        }} />
      </div>
      <div style={{ marginTop: '0.4rem', fontSize: '0.75rem', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
        {pct.toFixed(1)}% of $460M
      </div>
    </div>
  );
}

export function KnightCapitalReplay() {
  const { state } = useContext(DashboardContext);
  const [demo, setDemo]     = useState(null);  // null | 'running' | 'complete'
  const [noGov, setNoGov]   = useState(0);
  const [gov, setGov]       = useState(0);
  const [frozen, setFrozen] = useState(false);
  const [freezeReason, setFreezeReason] = useState('');
  const [elapsed, setElapsed] = useState(0);
  const [showClosing, setShowClosing] = useState(false);

  // Listen for knight_capital_broadcast messages from the WS fleet hook
  useEffect(() => {
    const handler = (e) => {
      const msg = e.detail;
      if (msg.channel !== 'knight_capital_broadcast') return;
      const p = msg.payload;

      if (p.reset) {
        setNoGov(0); setGov(0); setFrozen(false);
        setFreezeReason(''); setElapsed(0);
        setDemo(null); setShowClosing(false);
        return;
      }

      setNoGov(p.no_gov_total ?? 0);
      setGov(p.gov_total ?? 0);
      setFrozen(p.gov_frozen ?? false);
      setFreezeReason(p.gov_freeze_reason ?? '');
      setElapsed(p.elapsed_seconds ?? 0);
      if (p.complete) { setDemo('complete'); setShowClosing(true); }
    };

    window.addEventListener('ws-knight-capital', handler);
    return () => window.removeEventListener('ws-knight-capital', handler);
  }, []);

  // Also watch the context ledger for messages coming through useWebSockets hook
  useEffect(() => {
    // useWebSockets already dispatches to DashboardContext — we need to tap it
    // The hook sends raw WS messages; we intercept via a custom event from useWebSockets
  }, []);

  const handleStart = async () => {
    setDemo('running');
    setShowClosing(false);
    await fetch(`${API_BASE}/demo/knight-capital/start`, { method: 'POST' });
  };

  const handleReset = async () => {
    await fetch(`${API_BASE}/demo/knight-capital/reset`, { method: 'POST' });
    setNoGov(0); setGov(0); setFrozen(false);
    setFreezeReason(''); setElapsed(0);
    setDemo(null); setShowClosing(false);
  };

  const elapsedStr = `${Math.floor(elapsed / 60).toString().padStart(2, '0')}:${Math.floor(elapsed % 60).toString().padStart(2, '0')}`;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', minHeight: '100%' }}>

      {/* Header */}
      <div className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ margin: 0, color: 'var(--text-heading)' }}>Knight Capital Replay</h2>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            Same order stream. Two worlds. One has governance.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          {demo === 'running' && (
            <div style={{ fontFamily: 'monospace', fontSize: '1.1rem', color: 'var(--color-primary)', fontWeight: 600 }}>
              {elapsedStr}
            </div>
          )}
          {demo !== 'running' ? (
            <button
              onClick={handleStart}
              style={{
                background: 'linear-gradient(135deg, #f44336 0%, #d32f2f 100%)',
                color: 'white', border: 'none',
                padding: '0.75rem 2rem',
                borderRadius: 'var(--radius-sm)',
                fontSize: '1rem', fontWeight: 700,
                cursor: 'pointer',
                boxShadow: '0 4px 15px rgba(244,67,54,0.35)',
                transition: 'transform 0.1s'
              }}
              onMouseDown={e => e.currentTarget.style.transform = 'scale(0.97)'}
              onMouseUp={e => e.currentTarget.style.transform = 'scale(1)'}
            >
              ▶ START REPLAY
            </button>
          ) : (
            <button
              onClick={handleReset}
              style={{
                background: 'var(--bg-body)', color: 'var(--text-primary)',
                border: '1px solid var(--border-color)',
                padding: '0.75rem 1.5rem',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.9rem', fontWeight: 600, cursor: 'pointer'
              }}
            >
              ↺ Reset
            </button>
          )}
          {demo === 'complete' && (
            <button onClick={handleReset} style={{
              background: 'var(--bg-body)', color: 'var(--text-primary)',
              border: '1px solid var(--border-color)',
              padding: '0.75rem 1.5rem',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.9rem', fontWeight: 600, cursor: 'pointer'
            }}>
              ↺ Reset
            </button>
          )}
        </div>
      </div>

      {/* Dual Counter Area */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>

        {/* NO GOVERNANCE */}
        <div className="card" style={{
          border: '2px solid #ffcdd2',
          background: 'linear-gradient(160deg, #fff5f5 0%, #ffffff 100%)',
          position: 'relative', overflow: 'hidden'
        }}>
          <div style={{
            position: 'absolute', top: 0, right: 0, left: 0, height: '3px',
            background: 'linear-gradient(90deg, #f44336, #ff7043)'
          }} />
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{
                background: '#ffcdd2', color: '#b71c1c',
                padding: '0.2rem 0.6rem', borderRadius: '4px',
                fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px'
              }}>
                NO GOVERNANCE
              </span>
              <span style={{ fontSize: '0.75rem', color: '#b71c1c', fontFamily: 'monospace' }}>
                runaway loop active
              </span>
            </div>
          </div>
          <Counter value={noGov} color="#e53935" frozen={false} />
          <div style={{ marginTop: '1.25rem', fontSize: '0.8rem', color: '#c62828', lineHeight: 1.5 }}>
            Every order executes. No intent check. No loss-ratio guard. No spending cap enforcement.
            Unattended automation bleeding capital at machine speed.
          </div>
        </div>

        {/* WITH GOVERNANCE */}
        <div className="card" style={{
          border: `2px solid ${frozen ? '#bbdefb' : '#c8e6c9'}`,
          background: frozen
            ? 'linear-gradient(160deg, #e3f2fd 0%, #ffffff 100%)'
            : 'linear-gradient(160deg, #f1f8e9 0%, #ffffff 100%)',
          position: 'relative', overflow: 'hidden',
          transition: 'border-color 0.5s, background 0.5s'
        }}>
          <div style={{
            position: 'absolute', top: 0, right: 0, left: 0, height: '3px',
            background: frozen
              ? 'linear-gradient(90deg, #1976d2, #42a5f5)'
              : 'linear-gradient(90deg, #388e3c, #66bb6a)'
          }} />
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{
                background: frozen ? '#bbdefb' : '#c8e6c9',
                color: frozen ? '#0d47a1' : '#1b5e20',
                padding: '0.2rem 0.6rem', borderRadius: '4px',
                fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px'
              }}>
                WITH GOVERNANCE
              </span>
              {frozen ? (
                <span style={{
                  background: '#1976d2', color: 'white',
                  padding: '0.2rem 0.6rem', borderRadius: '4px',
                  fontSize: '0.7rem', fontWeight: 700
                }}>
                  SYSTEM HALTED
                </span>
              ) : (
                <span style={{ fontSize: '0.75rem', color: '#2e7d32', fontFamily: 'monospace' }}>
                  gateway active
                </span>
              )}
            </div>
          </div>
          <Counter value={gov} color={frozen ? '#1976d2' : '#43a047'} frozen={frozen} />
          {frozen ? (
            <div style={{ marginTop: '1.25rem', fontSize: '0.8rem', color: '#0d47a1', lineHeight: 1.5 }}>
              <strong>Governance intervened.</strong><br />
              Reason: <code style={{ background: '#e3f2fd', padding: '0 4px', borderRadius: '3px' }}>{freezeReason}</code>
              <br />Intent divergence and sliding-window enforcement halted the runaway. Loss locked at {formatDollars(gov)}.
            </div>
          ) : (
            <div style={{ marginTop: '1.25rem', fontSize: '0.8rem', color: '#2e7d32', lineHeight: 1.5 }}>
              Heartbeat check, epoch check, Cedar eligibility, intent-divergence envelope, and sliding-window
              cap enforcement running on every order in real time.
            </div>
          )}
        </div>
      </div>

      {/* Difference callout */}
      {(noGov > 0 || gov > 0) && (
        <div className="card" style={{
          background: 'linear-gradient(90deg, #fff3e0, #ffffff)',
          border: '1px solid #ffe0b2',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center'
        }}>
          <div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 600 }}>
              Governance Saved
            </div>
            <div style={{ fontFamily: 'monospace', fontSize: '1.75rem', fontWeight: 700, color: '#e65100' }}>
              {formatDollars(noGov - gov)}
            </div>
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', textAlign: 'right', maxWidth: '55%', lineHeight: 1.5 }}>
            The delta between an uncontrolled runaway and a governed system, computed in real time
            as governance blocks each unauthorized order.
          </div>
        </div>
      )}

      {/* Closing Card — appears when no-governance counter completes */}
      {showClosing && (
        <div style={{
          background: 'linear-gradient(135deg, #0d0d0d 0%, #1a1a2e 100%)',
          borderRadius: 'var(--radius-md)',
          padding: '3rem',
          textAlign: 'center',
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
          animation: 'fadeInUp 0.6s ease forwards'
        }}>
          <p style={{
            fontFamily: "'Inter', sans-serif",
            fontSize: 'clamp(1rem, 2.5vw, 1.4rem)',
            color: '#e0e0e0',
            lineHeight: 1.8,
            margin: 0,
            fontWeight: 300,
            letterSpacing: '0.01em'
          }}>
            "Knight Capital, 2012: $460M in 45 minutes, no automated threshold.
            <br />This is the layer that closes that gap."
          </p>
        </div>
      )}
    </div>
  );
}

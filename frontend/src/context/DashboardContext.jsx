import React, { createContext, useReducer, useEffect } from 'react';
import { API_BASE } from '../config';


// Initial state
const initialState = {
  agents: [], // List of agent objects
  heartbeats: {}, // agent_id -> last_tick_timestamp
  ledger: [], // List of ledger entries
  global_epoch: 1,
  pending_approvals: [] // high-risk actions pending operator decision
};

// Reducer
function dashboardReducer(state, action) {
  switch (action.type) {
    case 'SET_AGENTS':
      return { ...state, agents: action.payload };
    case 'UPDATE_AGENT_STATUS': {
      const { agent_id, status } = action.payload;
      return {
        ...state,
        agents: state.agents.map(a => 
          a.agent_id === agent_id ? { ...a, status } : a
        )
      };
    }
    case 'UPDATE_EFFECTIVE_CAP': {
      const { agent_id, effective_cap, intent_multiplier, loss_ratio_multiplier, divergence_score, loss_ratio, current_window_sum } = action.payload;
      return {
        ...state,
        agents: state.agents.map(a =>
          a.agent_id === agent_id ? { 
            ...a, 
            effective_cap, 
            intent_multiplier, 
            loss_ratio_multiplier, 
            divergence_score, 
            loss_ratio, 
            current_window_sum 
          } : a
        )
      };
    }
    case 'HEARTBEAT_TICK': {
      const { agent_id, timestamp } = action.payload;
      return {
        ...state,
        heartbeats: {
          ...state.heartbeats,
          [agent_id]: timestamp
        }
      };
    }
    case 'REVOKE_BROADCAST': {
      const { event, new_epoch } = action.payload;
      if (event === 'fleet_emergency_stop' && new_epoch) {
        return { ...state, global_epoch: new_epoch };
      }
      return state;
    }
    case 'SET_LEDGER':
      return { ...state, ledger: action.payload };
    case 'ADD_LEDGER_ENTRY':
      // Prepend new entry
      return { ...state, ledger: [action.payload, ...state.ledger] };
    case 'ADD_PENDING_APPROVAL':
      return { 
        ...state, 
        pending_approvals: [...state.pending_approvals, action.payload]
      };
    case 'REMOVE_PENDING_APPROVAL':
      return {
        ...state,
        pending_approvals: state.pending_approvals.filter(p => p.approval_id !== action.payload)
      };
    default:
      return state;
  }
}

export const DashboardContext = createContext();

export function DashboardProvider({ children }) {
  const [state, dispatch] = useReducer(dashboardReducer, initialState);

  // Initial REST fetch
  useEffect(() => {
    async function fetchData() {
      try {
        const [agentsRes, ledgerRes] = await Promise.all([
          fetch(`${API_BASE}/agents`),
          fetch(`${API_BASE}/ledger`)
        ]);
        
        if (agentsRes.ok) {
          const agents = await agentsRes.json();
          dispatch({ type: 'SET_AGENTS', payload: agents });
          // If any agents exist, use the max current_epoch to estimate global_epoch initially
          if (agents.length > 0) {
              const maxEpoch = Math.max(...agents.map(a => a.current_epoch));
              state.global_epoch = maxEpoch; // Note: better if global_epoch was explicitly exposed by an API
          }
        }
        
        if (ledgerRes.ok) {
          const ledger = await ledgerRes.json();
          dispatch({ type: 'SET_LEDGER', payload: ledger });
        }
      } catch (err) {
        console.error("Error fetching initial state:", err);
      }
    }
    fetchData();
  }, []);

  return (
    <DashboardContext.Provider value={{ state, dispatch }}>
      {children}
    </DashboardContext.Provider>
  );
}

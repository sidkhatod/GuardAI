import React, { useContext } from 'react';
import { DashboardContext } from '../context/DashboardContext';
import { AgentCard } from './AgentCard';

export function FleetView() {
  const { state } = useContext(DashboardContext);

  if (!state.agents || state.agents.length === 0) {
    return (
      <div className="card placeholder-panel">
        <h2>No Agents Registered</h2>
        <p>Start an agent to see it in the fleet view.</p>
      </div>
    );
  }

  return (
    <div className="grid-container">
      {state.agents.map(agent => (
        <AgentCard 
          key={agent.agent_id} 
          agent={agent} 
          lastHeartbeat={state.heartbeats[agent.agent_id]} 
        />
      ))}
    </div>
  );
}

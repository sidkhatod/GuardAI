import { useEffect, useContext } from 'react';
import { DashboardContext } from '../context/DashboardContext';
import { WS_BASE } from '../config';


export function useWebSockets() {
  const { dispatch } = useContext(DashboardContext);

  useEffect(() => {
    const fleetWs = new WebSocket(`${WS_BASE}/ws/fleet`);
    const ledgerWs = new WebSocket(`${WS_BASE}/ws/ledger`);

    fleetWs.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const { channel, payload } = data;
      console.log(`[Fleet WS] ${channel}:`, payload);
      
      switch (channel) {
        case 'heartbeat_broadcast':
          dispatch({ type: 'HEARTBEAT_TICK', payload });
          break;
        case 'revoke_broadcast':
          dispatch({ type: 'REVOKE_BROADCAST', payload });
          break;
        case 'effective_cap_broadcast':
          dispatch({ type: 'UPDATE_EFFECTIVE_CAP', payload });
          break;
        case 'agent_status_broadcast':
          dispatch({ type: 'UPDATE_AGENT_STATUS', payload });
          break;
        case 'pending_approvals':
          dispatch({ type: 'ADD_PENDING_APPROVAL', payload });
          break;
        case 'knight_capital_broadcast':
          // Dispatch as a custom DOM event so KnightCapitalReplay can listen directly
          window.dispatchEvent(new CustomEvent('ws-knight-capital', { detail: { channel, payload } }));
          break;
        default:
          break;
      }
    };

    ledgerWs.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const { channel, payload } = data;
      console.log(`[Ledger WS] ${channel}:`, payload);
      
      if (channel === 'ledger_broadcast') {
        dispatch({ type: 'ADD_LEDGER_ENTRY', payload });
      }
    };

    return () => {
      fleetWs.close();
      ledgerWs.close();
    };
  }, [dispatch]);
}

import React, { useState } from 'react';
import { DashboardProvider } from './context/DashboardContext';
import { useWebSockets } from './hooks/useWebSockets';
import { FleetView } from './components/FleetView';
import { KillSwitchConsole } from './components/KillSwitchConsole';
import { LedgerViewer } from './components/LedgerViewer';
import { PolicyConfig } from './components/PolicyConfig';
import { KnightCapitalReplay } from './components/KnightCapitalReplay';
import { LayoutDashboard, ShieldAlert, FileText, Settings, History, Search, Bell, User } from 'lucide-react';

function DashboardContent() {
  const [activeTab, setActiveTab] = useState('fleet');
  useWebSockets();

  const tabs = [
    { id: 'fleet', label: 'Fleet View', icon: <LayoutDashboard size={18} /> },
    { id: 'kill-switch', label: 'Kill Switch Console', icon: <ShieldAlert size={18} /> },
    { id: 'ledger', label: 'Ledger Viewer', icon: <FileText size={18} /> },
    { id: 'policy', label: 'Policy Config', icon: <Settings size={18} /> },
    { id: 'replay', label: 'Knight Capital Replay', icon: <History size={18} /> },
  ];

  return (
    <div className="dashboard-layout">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="brand">
            <span style={{ color: '#2196f3' }}>✦</span> GovLayer
          </div>
        </div>
        
        <div className="nav-section">Navigation</div>
        <nav className="nav-menu">
          {tabs.map(tab => (
            <button 
              key={tab.id}
              className={`nav-item ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          ))}
        </nav>
      </aside>

      {/* Main Content Area */}
      <div className="main-area">
        {/* Top Header */}
        <header className="top-header">
          <div className="header-search">
            <Search size={16} color="var(--text-secondary)" style={{ marginRight: '8px' }} />
            <input type="text" placeholder="Search (Ctrl + K)" />
          </div>
          
          <div className="header-actions">
            <div className="status-badge">
              <div className="status-dot"></div>
              OPERATIONAL
            </div>
            <Bell size={20} color="var(--text-secondary)" style={{ cursor: 'pointer' }} />
            <div style={{ width: '32px', height: '32px', borderRadius: '50%', backgroundColor: '#e3f2fd', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#2196f3', cursor: 'pointer' }}>
              <User size={18} />
            </div>
          </div>
        </header>

        {/* Tab Content Wrapper */}
        <main className="content-wrapper">
          {/* Dashboard Hero Banner (Only show on Fleet view for now) */}
          {activeTab === 'fleet' && (
            <div className="hero-banner">
              <div>
                <h1>Governance Fleet Control</h1>
                <p>Monitor autonomous agents, review high-risk actions, and enforce policies in real-time. Endless possibilities with dynamic dual-control.</p>
                <button className="hero-btn">View Metrics</button>
              </div>
              <div style={{ fontSize: '4rem', opacity: 0.8 }}>🚀</div>
            </div>
          )}

          {/* Active Tab Panel */}
          {activeTab === 'fleet' && <FleetView />}
          {activeTab === 'kill-switch' && <KillSwitchConsole />}
          {activeTab === 'ledger' && <LedgerViewer />}
          {activeTab === 'policy' && <PolicyConfig />}
          {activeTab === 'replay' && <KnightCapitalReplay />}
        </main>
      </div>
    </div>
  );
}

function App() {
  return (
    <DashboardProvider>
      <DashboardContent />
    </DashboardProvider>
  );
}

export default App;

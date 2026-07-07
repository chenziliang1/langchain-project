import { useState } from 'react';
import { LayoutDashboard, Sparkles, Activity, TrendingUp } from 'lucide-react';
import Dashboard from './components/Dashboard';
import ExplorePanel from './components/ExplorePanel';
import ForecastWorkspace from './components/ForecastWorkspace';

type Tab = 'dashboard' | 'explore' | 'forecast';

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('explore');

  return (
    <div className="app-layout">
      <header className="app-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Activity size={22} color="#3b82f6" />
          <h1>GDELT Analysis Platform</h1>
        </div>

        <div className="nav-tabs">
          <button
            className={`nav-tab ${activeTab === 'explore' ? 'active' : ''}`}
            onClick={() => setActiveTab('explore')}
          >
            <Sparkles size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} />
            AI Explore
          </button>
          <button
            className={`nav-tab ${activeTab === 'forecast' ? 'active' : ''}`}
            onClick={() => setActiveTab('forecast')}
          >
            <TrendingUp size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} />
            Forecast
          </button>
          <button
            className={`nav-tab ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => setActiveTab('dashboard')}
          >
            <LayoutDashboard size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} />
            Dashboard
          </button>
        </div>
      </header>

      <main className="app-body">
        <div style={{ display: activeTab === 'explore' ? 'block' : 'none' }}>
          <ExplorePanel />
        </div>
        <div style={{ display: activeTab === 'forecast' ? 'block' : 'none' }}>
          <ForecastWorkspace />
        </div>
        <div style={{ display: activeTab === 'dashboard' ? 'block' : 'none' }}>
          <Dashboard />
        </div>
      </main>
    </div>
  );
}

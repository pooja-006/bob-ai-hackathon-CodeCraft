import { useState, useEffect } from 'react'
import './App.css'
import { apiFetch } from './api'
import LotOverview from './tabs/LotOverview'
import RootCause   from './tabs/RootCause'
import RiskPredict from './tabs/RiskPredict'
import AskBob      from './tabs/AskBob'

const TABS = [
  { id: 'lots', label: 'Lot Overview' },
  { id: 'rca',  label: 'Root Cause Analysis' },
  { id: 'risk', label: 'Risk Prediction' },
  { id: 'bob',  label: 'Ask Bob' },
]

export default function App() {
  const [activeTab, setActiveTab]   = useState('lots')
  const [wxStatus,  setWxStatus]    = useState(null)
  const [lotItems,  setLotItems]    = useState([])   // shared for lot selectors

  useEffect(() => {
    apiFetch('/api/analysis/watsonx-status')
      .then(setWxStatus)
      .catch(() => {})
  }, [])

  const wxLive = wxStatus?.mode === 'live'

  return (
    <>
      <header className="app-header">
        <div className="logo">IBM <span>WaferSight</span></div>
        <div className="subtitle">Wafer Yield Root Cause &amp; Defect Pattern Analyser</div>
        <span className={`wx-badge ${wxLive ? 'live' : 'fallback'}`}>
          {wxStatus ? (wxLive ? 'watsonx.ai LIVE' : 'watsonx.ai OFFLINE') : 'watsonx.ai …'}
        </span>
      </header>

      <nav className="tab-bar">
        {TABS.map(t => (
          <button
            key={t.id}
            className={`tab-btn ${activeTab === t.id ? 'active' : ''}`}
            onClick={() => setActiveTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="main">
        {activeTab === 'lots' && <LotOverview onLotsLoaded={setLotItems} />}
        {activeTab === 'rca'  && <RootCause   lotItems={lotItems} />}
        {activeTab === 'risk' && <RiskPredict />}
        {activeTab === 'bob'  && <AskBob      lotItems={lotItems} />}
      </main>
    </>
  )
}

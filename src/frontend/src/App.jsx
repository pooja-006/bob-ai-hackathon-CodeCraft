import { useState, useEffect } from 'react'
import './App.css'
import { apiFetch } from './api'
import LotOverview from './tabs/LotOverview'
import RootCause   from './tabs/RootCause'
import RiskPredict from './tabs/RiskPredict'
import AskBob      from './tabs/AskBob'

// ── SVG Icons ────────────────────────────────────────────────
function IconGrid()   { return <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="2" y="2" width="7" height="7" rx="1.5"/><rect x="11" y="2" width="7" height="7" rx="1.5"/><rect x="2" y="11" width="7" height="7" rx="1.5"/><rect x="11" y="11" width="7" height="7" rx="1.5"/></svg> }
function IconSearch() { return <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="8.5" cy="8.5" r="5.5"/><line x1="12.5" y1="12.5" x2="17" y2="17"/></svg> }
function IconRisk()   { return <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M10 3L18 17H2L10 3z"/><line x1="10" y1="9" x2="10" y2="13"/><circle cx="10" cy="15.5" r=".8" fill="currentColor"/></svg> }
function IconBot()    { return <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="3" y="7" width="14" height="10" rx="2"/><circle cx="7.5" cy="12" r="1.2" fill="currentColor" stroke="none"/><circle cx="12.5" cy="12" r="1.2" fill="currentColor" stroke="none"/><path d="M10 7V4"/><circle cx="10" cy="3" r="1" fill="currentColor" stroke="none"/><line x1="6" y1="17" x2="6" y2="19"/><line x1="14" y1="17" x2="14" y2="19"/></svg> }
function IconWafer()  { return (
  <svg viewBox="0 0 20 20" fill="none" stroke="white" strokeWidth="1.5">
    <circle cx="10" cy="10" r="7"/>
    <circle cx="10" cy="10" r="4"/>
    <circle cx="10" cy="10" r="1.5" fill="white"/>
    <line x1="10" y1="3" x2="10" y2="5"/>
    <line x1="10" y1="15" x2="10" y2="17"/>
    <line x1="3" y1="10" x2="5" y2="10"/>
    <line x1="15" y1="10" x2="17" y2="10"/>
  </svg>
) }

const NAV = [
  { id: 'lots',   label: 'Lot Overview',         Icon: IconGrid   },
  { id: 'rca',    label: 'Root Cause Analysis',   Icon: IconSearch },
  { id: 'risk',   label: 'Risk Prediction',       Icon: IconRisk   },
  { id: 'bob',    label: 'Ask Bob',               Icon: IconBot    },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('lots')
  const [wxStatus,  setWxStatus]  = useState(null)
  const [lotItems,  setLotItems]  = useState([])

  useEffect(() => {
    apiFetch('/api/analysis/watsonx-status')
      .then(setWxStatus)
      .catch(() => {})
  }, [])

  const wxMode = wxStatus?.mode
  const wxLive = wxMode === 'live'

  const wxBadgeCls = wxStatus == null ? 'loading' : wxLive ? 'live' : 'fallback'
  const wxBadgeTxt = wxStatus == null
    ? 'Connecting…'
    : wxLive
      ? 'watsonx.ai LIVE'
      : 'watsonx.ai OFFLINE'

  return (
    <div className="shell">
      {/* ── Topbar ── */}
      <header className="topbar">
        <div className="topbar-logo">
          <div className="topbar-logo-mark"><IconWafer /></div>
          <span className="topbar-brand">IBM <span>WaferSight</span></span>
        </div>
        <span className="topbar-sub">Wafer Yield Root Cause &amp; Defect Pattern Analyser</span>
        <div className="topbar-spacer" />
        <span className={`wx-badge ${wxBadgeCls}`}>
          <span className="dot" />
          {wxBadgeTxt}
        </span>
      </header>

      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <div className="sidebar-section">Analytics</div>
        {NAV.map(({ id, label, Icon }) => (
          <button
            key={id}
            className={`nav-item ${activeTab === id ? 'active' : ''}`}
            onClick={() => setActiveTab(id)}
          >
            <span className="nav-icon"><Icon /></span>
            {label}
          </button>
        ))}
        <div className="sidebar-footer">
          WaferSight v1.0<br />
          <span style={{color:'var(--blue-60)',fontWeight:600}}>IBM Bob AI Hackathon</span>
        </div>
      </aside>

      {/* ── Main content ── */}
      <main className="content">
        {activeTab === 'lots' && <LotOverview onLotsLoaded={setLotItems} />}
        {activeTab === 'rca'  && <RootCause   lotItems={lotItems} />}
        {activeTab === 'risk' && <RiskPredict />}
        {activeTab === 'bob'  && <AskBob      lotItems={lotItems} />}
      </main>
    </div>
  )
}

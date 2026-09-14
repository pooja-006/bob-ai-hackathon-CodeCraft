import { useState } from 'react'
import { apiFetch, yieldClass } from '../api'

// ── Confidence bar ────────────────────────────────────────────
function ConfBar({ pct }) {
  const cls = pct >= 60 ? 'h' : pct >= 30 ? 'm' : ''
  return (
    <div className="conf-row">
      <div className="conf-track"><div className={`conf-fill ${cls}`} style={{width:`${pct}%`}}/></div>
      <span className="conf-pct">{pct.toFixed(0)}%</span>
    </div>
  )
}

// ── Evidence boxes ────────────────────────────────────────────
function EvidenceRow({ evidence }) {
  if (!evidence?.length) return null
  return (
    <div className="ev-row">
      {evidence.map((ev, i) => {
        if (ev.parameter) return (
          <div key={i} className="ev-box">
            <strong>{ev.parameter}</strong>
            <div style={{display:'flex',flexWrap:'wrap',gap:'4px 12px',marginTop:2}}>
              <span>Lot value: <b>{ev.lot_value?.toFixed(4) ?? '—'}</b></span>
              <span>Fleet mean: {ev.fleet_mean?.toFixed(4) ?? '—'}</span>
              <span>Deviation: <b style={{color: Math.abs(ev.deviation_sigma??0) > 2 ? 'var(--red-60)' : 'var(--orange-40)'}}>
                {ev.deviation_sigma != null ? `${ev.deviation_sigma > 0 ? '+' : ''}${ev.deviation_sigma.toFixed(2)}σ` : '—'}
              </b></span>
              <span>ρ = {ev.yield_correlation_rho?.toFixed(4) ?? '—'}</span>
            </div>
          </div>
        )
        if (ev.defect_type) return (
          <div key={i} className="ev-box defect">
            <strong>{ev.defect_type} defects</strong>
            <div style={{display:'flex',flexWrap:'wrap',gap:'4px 12px',marginTop:2}}>
              <span>Lot density: <b>{ev.lot_density?.toFixed(4) ?? '—'}/cm²</b></span>
              <span>Fleet mean: {ev.fleet_mean_density?.toFixed(4) ?? '—'}/cm²</span>
              <span>Deviation: <b style={{color:'var(--red-60)'}}>+{ev.deviation_sigma?.toFixed(2) ?? '—'}σ</b></span>
            </div>
          </div>
        )
        if (ev.tool_id) return (
          <div key={i} className="ev-box tool">
            <strong>{ev.tool_id}</strong>
            <div style={{display:'flex',flexWrap:'wrap',gap:'4px 12px',marginTop:2}}>
              <span>Mean yield: <b>{ev.mean_yield?.toFixed(1) ?? '—'}%</b></span>
              <span>Lots: {ev.lot_count ?? '?'}</span>
              <span>Z-score: <b>{ev.yield_z_score?.toFixed(2) ?? '—'}</b></span>
            </div>
          </div>
        )
        return null
      })}
    </div>
  )
}

// ── Root cause candidate card ─────────────────────────────────
function CandidateCard({ cand, rank }) {
  const [open, setOpen] = useState(rank === 0)
  const dotCls = rank === 0 ? 'r1' : rank === 1 ? 'r2' : 'r3'
  return (
    <div className="cand-card">
      <div className="cand-head" onClick={() => setOpen(o => !o)}>
        <div className={`rank-dot ${dotCls}`}>{rank + 1}</div>
        <h4>{cand.cause}</h4>
        <span className={`cat-tag ${cand.category}`}>{cand.category.replace(/_/g,' ')}</span>
        <ConfBar pct={cand.confidence_pct} />
        <span className={`cand-chevron ${open ? 'open' : ''}`}>▾</span>
      </div>
      {open && (
        <div className="cand-body">
          <p style={{marginBottom: cand.evidence?.length ? 8 : 0}}>{cand.summary}</p>
          <EvidenceRow evidence={cand.evidence} />
        </div>
      )}
    </div>
  )
}

// ── Corrective actions panel ──────────────────────────────────
function ActionsPanel({ actions, source }) {
  if (!actions?.length) return null
  const isWx = source?.startsWith('watsonx')
  return (
    <div className="card mt-16">
      <div className="card-header">
        <div style={{display:'flex',alignItems:'center',gap:8}}>
          <span className="card-title">Corrective Actions</span>
          <span className="badge">{actions.length}</span>
          <span className={`chip ${isWx ? 'watsonx' : 'fallback'}`}>
            {isWx ? 'IBM watsonx.ai' : 'Rule-based'}
          </span>
        </div>
      </div>
      <div className="actions-list">
        {actions.map((a, i) => (
          <div key={i} className={`action-item ${a.urgency}`}>
            <span className={`urgency-tag ${a.urgency}`}>{a.urgency}</span>
            <div className="action-body">
              <strong>{a.action}</strong>
              <small>{a.rationale}</small>
              <div className="action-owner">Owner: {a.owner}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── At-risk lots quick list ───────────────────────────────────
function AtRiskLots({ lotItems }) {
  const atRisk = lotItems.filter(l => l.low_yield_flag).slice(0, 8)
  if (atRisk.length === 0) return (
    <div className="alert info" style={{marginBottom:0}}>No low-yield lots in the current lot list. Load lots from Lot Overview first.</div>
  )
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Lot ID</th><th>Tool</th><th>Step</th><th>Yield</th></tr></thead>
        <tbody>
          {atRisk.map(l => (
            <tr key={l.lot_id} className="row-low">
              <td><span className="lot-id-cell">{l.lot_id}</span></td>
              <td style={{fontFamily:'var(--font-mono)',fontSize:12}}>{l.tool_id}</td>
              <td style={{color:'var(--gray-80)'}}>{l.process_step}</td>
              <td><span className={`pill ${yieldClass(l.yield_pct)}`}>{l.yield_pct.toFixed(1)}%</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Main ─────────────────────────────────────────────────────
export default function RootCause({ lotItems }) {
  const [lotId,    setLotId]    = useState('')
  const [result,   setResult]   = useState(null)
  const [actions,  setActions]  = useState(null)
  const [loading,  setLoading]  = useState(false)
  const [loadingA, setLoadingA] = useState(false)
  const [error,    setError]    = useState(null)

  async function analyse() {
    if (!lotId) return
    setLoading(true); setError(null); setResult(null); setActions(null)
    try {
      const data = await apiFetch('/api/analysis/root-cause', {
        method: 'POST', body: JSON.stringify({ lot_id: lotId })
      })
      setResult(data)
      setLoadingA(true)
      const act = await apiFetch('/api/analysis/corrective-actions', {
        method: 'POST', body: JSON.stringify({ lot_id: lotId })
      })
      setActions(act)
    } catch (e) { setError(e.message) }
    finally { setLoading(false); setLoadingA(false) }
  }

  const sourceMode = result?.source_mode ?? 'fallback'
  const isWx = sourceMode.startsWith('watsonx')

  return (
    <div>
      <div className="page-header">
        <h1>Root Cause Analysis</h1>
        <p>AI-powered pattern detection and root-cause ranking powered by IBM watsonx.ai Granite.</p>
      </div>

      {/* ── Selector ── */}
      <div className="card">
        <div className="card-title" style={{marginBottom:14}}>Select lot to analyse</div>
        <div style={{display:'flex',gap:12,alignItems:'flex-end',flexWrap:'wrap'}}>
          <div className="field" style={{flex:2,minWidth:200}}>
            <label>Wafer Lot</label>
            <select value={lotId} onChange={e => setLotId(e.target.value)}>
              <option value="">— Select a lot —</option>
              {lotItems.map(l => (
                <option key={l.lot_id} value={l.lot_id}>
                  {l.lot_id} ({l.yield_pct.toFixed(1)}%){l.low_yield_flag ? ' ⚠ LOW' : ''}
                </option>
              ))}
            </select>
          </div>
          <button className="btn btn-primary" disabled={!lotId || loading} onClick={analyse}>
            {loading ? <><span className="spinner"/>Analysing…</> : 'Run Analysis'}
          </button>
        </div>
        <p className="text-muted" style={{fontSize:12,marginTop:12}}>
          Lots marked ⚠ are flagged low-yield. The pattern detector correlates sensor readings and defect data;
          IBM watsonx.ai Granite generates the narrative.
        </p>
      </div>

      {/* ── At-risk lots ── */}
      {!result && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">At-Risk Lots</span>
            <span className="pill danger">{lotItems.filter(l => l.low_yield_flag).length} flagged</span>
          </div>
          <AtRiskLots lotItems={lotItems} />
        </div>
      )}

      {error && <div className="alert error"><strong>Error:</strong> {error}</div>}

      {result && (
        <>
          {/* Lot header */}
          <div className="card">
            <div className="lot-detail-header">
              <span className="lot-id">{result.lot_id}</span>
              <span className={`pill ${yieldClass(result.yield_pct)}`}>{result.yield_pct.toFixed(2)}%</span>
              {result.low_yield_flag && <span className="pill danger">LOW YIELD</span>}
              <span className="badge">⚡ {result.candidate_count} signal{result.candidate_count !== 1 ? 's' : ''} detected</span>
              <span className={`chip ${isWx ? 'watsonx' : 'fallback'}`}>
                {isWx ? 'IBM watsonx.ai Granite' : 'Offline analysis'}
              </span>
            </div>
          </div>

          {/* Narrative */}
          {result.narrative && (
            <div className="narrative-panel">
              <div className="narrative-label">AI Root-Cause Narrative</div>
              <div className="narrative-text">{result.narrative}</div>
              {result.recommended_next_step && (
                <div className="narrative-next">→ Recommended next step: {result.recommended_next_step}</div>
              )}
            </div>
          )}

          {/* Candidates */}
          {result.candidates?.length > 0 ? (
            <div style={{marginBottom:20}}>
              <div className="section-title">
                Root Cause Candidates
                <span className="badge" style={{marginLeft:8}}>{result.candidates.length}</span>
              </div>
              <div className="cand-list">
                {result.candidates.map((c, i) => <CandidateCard key={i} cand={c} rank={i} />)}
              </div>
            </div>
          ) : (
            <div className="alert info">No statistical anomalies detected for this lot.</div>
          )}

          {/* Loading actions */}
          {loadingA && (
            <div className="loading-row">
              <span className="spinner"/>Generating corrective actions via IBM watsonx.ai…
            </div>
          )}
          {actions && <ActionsPanel actions={actions.actions} source={actions.source} />}
        </>
      )}
    </div>
  )
}

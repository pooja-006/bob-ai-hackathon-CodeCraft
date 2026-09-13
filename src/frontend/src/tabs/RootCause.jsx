import { useState } from 'react'
import { apiFetch, yieldClass } from '../api'

function ConfBar({ pct }) {
  const cls = pct >= 60 ? 'h' : pct >= 30 ? 'm' : ''
  return (
    <div className="conf-row">
      <div className="conf-track"><div className={`conf-fill ${cls}`} style={{width:`${pct}%`}}/></div>
      <span className="conf-pct">{pct.toFixed(0)}%</span>
    </div>
  )
}

function EvidenceRow({ evidence }) {
  if (!evidence?.length) return null
  return (
    <div className="ev-row">
      {evidence.map((ev, i) => {
        if (ev.parameter) return (
          <div key={i} className="ev-box">
            <strong>{ev.parameter}</strong>
            Lot: <b>{ev.lot_value?.toFixed(4) ?? '—'}</b> &nbsp;|&nbsp;
            Fleet mean: {ev.fleet_mean?.toFixed(4) ?? '—'} &nbsp;|&nbsp;
            Dev: <b>{ev.deviation_sigma != null ? `${ev.deviation_sigma > 0 ? '+' : ''}${ev.deviation_sigma.toFixed(2)}σ` : '—'}</b>&nbsp;|&nbsp;
            ρ = {ev.yield_correlation_rho?.toFixed(4) ?? '—'}
          </div>
        )
        if (ev.defect_type) return (
          <div key={i} className="ev-box">
            <strong>{ev.defect_type} defects</strong>
            Lot density: <b>{ev.lot_density?.toFixed(4) ?? '—'}/cm²</b>&nbsp;|&nbsp;
            Fleet mean: {ev.fleet_mean_density?.toFixed(4) ?? '—'}/cm²&nbsp;|&nbsp;
            Dev: <b>+{ev.deviation_sigma?.toFixed(2) ?? '—'}σ</b>
          </div>
        )
        if (ev.tool_id) return (
          <div key={i} className="ev-box">
            <strong>{ev.tool_id}</strong>
            Mean yield: <b>{ev.mean_yield?.toFixed(1) ?? '—'}%</b> across {ev.lot_count ?? '?'} lots&nbsp;|&nbsp;
            Z-score: <b>{ev.yield_z_score?.toFixed(2) ?? '—'}</b>
          </div>
        )
        return null
      })}
    </div>
  )
}

function CandidateCard({ cand, rank }) {
  const [open, setOpen] = useState(rank === 0)
  return (
    <div className="cand-card">
      <div className="cand-head" onClick={() => setOpen(o => !o)}>
        <div className="rank-dot">{rank + 1}</div>
        <h4>{cand.cause}</h4>
        <span className={`cat-tag ${cand.category}`}>{cand.category.replace(/_/g,' ')}</span>
        <ConfBar pct={cand.confidence_pct} />
        <span style={{fontSize:18,color:'#525252',marginLeft:4}}>{open ? '▲' : '▼'}</span>
      </div>
      {open && (
        <div className="cand-body">
          <p className="text-muted">{cand.summary}</p>
          <EvidenceRow evidence={cand.evidence} />
        </div>
      )}
    </div>
  )
}

function ActionsList({ actions, source }) {
  if (!actions?.length) return null
  const isWx = source?.startsWith('watsonx')
  return (
    <div className="card mt-12">
      <div className="card-title">
        Corrective Actions
        <span style={{marginLeft:4,background:'#e0e0e0',color:'#525252',borderRadius:10,padding:'1px 8px',fontWeight:400,textTransform:'none',letterSpacing:0,fontSize:12}}>
          {actions.length}
        </span>
        <span className={`chip ${isWx ? 'watsonx' : 'fallback'}`} style={{marginLeft:4}}>
          {isWx ? 'IBM watsonx.ai' : 'Rule-based'}
        </span>
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
      // Fetch corrective actions for top candidate
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
      <div className="section-head"><h2>Root Cause Analysis</h2></div>

      <div className="card">
        <div className="form-row">
          <div className="field" style={{flex:2}}>
            <label>Select Lot to Analyse</label>
            <select value={lotId} onChange={e => setLotId(e.target.value)}>
              <option value="">— Select a lot —</option>
              {lotItems.map(l => (
                <option key={l.lot_id} value={l.lot_id}>
                  {l.lot_id} ({l.yield_pct.toFixed(1)}%){l.low_yield_flag ? ' ⚠' : ''}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{flex:'0 0 auto'}}>
            <label>&nbsp;</label>
            <button className="btn btn-primary" disabled={!lotId || loading} onClick={analyse}>
              {loading ? <><span className="spinner"/>&nbsp;Analysing…</> : 'Analyse'}
            </button>
          </div>
        </div>
        <p className="text-muted" style={{fontSize:12}}>
          Lots marked ⚠ are flagged as low-yield. The pattern detector correlates sensor readings
          and defect data; IBM watsonx.ai Granite generates the narrative explanation.
        </p>
      </div>

      {error && <div className="alert error"><strong>Error:</strong> {error}</div>}

      {result && (
        <>
          {/* Lot header */}
          <div className="card">
            <div style={{display:'flex',alignItems:'center',gap:12,flexWrap:'wrap'}}>
              <span style={{fontWeight:600,fontSize:15}}>Lot {result.lot_id}</span>
              <span className={`pill ${yieldClass(result.yield_pct)}`}>{result.yield_pct.toFixed(2)}%</span>
              {result.low_yield_flag && <span className="pill danger">LOW YIELD</span>}
              <span className="badge">&#9729; {result.candidate_count} signal{result.candidate_count !== 1 ? 's' : ''} detected</span>
              <span className={`chip ${isWx ? 'watsonx' : 'fallback'}`}>
                {isWx ? 'IBM watsonx.ai' : 'Offline analysis'}
              </span>
            </div>
          </div>

          {/* Narrative */}
          {result.narrative && (
            <div className="narrative">
              <strong>AI Analysis</strong>
              <div style={{marginTop:6}}>{result.narrative}</div>
              {result.recommended_next_step && (
                <div className="next">→ Recommended next step: {result.recommended_next_step}</div>
              )}
            </div>
          )}

          {/* Candidates */}
          {result.candidates?.length > 0 ? (
            <>
              <div className="card-title">
                Root Cause Candidates
                <span style={{background:'#e0e0e0',color:'#525252',borderRadius:10,padding:'1px 8px',fontWeight:400,textTransform:'none',letterSpacing:0,fontSize:12}}>
                  {result.candidates.length}
                </span>
              </div>
              <div className="cand-list">
                {result.candidates.map((c, i) => <CandidateCard key={i} cand={c} rank={i} />)}
              </div>
            </>
          ) : (
            <div className="alert info">No statistical anomalies detected for this lot.</div>
          )}

          {/* Corrective actions */}
          {loadingA && <div className="loading-row mt-12"><span className="spinner"/>&nbsp;Generating corrective actions…</div>}
          {actions && <ActionsList actions={actions.actions} source={actions.source} />}
        </>
      )}
    </div>
  )
}

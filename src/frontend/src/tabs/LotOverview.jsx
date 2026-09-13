import { useState, useEffect, useCallback } from 'react'
import { apiFetch, yieldClass } from '../api'

const PAGE_SIZE = 25

export default function LotOverview({ onLotsLoaded }) {
  const [fleet,   setFleet]   = useState(null)
  const [items,   setItems]   = useState([])
  const [total,   setTotal]   = useState(0)
  const [page,    setPage]    = useState(0)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  // Filters
  const [step,    setStep]    = useState('')
  const [tool,    setTool]    = useState('')
  const [low,     setLow]     = useState(false)
  const [sortBy,  setSortBy]  = useState('timestamp')

  // Load fleet summary once
  useEffect(() => {
    apiFetch('/api/analysis/fleet-summary').then(setFleet).catch(() => {})
  }, [])

  // Load lots whenever filters or page changes
  const loadLots = useCallback(async (pg = page) => {
    setLoading(true); setError(null)
    const p = new URLSearchParams({ limit: PAGE_SIZE, offset: pg * PAGE_SIZE, sort_by: sortBy, sort_dir: 'desc' })
    if (step) p.set('process_step', step)
    if (tool) p.set('tool_id', tool)
    if (low)  p.set('low_yield_only', 'true')
    try {
      const data = await apiFetch(`/api/lots?${p}`)
      setItems(data.items); setTotal(data.total)
      onLotsLoaded && onLotsLoaded(data.items)
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }, [step, tool, low, sortBy, page, onLotsLoaded])

  useEffect(() => { loadLots(page) }, [step, tool, low, sortBy]) // eslint-disable-line
  useEffect(() => { loadLots(page) }, [page])                     // eslint-disable-line

  const resetPage = () => setPage(0)

  return (
    <div>
      <div className="section-head"><h2>Wafer Lot Overview</h2></div>

      {/* Fleet summary */}
      <div className="card">
        <div className="card-title">Fleet Summary</div>
        <div className="fleet-grid">
          <div className="stat-box"><div className="val">{fleet?.total_lots ?? '—'}</div><div className="lbl">Total Lots</div></div>
          <div className="stat-box good"><div className="val">{fleet ? fleet.mean_yield_pct.toFixed(1) + '%' : '—'}</div><div className="lbl">Mean Yield</div></div>
          <div className="stat-box danger"><div className="val">{fleet?.low_yield_lots ?? '—'}</div><div className="lbl">Low-Yield Lots</div></div>
          <div className="stat-box">
            <div className="val" style={{fontSize:14,paddingTop:6}}>
              {fleet?.top_yield_correlated_params?.[0]
                ? `${fleet.top_yield_correlated_params[0].parameter} (ρ=${fleet.top_yield_correlated_params[0].spearman_rho.toFixed(3)})`
                : '—'}
            </div>
            <div className="lbl">Top Correlated Parameter</div>
          </div>
          <div className="stat-box">
            <div className="val" style={{fontSize:14,paddingTop:6}}>
              {fleet?.underperforming_tools?.[0]
                ? `${fleet.underperforming_tools[0].tool_id} (${fleet.underperforming_tools[0].mean_yield.toFixed(1)}%)`
                : 'None flagged'}
            </div>
            <div className="lbl">Underperforming Tool</div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="card">
        <div className="form-row">
          <div className="field">
            <label>Process Step</label>
            <select value={step} onChange={e => { setStep(e.target.value); resetPage() }}>
              <option value="">All steps</option>
              {['litho','etch','deposition','cmp','diffusion','implant'].map(s => <option key={s}>{s}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Tool</label>
            <select value={tool} onChange={e => { setTool(e.target.value); resetPage() }}>
              <option value="">All tools</option>
              {['ETCH-01','ETCH-02','ETCH-03','DEP-01','DEP-02','DEP-03','LIT-01','LIT-02','LIT-03','CMP-01','CMP-02','DIFF-01','DIFF-02','IMP-01','IMP-02'].map(t => <option key={t}>{t}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Sort By</label>
            <select value={sortBy} onChange={e => { setSortBy(e.target.value); resetPage() }}>
              <option value="timestamp">Date (newest)</option>
              <option value="yield_pct">Yield</option>
              <option value="lot_id">Lot ID</option>
            </select>
          </div>
          <div className="field" style={{flex:'0 0 auto', justifyContent:'flex-end'}}>
            <label>&nbsp;</label>
            <label style={{display:'flex',alignItems:'center',gap:6,padding:'9px 0',cursor:'pointer',whiteSpace:'nowrap'}}>
              <input type="checkbox" checked={low} onChange={e => { setLow(e.target.checked); resetPage() }} />
              Low yield only
            </label>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="card">
        {error && <div className="alert error"><strong>Error:</strong> {error}</div>}
        {loading ? (
          <div className="loading-row"><span className="spinner"/>&nbsp;Loading lots…</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Lot ID</th><th>Node</th><th>Step</th><th>Tool</th><th>Recipe</th><th>Yield</th><th>Status</th></tr>
              </thead>
              <tbody>
                {items.length === 0 && (
                  <tr><td colSpan={7} className="text-muted" style={{padding:16}}>No lots match the current filters.</td></tr>
                )}
                {items.map(lot => (
                  <tr key={lot.lot_id} className={lot.low_yield_flag ? 'row-low' : ''}>
                    <td><code>{lot.lot_id}</code></td>
                    <td>{lot.node}</td>
                    <td>{lot.process_step}</td>
                    <td>{lot.tool_id}</td>
                    <td>{lot.recipe_id}</td>
                    <td><span className={`pill ${yieldClass(lot.yield_pct)}`}>{lot.yield_pct.toFixed(2)}%</span></td>
                    <td>{lot.low_yield_flag
                      ? <span className="pill danger">LOW YIELD</span>
                      : <span className="pill good">OK</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="pagination">
          <button className="btn btn-secondary btn-sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>&#8592; Prev</button>
          <span className="page-info">
            {total > 0 ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, total)} of ${total}` : ''}
          </span>
          <button className="btn btn-secondary btn-sm" disabled={(page + 1) * PAGE_SIZE >= total} onClick={() => setPage(p => p + 1)}>Next &#8594;</button>
        </div>
      </div>
    </div>
  )
}

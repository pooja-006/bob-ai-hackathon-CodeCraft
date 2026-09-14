import { useState, useEffect, useCallback, useRef } from 'react'
import { apiFetch, yieldClass } from '../api'

const PAGE_SIZE = 25

// ── Pure-SVG yield sparkline ─────────────────────────────────────────────────
function YieldSparkline({ items }) {
  const svgRef = useRef(null)
  const [tooltip, setTooltip] = useState(null)

  if (!items || items.length < 2) return null

  const W = 560; const H = 120; const PAD = { t: 12, r: 12, b: 28, l: 42 }
  const plotW = W - PAD.l - PAD.r
  const plotH = H - PAD.t - PAD.b

  // Use up to 60 most-recent lots (already sorted desc by the API, reverse for chart)
  const pts = [...items].reverse().slice(-60)
  const vals = pts.map(p => p.yield_pct)
  const minV = Math.max(0, Math.min(...vals) - 5)
  const maxV = Math.min(100, Math.max(...vals) + 5)

  const x = i => PAD.l + (i / (pts.length - 1)) * plotW
  const y = v => PAD.t + plotH - ((v - minV) / (maxV - minV)) * plotH

  // Y grid lines
  const gridY = [60, 70, 80, 90, 100].filter(v => v >= minV && v <= maxV)

  // Path
  const linePath = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(p.yield_pct).toFixed(1)}`).join(' ')
  const areaPath = linePath + ` L${x(pts.length-1).toFixed(1)},${(PAD.t+plotH).toFixed(1)} L${PAD.l.toFixed(1)},${(PAD.t+plotH).toFixed(1)} Z`

  return (
    <div className="chart-wrap" style={{position:'relative'}}>
      <svg viewBox={`0 0 ${W} ${H}`} ref={svgRef} style={{overflow:'visible'}}>
        <defs>
          <linearGradient id="yieldGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor="#0f62fe" stopOpacity=".18"/>
            <stop offset="100%" stopColor="#0f62fe" stopOpacity="0"/>
          </linearGradient>
        </defs>

        {/* Grid */}
        {gridY.map(v => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} stroke="#e0e0e0" strokeDasharray="3 3" strokeWidth=".8"/>
            <text x={PAD.l - 6} y={y(v) + 4} textAnchor="end" fontSize="10" fill="#8d8d8d">{v}%</text>
          </g>
        ))}

        {/* 82% low-yield threshold */}
        {82 >= minV && 82 <= maxV && (
          <line x1={PAD.l} x2={W - PAD.r} y1={y(82)} y2={y(82)}
            stroke="#da1e28" strokeDasharray="5 3" strokeWidth="1" opacity=".7"/>
        )}

        {/* Area fill */}
        <path d={areaPath} fill="url(#yieldGrad)"/>

        {/* Line */}
        <path d={linePath} fill="none" stroke="#0f62fe" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round"/>

        {/* Dots for low-yield */}
        {pts.map((p, i) => p.low_yield_flag ? (
          <circle key={i} cx={x(i)} cy={y(p.yield_pct)} r="3.5" fill="#da1e28" stroke="white" strokeWidth="1.2"/>
        ) : null)}

        {/* Hover targets */}
        {pts.map((p, i) => (
          <rect key={i}
            x={x(i) - (plotW / pts.length / 2)} y={PAD.t}
            width={plotW / pts.length} height={plotH}
            fill="transparent"
            onMouseEnter={e => setTooltip({ x: e.clientX + 10, y: e.clientY - 28, lot: p })}
            onMouseLeave={() => setTooltip(null)}
          />
        ))}

        {/* X axis labels (sparse) */}
        {pts.filter((_, i) => i % Math.ceil(pts.length / 6) === 0).map((p) => {
          const i = pts.indexOf(p)
          return (
            <text key={i} x={x(i)} y={H - 4} textAnchor="middle" fontSize="9.5" fill="#8d8d8d">
              {p.lot_id?.slice(-4)}
            </text>
          )
        })}
      </svg>

      {/* Legend */}
      <div style={{display:'flex',gap:16,marginTop:6,fontSize:11,color:'#8d8d8d'}}>
        <span style={{display:'flex',alignItems:'center',gap:4}}>
          <svg width="20" height="3"><line x1="0" y1="1.5" x2="20" y2="1.5" stroke="#0f62fe" strokeWidth="1.8"/></svg>
          Yield %
        </span>
        <span style={{display:'flex',alignItems:'center',gap:4}}>
          <svg width="20" height="3"><line x1="0" y1="1.5" x2="20" y2="1.5" stroke="#da1e28" strokeWidth="1" strokeDasharray="5 3"/></svg>
          82% low-yield threshold
        </span>
        <span style={{display:'flex',alignItems:'center',gap:4}}>
          <svg width="10" height="10"><circle cx="5" cy="5" r="4" fill="#da1e28"/></svg>
          Low-yield lot
        </span>
      </div>

      {tooltip && (
        <div className="chart-tooltip" style={{left: tooltip.x, top: tooltip.y}}>
          <strong>{tooltip.lot.lot_id}</strong> — {tooltip.lot.yield_pct.toFixed(2)}%
          {tooltip.lot.low_yield_flag ? ' ⚠ LOW' : ''}
        </div>
      )}
    </div>
  )
}

// ── Defect/risk distribution bars ───────────────────────────────────────────
function RiskDistribution({ items }) {
  if (!items || items.length === 0) return null
  const total = items.length
  const high   = items.filter(i => i.yield_pct < 75).length
  const medium = items.filter(i => i.yield_pct >= 75 && i.yield_pct < 82).length
  const low    = items.filter(i => i.yield_pct >= 82).length

  const row = (label, count, cls) => (
    <div className="risk-dist-row" key={label}>
      <span className="risk-dist-label" style={{color: cls === 'HIGH' ? 'var(--red-60)' : cls === 'MEDIUM' ? 'var(--orange-40)' : 'var(--green-60)'}}>{label}</span>
      <div className="risk-dist-track">
        <div className={`risk-dist-fill ${cls}`} style={{width: `${Math.round((count/total)*100)}%`}}/>
      </div>
      <span className="risk-dist-count">{count}</span>
      <span style={{fontSize:11,color:'var(--gray-50)',minWidth:36}}>{Math.round((count/total)*100)}%</span>
    </div>
  )

  return (
    <div>
      {row('HIGH',   high,   'HIGH')}
      {row('MEDIUM', medium, 'MEDIUM')}
      {row('LOW',    low,    'LOW')}
    </div>
  )
}

// ── Equipment sensor heatmap (simplified — top tools) ────────────────────────
function ToolTable({ items }) {
  if (!items || items.length === 0) return null
  const toolMap = {}
  items.forEach(l => {
    if (!toolMap[l.tool_id]) toolMap[l.tool_id] = { yields: [], count: 0, low: 0 }
    toolMap[l.tool_id].yields.push(l.yield_pct)
    toolMap[l.tool_id].count++
    if (l.low_yield_flag) toolMap[l.tool_id].low++
  })
  const tools = Object.entries(toolMap).map(([id, d]) => ({
    id,
    mean: d.yields.reduce((a, b) => a + b, 0) / d.yields.length,
    count: d.count,
    low: d.low,
    lowPct: Math.round((d.low / d.count) * 100),
  })).sort((a, b) => a.mean - b.mean).slice(0, 8)

  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Tool</th><th>Lots</th><th>Mean Yield</th><th>Low-Yield Lots</th><th>Low-Yield Rate</th></tr></thead>
        <tbody>
          {tools.map(t => (
            <tr key={t.id} className={t.lowPct > 30 ? 'row-low' : ''}>
              <td><span className="lot-id-cell">{t.id}</span></td>
              <td style={{color:'var(--gray-70)'}}>{t.count}</td>
              <td><span className={`pill ${yieldClass(t.mean)}`}>{t.mean.toFixed(1)}%</span></td>
              <td style={{color: t.low > 0 ? 'var(--red-60)' : 'var(--green-60)', fontWeight: 600}}>{t.low}</td>
              <td>
                <div style={{display:'flex',alignItems:'center',gap:8}}>
                  <div style={{flex:1,height:6,background:'var(--gray-10)',borderRadius:3,minWidth:60}}>
                    <div style={{height:'100%',borderRadius:3,width:`${t.lowPct}%`,background: t.lowPct > 30 ? 'var(--red-60)' : t.lowPct > 15 ? 'var(--orange-40)' : 'var(--green-60)'}}/>
                  </div>
                  <span style={{fontSize:12,color:'var(--gray-70)',minWidth:28,fontWeight:600}}>{t.lowPct}%</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Main component ───────────────────────────────────────────────────────────
export default function LotOverview({ onLotsLoaded }) {
  const [fleet,   setFleet]   = useState(null)
  const [items,   setItems]   = useState([])
  const [total,   setTotal]   = useState(0)
  const [page,    setPage]    = useState(0)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  // Filters
  const [step,   setStep]   = useState('')
  const [tool,   setTool]   = useState('')
  const [low,    setLow]    = useState(false)
  const [sortBy, setSortBy] = useState('timestamp')

  useEffect(() => {
    apiFetch('/api/analysis/fleet-summary').then(setFleet).catch(() => {})
  }, [])

  const loadLots = useCallback(async (pg = page) => {
    setLoading(true); setError(null)
    const p = new URLSearchParams({ limit: PAGE_SIZE, offset: pg * PAGE_SIZE, sort_by: sortBy, sort_dir: 'desc' })
    if (step) p.set('process_step', step)
    if (tool) p.set('tool_id', tool)
    if (low)  p.set('low_yield_only', 'true')
    try {
      const data = await apiFetch(`/api/lots?${p}`)
      setItems(data.items); setTotal(data.total)
      if (onLotsLoaded) onLotsLoaded(data.items)
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }, [step, tool, low, sortBy, page, onLotsLoaded])

  useEffect(() => { loadLots(0); setPage(0) }, [step, tool, low, sortBy]) // eslint-disable-line
  useEffect(() => { loadLots(page) }, [page])                              // eslint-disable-line

  const topParam = fleet?.top_yield_correlated_params?.[0]
  const topTool  = fleet?.underperforming_tools?.[0]

  return (
    <div>
      <div className="page-header">
        <h1>Lot Overview</h1>
        <p>Fleet-level yield analytics across all wafer lots, tools, and process steps.</p>
      </div>

      {/* ── KPI cards ── */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">Total Lots</div>
          <div className="kpi-value">{fleet?.total_lots ?? '—'}</div>
          <div className="kpi-sub">in dataset</div>
        </div>
        <div className="kpi-card good">
          <div className="kpi-label">Mean Yield</div>
          <div className="kpi-value good">{fleet ? fleet.mean_yield_pct.toFixed(1) + '%' : '—'}</div>
          <div className="kpi-sub">fleet average</div>
        </div>
        <div className="kpi-card danger">
          <div className="kpi-label">Low-Yield Lots</div>
          <div className="kpi-value danger">{fleet?.low_yield_lots ?? '—'}</div>
          <div className="kpi-sub">below 82% threshold</div>
        </div>
        <div className="kpi-card warn">
          <div className="kpi-label">Top Risk Parameter</div>
          <div className="kpi-value" style={{fontSize:17,marginTop:2}}>
            {topParam ? topParam.parameter : '—'}
          </div>
          <div className="kpi-sub">
            {topParam ? `ρ = ${topParam.spearman_rho.toFixed(3)} yield correlation` : 'loading…'}
          </div>
        </div>
        <div className="kpi-card purple">
          <div className="kpi-label">Underperforming Tool</div>
          <div className="kpi-value" style={{fontSize:17,marginTop:2}}>
            {topTool ? topTool.tool_id : '—'}
          </div>
          <div className="kpi-sub">
            {topTool ? `${topTool.mean_yield.toFixed(1)}% mean yield` : 'loading…'}
          </div>
        </div>
      </div>

      {/* ── Two-column charts row ── */}
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:20,marginBottom:20}}>
        {/* Yield trend */}
        <div className="card" style={{marginBottom:0}}>
          <div className="card-header">
            <span className="card-title">Yield Trend (last {Math.min(items.length, 60)} lots)</span>
          </div>
          {loading
            ? <div className="loading-row"><span className="spinner"/>Loading chart…</div>
            : <YieldSparkline items={items} />
          }
        </div>

        {/* Risk distribution */}
        <div className="card" style={{marginBottom:0}}>
          <div className="card-header">
            <span className="card-title">Yield Risk Distribution</span>
            <span className="badge">{total} lots</span>
          </div>
          {loading
            ? <div className="loading-row"><span className="spinner"/>Loading…</div>
            : <>
                <RiskDistribution items={items} />
                <div className="divider"/>
                <div style={{fontSize:12,color:'var(--gray-70)',lineHeight:1.6}}>
                  <span style={{color:'var(--red-60)',fontWeight:600}}>HIGH</span> = yield &lt; 75% &nbsp;·&nbsp;
                  <span style={{color:'var(--orange-40)',fontWeight:600}}>MEDIUM</span> = 75–82% &nbsp;·&nbsp;
                  <span style={{color:'var(--green-60)',fontWeight:600}}>LOW</span> = ≥ 82%
                </div>
              </>
          }
        </div>
      </div>

      {/* ── Equipment performance table ── */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Equipment Performance (top 8 by low-yield rate)</span>
        </div>
        {loading
          ? <div className="loading-row"><span className="spinner"/>Loading…</div>
          : <ToolTable items={items} />
        }
      </div>

      {/* ── Filters ── */}
      <div className="card">
        <div className="card-title" style={{marginBottom:14}}>Filter &amp; Sort Lots</div>
        <div className="form-grid" style={{gridTemplateColumns:'repeat(auto-fit,minmax(140px,1fr))'}}>
          <div className="field">
            <label>Process Step</label>
            <select value={step} onChange={e => { setStep(e.target.value); setPage(0) }}>
              <option value="">All steps</option>
              {['litho','etch','deposition','cmp','diffusion','implant'].map(s => <option key={s}>{s}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Tool</label>
            <select value={tool} onChange={e => { setTool(e.target.value); setPage(0) }}>
              <option value="">All tools</option>
              {['ETCH-01','ETCH-02','ETCH-03','DEP-01','DEP-02','DEP-03','LIT-01','LIT-02','LIT-03','CMP-01','CMP-02','DIFF-01','DIFF-02','IMP-01','IMP-02'].map(t => <option key={t}>{t}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Sort By</label>
            <select value={sortBy} onChange={e => { setSortBy(e.target.value); setPage(0) }}>
              <option value="timestamp">Date (newest)</option>
              <option value="yield_pct">Yield</option>
              <option value="lot_id">Lot ID</option>
            </select>
          </div>
          <div className="field" style={{justifyContent:'flex-end'}}>
            <label>&nbsp;</label>
            <label className="field-checkbox">
              <input type="checkbox" checked={low} onChange={e => { setLow(e.target.checked); setPage(0) }} />
              Low-yield only
            </label>
          </div>
        </div>
      </div>

      {/* ── Lots table ── */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            Wafer Lots
            {total > 0 && <span className="badge" style={{marginLeft:8}}>{total}</span>}
          </span>
          {low && <span className="pill danger">Filtered: low-yield only</span>}
        </div>
        {error && <div className="alert error"><strong>Error:</strong> {error}</div>}
        {loading ? (
          <div className="loading-row"><span className="spinner"/>Loading lots…</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Lot ID</th><th>Node</th><th>Step</th><th>Tool</th>
                  <th>Recipe</th><th>Yield</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 && (
                  <tr><td colSpan={7} className="text-muted" style={{padding:20,textAlign:'center'}}>
                    No lots match the current filters.
                  </td></tr>
                )}
                {items.map(lot => (
                  <tr key={lot.lot_id} className={lot.low_yield_flag ? 'row-low' : ''}>
                    <td><span className="lot-id-cell">{lot.lot_id}</span></td>
                    <td><span className="pill neutral">{lot.node}</span></td>
                    <td style={{color:'var(--gray-80)'}}>{lot.process_step}</td>
                    <td style={{fontFamily:'var(--font-mono)',fontSize:12}}>{lot.tool_id}</td>
                    <td style={{color:'var(--gray-70)',fontSize:12}}>{lot.recipe_id}</td>
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
          <button className="btn btn-ghost btn-sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Prev</button>
          <span className="page-info">
            {total > 0 ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, total)} of ${total}` : ''}
          </span>
          <button className="btn btn-ghost btn-sm" disabled={(page + 1) * PAGE_SIZE >= total} onClick={() => setPage(p => p + 1)}>Next →</button>
        </div>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { apiFetch } from '../api'

const TOOLS = [
  'ETCH-01','ETCH-02','ETCH-03',
  'DEP-01','DEP-02','DEP-03',
  'LIT-01','LIT-02','LIT-03',
  'CMP-01','CMP-02',
  'DIFF-01','DIFF-02',
  'IMP-01','IMP-02',
]
const RECIPES = [
  'R-ETH-04','R-ETH-05','R-ETH-06',
  'R-DEP-01','R-NIT-07','R-OXI-02',
  'R-LIT-01','R-LIT-02','R-LIT-03',
  'R-CMP-01','R-CMP-02',
  'R-DIF-01','R-DIF-02',
  'R-IMP-01','R-IMP-02',
]

const INTERP = {
  HIGH:   'High probability of low yield. Immediate review recommended before scheduling this lot.',
  MEDIUM: 'Moderate risk detected. Monitor key parameters closely and consider a qualification run.',
  LOW:    'Low yield risk. Lot may proceed with standard monitoring protocols.',
}

// ── Risk gauge SVG ────────────────────────────────────────────
function RiskGauge({ pct, label }) {
  // Semi-circle gauge: 0% = left, 100% = right
  const r = 54
  const cx = 70; const cy = 68
  const angle = Math.PI - (pct / 100) * Math.PI
  const needleX = cx + r * Math.cos(angle)
  const needleY = cy - r * Math.sin(angle)

  const arcPath = (startDeg, endDeg, radius, color) => {
    const s = Math.PI - (startDeg / 100) * Math.PI
    const e = Math.PI - (endDeg / 100) * Math.PI
    const x1 = cx + radius * Math.cos(s); const y1 = cy - radius * Math.sin(s)
    const x2 = cx + radius * Math.cos(e); const y2 = cy - radius * Math.sin(e)
    const large = Math.abs(endDeg - startDeg) > 50 ? 1 : 0
    return <path d={`M${x1} ${y1} A${radius} ${radius} 0 ${large} 0 ${x2} ${y2}`} fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"/>
  }

  const scoreColor = label === 'HIGH' ? '#da1e28' : label === 'MEDIUM' ? '#ff832b' : '#198038'

  return (
    <svg viewBox="0 0 140 80" style={{width:'100%',maxWidth:180}}>
      {/* Background arc */}
      {arcPath(0, 100, r, '#e0e0e0')}
      {/* Colored zones */}
      {arcPath(0,  35,  r, '#defbe6')}
      {arcPath(35, 65,  r, '#fff2e8')}
      {arcPath(65, 100, r, '#fff1f1')}
      {/* Score fill */}
      {arcPath(0, pct, r - 2, scoreColor)}
      {/* Needle */}
      <line x1={cx} y1={cy} x2={needleX} y2={needleY} stroke={scoreColor} strokeWidth="2.5" strokeLinecap="round"/>
      <circle cx={cx} cy={cy} r="4" fill={scoreColor}/>
      {/* Score label */}
      <text x={cx} y={cy - 14} textAnchor="middle" fontSize="19" fontWeight="800" fill={scoreColor}>{pct.toFixed(0)}%</text>
      {/* Zone labels */}
      <text x="10" y="78" fontSize="8" fill="#198038">LOW</text>
      <text x={cx - 10} y="78" fontSize="8" fill="#ff832b">MED</text>
      <text x="108" y="78" fontSize="8" fill="#da1e28">HIGH</text>
    </svg>
  )
}

// ── Sensor quick-ref bar ──────────────────────────────────────
const SENSOR_PRESETS = [
  { label: 'ETCH-03 hot run (high risk)',  etchTemp: 191, rfPower: '', defDens: '' },
  { label: 'DEP-02 RF spike',             etchTemp: '',  rfPower: 435, defDens: '' },
  { label: 'High particle contamination', etchTemp: '',  rfPower: '',  defDens: 0.38 },
  { label: 'Normal conditions',           etchTemp: 174, rfPower: 375, defDens: 0.05 },
]

export default function RiskPredict() {
  const [node,     setNode]     = useState('3nm')
  const [step,     setStep]     = useState('etch')
  const [tool,     setTool]     = useState('ETCH-01')
  const [recipe,   setRecipe]   = useState('R-ETH-04')
  const [etchTemp, setEtchTemp] = useState('')
  const [rfPower,  setRfPower]  = useState('')
  const [defDens,  setDefDens]  = useState('')
  const [result,   setResult]   = useState(null)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState(null)

  async function predict() {
    setLoading(true); setError(null)
    const body = { node, process_step: step, tool_id: tool, recipe_id: recipe }
    if (etchTemp !== '') body.sensor_etch_temp_c  = parseFloat(etchTemp)
    if (rfPower  !== '') body.sensor_rf_power_w   = parseFloat(rfPower)
    if (defDens  !== '') body.defect_density_mean = parseFloat(defDens)
    try {
      const data = await apiFetch('/api/analysis/risk-prediction', {
        method: 'POST', body: JSON.stringify(body)
      })
      setResult(data)
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }

  function applyPreset(p) {
    if (p.etchTemp !== '') setEtchTemp(String(p.etchTemp)); else setEtchTemp('')
    if (p.rfPower  !== '') setRfPower(String(p.rfPower));   else setRfPower('')
    if (p.defDens  !== '') setDefDens(String(p.defDens));   else setDefDens('')
  }

  const label   = result?.risk_label ?? 'LOW'
  const score   = result ? result.risk_score * 100 : 0
  const factors = result?.top_risk_factors ?? []
  const maxImp  = factors.length ? Math.max(...factors.map(f => f.importance), 0.001) : 0.001

  return (
    <div>
      <div className="page-header">
        <h1>Batch Risk Prediction</h1>
        <p>Random Forest model trained on 500 historical lots — enter upcoming lot parameters to forecast yield risk.</p>
      </div>

      {/* ── Quick presets ── */}
      <div className="card">
        <div className="card-title" style={{marginBottom:10}}>Quick test scenarios</div>
        <div style={{display:'flex',flexWrap:'wrap',gap:8}}>
          {SENSOR_PRESETS.map((p, i) => (
            <button key={i} className="example-chip" onClick={() => applyPreset(p)}>{p.label}</button>
          ))}
        </div>
      </div>

      {/* ── Form ── */}
      <div className="card">
        <div className="card-title" style={{marginBottom:14}}>Lot configuration</div>
        <div className="form-grid">
          <div className="field">
            <label>Node</label>
            <select value={node} onChange={e => setNode(e.target.value)}>
              <option>3nm</option><option>5nm</option>
            </select>
          </div>
          <div className="field">
            <label>Process Step</label>
            <select value={step} onChange={e => setStep(e.target.value)}>
              {['etch','litho','deposition','cmp','diffusion','implant'].map(s => <option key={s}>{s}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Tool</label>
            <select value={tool} onChange={e => setTool(e.target.value)}>
              {TOOLS.map(t => <option key={t}>{t}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Recipe</label>
            <select value={recipe} onChange={e => setRecipe(e.target.value)}>
              {RECIPES.map(r => <option key={r}>{r}</option>)}
            </select>
          </div>
        </div>

        <div className="divider"/>
        <div className="card-title" style={{marginBottom:14}}>Sensor overrides <span style={{fontSize:11,fontWeight:400,textTransform:'none',letterSpacing:0}}>(optional — leave blank to use fleet averages)</span></div>
        <div className="form-grid">
          <div className="field">
            <label>Etch Temp (°C)</label>
            <input type="number" placeholder="e.g. 188" value={etchTemp} onChange={e => setEtchTemp(e.target.value)} step="0.1" min="150" max="210" />
          </div>
          <div className="field">
            <label>RF Power (W)</label>
            <input type="number" placeholder="e.g. 425" value={rfPower} onChange={e => setRfPower(e.target.value)} step="1" min="300" max="500" />
          </div>
          <div className="field">
            <label>Mean Defect Density (/cm²)</label>
            <input type="number" placeholder="e.g. 0.25" value={defDens} onChange={e => setDefDens(e.target.value)} step="0.01" min="0" max="1" />
          </div>
        </div>

        <div style={{display:'flex',alignItems:'center',gap:16,marginTop:4}}>
          <button className="btn btn-primary" disabled={loading} onClick={predict}>
            {loading ? <><span className="spinner"/>Predicting…</> : 'Predict Risk'}
          </button>
          <span className="text-muted" style={{fontSize:12}}>Try: ETCH-03 + etch temp 191°C for a high-risk example</span>
        </div>
      </div>

      {error && <div className="alert error"><strong>Error:</strong> {error}</div>}

      {result && (
        <div className="card">
          <div className="card-title" style={{marginBottom:16}}>Prediction result</div>
          <div className="risk-layout">
            {/* Gauge */}
            <div className={`risk-score-card ${label}`}>
              <RiskGauge pct={score} label={label} />
              <span className="risk-label">{label} RISK</span>
              <div className="risk-sub">probability of low yield</div>
            </div>

            {/* Factors */}
            {factors.length > 0 && (
              <div className="factor-list">
                <div className="card-title" style={{marginBottom:12}}>Top contributing factors</div>
                {factors.slice(0, 8).map((f, i) => {
                  const barPct = Math.round((f.importance / maxImp) * 100)
                  const dir = f.direction === 'high' ? '↑ ' : f.direction === 'low' ? '↓ ' : ''
                  return (
                    <div key={i} className="factor-row">
                      <div className="factor-name" title={f.feature}>{dir}{f.feature.replace('sensor_','')}</div>
                      <div className="factor-track"><div className="factor-fill" style={{width:`${barPct}%`}}/></div>
                      <div className="factor-pct">{(f.importance * 100).toFixed(1)}%</div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <div className={`alert ${label === 'HIGH' ? 'error' : label === 'MEDIUM' ? 'warn' : 'success'}`}>
            <strong>{label}:</strong> {INTERP[label]}
          </div>
        </div>
      )}
    </div>
  )
}

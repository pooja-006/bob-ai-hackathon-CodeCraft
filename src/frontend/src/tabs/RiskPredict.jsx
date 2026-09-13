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

  const label   = result?.risk_label ?? 'LOW'
  const score   = result ? (result.risk_score * 100).toFixed(1) : null
  const factors = result?.top_risk_factors ?? []
  const maxImp  = factors.length ? Math.max(...factors.map(f => f.importance), 0.001) : 0.001

  return (
    <div>
      <div className="section-head"><h2>Batch Risk Prediction</h2></div>

      <div className="card">
        <div className="card-title">Upcoming Lot Parameters</div>
        <p className="text-muted" style={{fontSize:12,marginBottom:16}}>
          Enter the planned configuration for an upcoming lot. The Random Forest model (trained on 500 historical lots) returns
          a low-yield probability and the top contributing risk factors.
        </p>

        <div className="form-row">
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

        <div className="card-title" style={{marginTop:4}}>Optional Sensor Overrides</div>
        <div className="form-row">
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

        <div className="form-row" style={{marginBottom:0}}>
          <button className="btn btn-primary" disabled={loading} onClick={predict}>
            {loading ? <><span className="spinner"/>&nbsp;Predicting…</> : 'Predict Risk'}
          </button>
          <p className="text-muted" style={{fontSize:12,alignSelf:'center'}}>
            Try: ETCH-03 + etch temp 191°C for a high-risk example
          </p>
        </div>
      </div>

      {error && <div className="alert error"><strong>Error:</strong> {error}</div>}

      {result && (
        <div className="card">
          <div className="risk-layout">
            <div className={`risk-score-card ${label}`}>
              <div className="big">{score}%</div>
              <span className="risk-label">{label} RISK</span>
              <div className="risk-sub">probability of low yield</div>
            </div>

            {factors.length > 0 && (
              <div className="factor-list">
                <div className="card-title" style={{marginBottom:10}}>Top Contributing Factors</div>
                {factors.slice(0, 8).map((f, i) => {
                  const barPct = Math.round((f.importance / maxImp) * 100)
                  const dir = f.direction === 'high' ? '↑' : f.direction === 'low' ? '↓' : ''
                  return (
                    <div key={i} className="factor-row">
                      <div className="factor-name" title={f.feature}>{dir} {f.feature.replace('sensor_','')}</div>
                      <div className="factor-track"><div className="factor-fill" style={{width:`${barPct}%`}}/></div>
                      <div className="factor-pct">{(f.importance * 100).toFixed(1)}%</div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <div className={`alert ${label === 'HIGH' ? 'error' : label === 'MEDIUM' ? 'warn' : 'info'}`}>
            <strong>{label}:</strong> {INTERP[label]}
          </div>
        </div>
      )}
    </div>
  )
}

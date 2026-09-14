import { useState, useRef } from 'react'
import { apiFetch } from '../api'

const EXAMPLES = [
  'What is the most likely cause of yield loss on this lot?',
  'Which tool should I inspect first?',
  'What corrective actions do you recommend for elevated etch temperature?',
  'Is there a process drift trend I should be concerned about?',
  'Summarise the defect profile for this lot.',
]

export default function AskBob({ lotItems }) {
  const [query,   setQuery]   = useState('')
  const [lotId,   setLotId]   = useState('')
  const [result,  setResult]  = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)
  const textRef = useRef(null)

  async function ask() {
    const q = query.trim()
    if (!q) return
    setLoading(true); setError(null); setResult(null)
    const body = { query: q }
    if (lotId) body.lot_id = lotId
    try {
      const data = await apiFetch('/api/analysis/chat', {
        method: 'POST', body: JSON.stringify(body)
      })
      setResult(data)
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }

  function handleKey(e) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) ask()
  }

  const isWx = result?.source_mode?.startsWith('watsonx')

  return (
    <div>
      <div className="page-header">
        <h1>Ask Bob</h1>
        <p>Conversational yield-engineering assistant powered by IBM watsonx.ai Granite.</p>
      </div>

      {/* ── Bob panel ── */}
      <div className="card">
        {/* Header */}
        <div className="bob-header">
          <div className="bob-avatar">
            <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="1.6" width="22" height="22">
              <rect x="3" y="8" width="18" height="12" rx="2.5"/>
              <circle cx="8.5" cy="14" r="1.5" fill="white" stroke="none"/>
              <circle cx="15.5" cy="14" r="1.5" fill="white" stroke="none"/>
              <path d="M12 8V5"/>
              <circle cx="12" cy="3.5" r="1.5" fill="white" stroke="none"/>
              <line x1="7" y1="20" x2="7" y2="22" strokeWidth="1.8"/>
              <line x1="17" y1="20" x2="17" y2="22" strokeWidth="1.8"/>
            </svg>
          </div>
          <div className="bob-header-text">
            <h3>IBM Bob — Yield Engineering Assistant</h3>
            <p>Ask any question about lots, sensors, defects, root causes, or corrective actions.</p>
          </div>
          <div style={{display:'flex',flexDirection:'column',gap:4,alignItems:'flex-end'}}>
            <span className="chip watsonx">IBM Granite</span>
            <span style={{fontSize:10,color:'rgba(255,255,255,.7)'}}>watsonx.ai</span>
          </div>
        </div>

        {/* Lot context */}
        <div style={{display:'flex',gap:12,alignItems:'flex-end',flexWrap:'wrap',marginBottom:16}}>
          <div className="field" style={{flex:'0 0 280px',minWidth:200}}>
            <label>Lot context (optional)</label>
            <select value={lotId} onChange={e => setLotId(e.target.value)}>
              <option value="">— No lot context (fleet-level) —</option>
              {lotItems.map(l => (
                <option key={l.lot_id} value={l.lot_id}>
                  {l.lot_id} ({l.yield_pct.toFixed(1)}%){l.low_yield_flag ? ' ⚠ LOW' : ''}
                </option>
              ))}
            </select>
          </div>
          {lotId && (
            <span className="badge">
              Context: lot {lotId}
            </span>
          )}
        </div>

        {/* Example chips */}
        <div className="card-title" style={{marginBottom:10}}>Example questions</div>
        <div className="example-chips">
          {EXAMPLES.map((q, i) => (
            <button key={i} className="example-chip" onClick={() => { setQuery(q); textRef.current?.focus() }}>
              {q}
            </button>
          ))}
        </div>

        <div className="divider"/>

        {/* Input */}
        <div className="chat-input-row">
          <textarea
            ref={textRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Type your yield-engineering question here… (Ctrl+Enter to send)"
            rows={3}
          />
          <button className="btn btn-primary" disabled={!query.trim() || loading} onClick={ask}
            style={{alignSelf:'stretch',minWidth:80}}>
            {loading ? <><span className="spinner"/>Asking…</> : <>Ask Bob</>}
          </button>
        </div>
        <div style={{fontSize:11,color:'var(--gray-50)',marginTop:6,textAlign:'right'}}>Ctrl + Enter to send</div>
      </div>

      {error && <div className="alert error"><strong>Error:</strong> {error}</div>}

      {loading && (
        <div className="loading-row">
          <span className="spinner"/>
          Consulting IBM watsonx.ai Granite…
        </div>
      )}

      {result && (
        <div className="card">
          {/* Response header */}
          <div className="card-header">
            <div style={{display:'flex',alignItems:'center',gap:8}}>
              <span className="card-title">Response</span>
              <span className={`chip ${isWx ? 'watsonx' : 'fallback'}`}>
                {isWx ? 'IBM watsonx.ai Granite' : 'Offline fallback'}
              </span>
            </div>
            {lotId && (
              <span className="badge">Lot context: {lotId}</span>
            )}
          </div>

          {/* Answer */}
          <div className="chat-answer">{result.answer}</div>

          {/* Meta footer */}
          <div className="chat-meta">
            {!isWx && (
              <span className="alert info" style={{padding:'4px 10px',margin:0,fontSize:11}}>
                Running in offline fallback mode — connect watsonx.ai credentials for live Granite responses.
              </span>
            )}
            <span style={{marginLeft:'auto',fontSize:11,color:'var(--gray-50)'}}>
              {result.query ? `Query: "${result.query.slice(0, 80)}${result.query.length > 80 ? '…' : ''}"` : ''}
            </span>
          </div>
        </div>
      )}

      {/* Tips card */}
      {!result && !loading && (
        <div className="card" style={{background:'var(--gray-05)',border:'1px dashed var(--gray-30)'}}>
          <div className="card-title" style={{marginBottom:10}}>Tips for best results</div>
          <ul style={{fontSize:13,color:'var(--gray-70)',lineHeight:2,paddingLeft:18}}>
            <li>Select a specific lot for context to get evidence-grounded answers.</li>
            <li>Ask about a specific tool, parameter, or defect type for detailed analysis.</li>
            <li>Use the Root Cause Analysis tab first to identify signals, then ask follow-up questions here.</li>
            <li>With watsonx.ai credentials configured, responses are generated by IBM Granite 3.3 8B.</li>
          </ul>
        </div>
      )}
    </div>
  )
}

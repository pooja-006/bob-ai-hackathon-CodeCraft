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
  const [query,    setQuery]    = useState('')
  const [lotId,    setLotId]    = useState('')
  const [result,   setResult]   = useState(null)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState(null)
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
      <div className="section-head"><h2>Ask Bob</h2></div>

      <div className="card">
        <p style={{fontSize:14,marginBottom:14,lineHeight:1.6}}>
          Ask any yield-engineering question. Optionally select a lot for context — the question is sent to{' '}
          <strong>IBM watsonx.ai Granite</strong> with relevant sensor and defect data injected automatically.
        </p>

        <div className="card-title">Example questions</div>
        <div className="example-chips">
          {EXAMPLES.map((q, i) => (
            <button key={i} className="example-chip" onClick={() => { setQuery(q); textRef.current?.focus() }}>
              {q}
            </button>
          ))}
        </div>

        <hr className="divider" />

        <div className="form-row" style={{marginBottom:12}}>
          <div className="field">
            <label>Lot context (optional)</label>
            <select value={lotId} onChange={e => setLotId(e.target.value)}>
              <option value="">— No lot context —</option>
              {lotItems.map(l => (
                <option key={l.lot_id} value={l.lot_id}>
                  {l.lot_id} ({l.yield_pct.toFixed(1)}%){l.low_yield_flag ? ' ⚠' : ''}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="chat-input-row">
          <textarea
            ref={textRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Type your question here… (Ctrl+Enter to send)"
            rows={3}
          />
          <button className="btn btn-primary" disabled={!query.trim() || loading} onClick={ask}>
            {loading ? <><span className="spinner"/>&nbsp;Asking…</> : 'Ask'}
          </button>
        </div>
      </div>

      {error && <div className="alert error"><strong>Error:</strong> {error}</div>}

      {result && (
        <div className="card">
          <div className="card-title">Response</div>
          <div className="chat-answer">{result.answer}</div>
          <div className="chat-meta">
            <span className={`chip ${isWx ? 'watsonx' : 'fallback'}`}>
              {isWx ? 'IBM watsonx.ai Granite' : 'Offline fallback'}
            </span>
            {lotId && <span>Context: lot <code>{lotId}</code></span>}
            <span className="text-muted" style={{marginLeft:'auto'}}>Ctrl+Enter to send</span>
          </div>
        </div>
      )}
    </div>
  )
}

import { useState, type FormEvent } from 'react'
import { LoaderCircle, Send } from 'lucide-react'
import { api } from '../services/api'
import type { Analysis, Priority, Recommendation } from '../types/dashboard'
import { score } from '../services/format'

export function RequestAnalyzer({ priorities, recommendations, onSaved, onSelect, onBusy }: {
  priorities: Priority[]; recommendations: Recommendation[]; onSaved: () => void; onSelect: (id: string) => void; onBusy: (busy: boolean) => void
}) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<Analysis | null>(null)
  const matching = result?.location_name && result.district ? priorities.filter(item =>
    item.location_name === result.location_name && item.district === result.district && item.category === result.category &&
    new Date(item.created_at).getTime() >= new Date(result.created_at).getTime()) : []
  const area = matching.length === 1 ? matching[0] : undefined
  const advice = area ? recommendations.find(item => item.hotspot_id === area.hotspot_id && item.evidence_snapshot.hotspot_created_at === area.created_at) : undefined

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy || !text.trim()) return
    setBusy(true)
    onBusy(true)
    setError('')
    setResult(null)
    try {
      setResult(await api.analyze(text.trim()))
      onSaved()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Analysis unavailable.')
    } finally { setBusy(false); onBusy(false) }
  }

  return <div className="analyzer-layout">
    <form onSubmit={submit} className="analyzer-form">
      <label htmlFor="citizen-text">Tell us about a development issue in your area</label>
      <textarea id="citizen-text" value={text} onChange={event => setText(event.target.value)} maxLength={5000} required disabled={busy} placeholder="Describe the issue and its location..." rows={6} />
      <div className="flex flex-wrap justify-between gap-2 field-meta"><span>English / Hindi / Kannada</span><span>{text.length.toLocaleString()} / 5,000</span></div>
      <p className="privacy-note">Submitted text is sent to Vertex AI and saved in BigQuery. Avoid personal or sensitive information.</p>
      <button type="submit" className="primary-button" disabled={busy || !text.trim()}>{busy ? <LoaderCircle className="spin" size={16} /> : <Send size={16} />}{busy ? 'Analyzing request' : 'Analyze request'}</button>
      {busy && <p role="status">Language, category, location and urgency analysis in progress...</p>}
      {error && <p role="alert" className="error-message">{error}</p>}
    </form>
    {result ? <section className="analysis-result" aria-label="Request analysis" aria-live="polite">
      <span className="result-label">REQUEST SAVED</span>
      <dl className="facts">
        <div><dt>Detected language</dt><dd>{result.language}</dd></div>
        <div><dt>Category</dt><dd>{result.category}</dd></div>
        <div><dt>Problem</dt><dd>{result.problem}</dd></div>
        <div><dt>Location</dt><dd>{result.location_name || 'Unresolved'}{result.district && `, ${result.district}`}</dd></div>
        <div><dt>Urgency</dt><dd>{result.urgency >= 0.7 ? 'High' : result.urgency >= 0.4 ? 'Medium' : 'Low'} <small>({result.urgency.toFixed(2)})</small></dd></div>
        <div><dt>Infrastructure Gap</dt><dd>{score(area?.infrastructure_gap_score)}</dd></div>
        <div><dt>Priority Score</dt><dd>{score(area?.priority_score)}</dd></div>
      </dl>
      <h3>AI Recommendation</h3>
      {advice ? <p>{advice.recommended_intervention}</p> : <p className="muted">Not available for this request's current evidence.</p>}
      {!area && <p className="muted">No matching scored hotspot at or after this submission. A resolved location and refreshed hotspot snapshot are required; below-threshold areas have no scores.</p>}
      {area && <a className="text-button" href="#recommendations" onClick={() => onSelect(area.hotspot_id)}>View area recommendations</a>}
    </section> : <div className="analysis-idle"><Send size={28} strokeWidth={1.3} /><p>{busy ? 'Analyzing citizen request...' : 'No request analyzed in this session.'}</p></div>}
  </div>
}
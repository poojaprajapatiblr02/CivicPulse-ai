import type { Hotspot, Priority, Recommendation } from '../types/dashboard'
import { number, score } from '../services/format'

export function AreaFacts({ hotspot, priority }: { hotspot: Hotspot; priority?: Priority }) {
  return <dl className="facts">
    <div><dt>Location</dt><dd>{hotspot.location_name}, {hotspot.district}</dd></div>
    <div><dt>Category</dt><dd>{hotspot.category}</dd></div>
    <div><dt>Request Count</dt><dd>{number(hotspot.request_count)}</dd></div>
    <div><dt>Affected Population</dt><dd>{number(hotspot.affected_population)} <small>proxy</small></dd></div>
    <div><dt>Priority Score</dt><dd>{score(priority?.priority_score)}</dd></div>
    <div><dt>Infrastructure Gap</dt><dd>{score(priority?.infrastructure_gap_score)}{priority?.capacity_gap != null && <small> / {number(priority.capacity_gap)} {priority.capacity_unit} deficit</small>}</dd></div>
  </dl>
}

export function RecommendationCard({ item, current }: { item: Recommendation; current: boolean | null }) {
  return <article className="recommendation">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="category-tag">{item.evidence_snapshot.category}</span>
      <span className={`snapshot-tag ${current ? 'current' : ''}`}>{current === null ? 'Snapshot status unavailable' : current ? 'Current snapshot' : 'Historical snapshot'}</span>
    </div>
    <p className="record-location">{item.evidence_snapshot.location_name} / {item.evidence_snapshot.district}</p>
    <h3>{item.recommended_intervention}</h3>
    <h4>Why</h4><ul>{item.reasoning.map((text, index) => <li key={index}>{text}</li>)}</ul>
    <h4>Evidence</h4><ul className="evidence-list">{item.evidence.map((text, index) => <li key={index}>{text}</li>)}</ul>
    <h4>Expected impact</h4><p>{item.expected_impact}</p>
    <div className="confidence-row"><span>Confidence <strong>{Math.round(item.confidence * 100)}%</strong></span><span className="muted">Uncalibrated AI estimate</span></div>
    <details><summary>Limitations &amp; source snapshot</summary>
      <ul>{item.limitations.map((text, index) => <li key={index}>{text}</li>)}</ul>
      <p>Evidence captured: <time dateTime={item.evidence_snapshot.hotspot_created_at}>{new Date(item.evidence_snapshot.hotspot_created_at).toLocaleString()}</time></p>
      <p>Generated: <time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString()}</time></p>
    </details>
  </article>
}
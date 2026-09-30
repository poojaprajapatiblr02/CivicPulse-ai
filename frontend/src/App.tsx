import { useEffect, useState } from 'react'
import { Activity, ArrowUpRight, Building2, Lightbulb, MapPin, MessageSquareText, LayoutDashboard, ListOrdered, RefreshCw, Sparkles, ChevronLeft, ChevronRight, LoaderCircle } from 'lucide-react'
import { HealthStatus } from './components/HealthStatus'
import { HotspotMap } from './components/HotspotMap'
import { AreaFacts, RecommendationCard } from './components/Evidence'
import { number, score } from './services/format'
import { RequestAnalyzer } from './components/RequestAnalyzer'
import { api, apiDocsUrl } from './services/api'
import { ComplaintPage } from './components/ComplaintPage'

const sections = [
  { id: 'overview', title: 'Overview', icon: LayoutDashboard },
  { id: 'hotspots', title: 'Demand Hotspot Map', icon: MapPin },
  { id: 'priorities', title: 'Priority Areas', icon: ListOrdered },
  { id: 'recommendations', title: 'AI Recommendations', icon: Lightbulb },
  { id: 'analyzer', title: 'Citizen Request Analyzer', icon: MessageSquareText },
]
const categories = ['Healthcare', 'Education', 'Roads', 'Water', 'Electricity', 'Other']

function useResource<Data>(load: () => Promise<Data>, revision: number): { data?: Data; loading: boolean; error?: string } {
  const [state, setState] = useState<{ data?: Data; revision: number; error?: string }>({ revision: -1 })
  useEffect(() => {
    let active = true
    load().then(data => { if (active) setState({ data, revision }) }, failure => {
      if (active) setState({ revision, error: failure instanceof Error ? failure.message : 'Data unavailable.' })
    })
    return () => { active = false }
  }, [load, revision])
  return state.revision === revision ? { ...state, loading: false } : { loading: true }
}

function Status({ resource }: { resource: { loading: boolean; error?: string } }) {
  if (resource.loading) return <p className="loading-state" role="status"><LoaderCircle size={16} className="spin" /> Loading live data...</p>
  if (resource.error) return <p className="error-message" role="alert">{resource.error}</p>
  return null
}

function App() {
  return window.location.pathname.replace(/\/$/, '') === '/complaint' ? <ComplaintPage /> : <Dashboard />
}

function Dashboard() {
  const [revision, setRevision] = useState(0)
  const [category, setCategory] = useState('All')
  const [selectedId, setSelectedId] = useState('')
  const [page, setPage] = useState(0)
  const [visibleAdvice, setVisibleAdvice] = useState(4)
  const [action, setAction] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')
  const summary = useResource(api.summary, revision)
  const hotspots = useResource(api.hotspots, revision)
  const priorities = useResource(api.priorities, revision)
  const gaps = useResource(api.gaps, revision)
  const recommendations = useResource(api.recommendations, revision)
  const loading = [summary, hotspots, priorities, gaps, recommendations].some(item => item.loading)
  const refresh = () => { setRevision(value => value + 1); setPage(0) }
  const matches = (item: { category: string }) => category === 'All' || item.category === category
  const shownHotspots = (hotspots.data || []).filter(matches)
  const ranked = (priorities.data || []).filter(matches)
  const shownAdvice = (recommendations.data || []).filter(item => matches(item.evidence_snapshot))
  const selected = shownHotspots.find(item => item.hotspot_id === selectedId)
  const currentScores = (priorities.data || []).filter(item => hotspots.data?.some(hotspot => hotspot.hotspot_id === item.hotspot_id && hotspot.created_at === item.created_at))
  const eligible = currentScores.filter(item => item.scoring_status === 'complete' && matches(item))
  const selectedPriority = currentScores.find(item => item.hotspot_id === selectedId)
  const capped = (count: number) => `${number(count)}${count >= 1000 ? '+' : ''}`
  const cards = [
    { title: 'Total Citizen Requests', icon: MessageSquareText, tone: 'green', resource: summary, value: summary.data && number(summary.data.total_requests), detail: 'All recorded submissions' },
    { title: 'Active Hotspots', icon: MapPin, tone: 'coral', resource: hotspots, value: hotspots.data && capped(hotspots.data.length), detail: 'Current detection snapshot' },
    { title: 'Infrastructure Gaps', icon: Building2, tone: 'blue', resource: gaps, value: gaps.data && `${number(gaps.data.filter(item => item.infrastructure_gap_score != null && item.infrastructure_gap_score > 0).length)}${gaps.data.length >= 1000 ? '+' : ''}`, detail: `Areas with a positive gap${gaps.data?.some(item => item.infrastructure_gap_score === null) ? ' / incomplete evidence excluded' : ''}` },
    { title: 'Recommendations', icon: Lightbulb, tone: 'gold', resource: recommendations, value: recommendations.data && capped(recommendations.data.length), detail: 'Saved advice, including history' },
  ]

  async function mutate(kind: 'detect' | 'generate') {
    if (action) return
    setAction(kind)
    setActionError('')
    setNotice('')
    try {
      if (kind === 'detect') await api.detect()
      else await api.generate(selectedId)
      setNotice(kind === 'detect' ? 'Hotspot scores refreshed.' : 'Recommendation saved.')
      refresh()
    } catch (failure) {
      setActionError(failure instanceof Error ? failure.message : 'Operation unavailable.')
    } finally { setAction('') }
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">Skip to content</a>
      <aside className="sidebar">
        <a href="#main" className="brand" aria-label="CivicPulse overview">
          <span className="brand-mark"><Activity size={22} aria-hidden="true" /></span>
          <span>CivicPulse<span className="brand-ai">AI</span></span>
        </a>
        <div className="workspace-label">POLICY WORKSPACE</div>
        <nav aria-label="Dashboard sections">
          {sections.map(({ id, title, icon: Icon }) => (
            <a key={id} href={`#${id}`} className="nav-link">
              <Icon size={18} aria-hidden="true" /><span>{title}</span>
            </a>
          ))}
        </nav>
        <div className="sidebar-footer"><span className="local-dot" /> Hackathon POC <span className="version">Phase 9</span></div>
      </aside>
      <div className="workspace min-w-0">
        <header className="topbar flex flex-wrap items-center justify-between gap-3">
          <span>Development intelligence <span className="breadcrumb">/ Overview</span></span>
          <a href="/complaint" className="secondary-button"><MessageSquareText size={16} />Register a complaint<ArrowUpRight size={14} /></a>
          <a href={apiDocsUrl} target="_blank" rel="noreferrer" className="flex items-center gap-1">API reference <ArrowUpRight size={14} /></a>
        </header>
        <main id="main" className="main-content">
          <div className="page-heading flex flex-wrap items-end justify-between gap-5">
            <div><p className="eyebrow">POLICYMAKER DASHBOARD</p><h1>CivicPulse AI</h1></div>
            <span className="demo-label">SYNTHETIC / DEMO DATA</span>
          </div>
          <HealthStatus />
          <section id="overview" className="dashboard-section" aria-labelledby="overview-title">
            <div className="section-heading flex flex-wrap items-center justify-between gap-3">
              <h2 id="overview-title">Development overview</h2>
              <button className="icon-button" title="Refresh dashboard" aria-label="Refresh dashboard" disabled={loading || !!action} onClick={refresh}><RefreshCw size={17} className={loading ? 'spin' : ''} /></button>
            </div>
            <div className="metrics-grid grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4">
              {cards.map(({ title, icon: Icon, tone, resource, value, detail }) => <article key={title} className={`metric tone-${tone}`}>
                <div className="flex justify-between gap-2"><h3>{title}</h3><span className="section-icon"><Icon size={18} /></span></div>
                <div className={`metric-value ${resource.loading ? 'skeleton' : ''}`} aria-label={resource.loading ? `${title} loading` : undefined}>{resource.loading ? '\u00a0' : value ?? 'Unavailable'}</div>
                <p>{detail}</p>
              </article>)}
            </div>
            <Status resource={summary} />
            <Status resource={gaps} />
            {cards.some(item => Array.isArray(item.resource.data) && item.resource.data.length >= 1000) && <p className="muted">List APIs are capped at 1,000 records; plus-marked counts are lower bounds.</p>}
          </section>
          <div className="dashboard-toolbar flex flex-wrap items-end justify-between gap-3">
            <label className="filter-label">Category<select aria-label="Category" value={category} onChange={event => { setCategory(event.target.value); setSelectedId(''); setPage(0); setVisibleAdvice(4) }}><option value="All">All categories</option>{categories.map(item => <option key={item}>{item}</option>)}</select></label>
            <button className="secondary-button" onClick={() => void mutate('detect')} disabled={!!action || loading || analyzing}><RefreshCw size={16} className={action === 'detect' ? 'spin' : ''} />{action === 'detect' ? 'Refreshing hotspot scores' : 'Refresh hotspot scores'}</button>
          </div>
          {actionError && <p role="alert" className="error-message">{actionError}</p>}
          {notice && <p role="status" className="success-message">{notice}</p>}
          <section id="hotspots" className="dashboard-section" aria-labelledby="map-title">
            <div className="section-heading"><span className="section-kicker">01 / DEMAND</span><h2 id="map-title">Demand Hotspot Map</h2></div>
            <Status resource={hotspots} />
            <div className="map-layout">
              <HotspotMap hotspots={shownHotspots} priorities={currentScores} selectedId={selectedId} onSelect={setSelectedId} />
              <aside className="area-detail"><span className="section-kicker">AREA BRIEF</span>
                {selected ? <><h3>{selected.location_name}</h3><AreaFacts hotspot={selected} priority={selectedPriority} /><a href="#recommendations" className="text-button">Review recommendations <ArrowUpRight size={14} /></a></> : <><MapPin size={28} strokeWidth={1.3} /><h3>{hotspots.data?.length ? 'No area selected' : 'Current demand snapshot'}</h3><p className="muted">{hotspots.loading ? 'Loading hotspot evidence...' : hotspots.error ? 'Hotspot evidence is unavailable.' : !hotspots.data?.length ? 'No active hotspots in the current snapshot.' : !shownHotspots.length ? 'No hotspots match this category.' : `${number(shownHotspots.length)} hotspot areas`}</p></>}
                <p className="map-footnote">Synthetic locations / population proxies</p>
              </aside>
            </div>
          </section>
          <section id="priorities" className="dashboard-section" aria-labelledby="priority-title">
            <div className="section-heading flex flex-wrap justify-between items-end gap-3"><div><span className="section-kicker">02 / ALLOCATION</span><h2 id="priority-title">Priority Areas</h2></div><span className="muted text-xs">Deterministic scores / 100</span></div>
            <Status resource={priorities} />
            {priorities.data && <><div className="table-scroll"><table aria-label="Priority areas"><thead><tr>{['Rank', 'Location', 'Category', 'Requests', 'Gap Score', 'Priority Score'].map(title => <th key={title} scope="col">{title}</th>)}</tr></thead><tbody>
              {ranked.slice(page * 10, page * 10 + 10).map((item, index) => <tr key={item.hotspot_id} className={selectedId === item.hotspot_id ? 'selected-row' : ''}>
                <td className="rank">{page * 10 + index + 1}</td><td><button className="location-button" onClick={() => setSelectedId(item.hotspot_id)}>{item.location_name}</button><small>{item.district}</small></td><td><span className="category-tag">{item.category}</span></td><td>{number(item.request_count)}</td><td>{score(item.infrastructure_gap_score)}</td><td><span className="priority-score">{score(item.priority_score)}</span>{item.data_issues && <small>{item.data_issues}</small>}</td>
              </tr>)}
            </tbody></table></div>
            {!ranked.length && <p className="empty-message">No priority areas match this category.</p>}
            {ranked.length > 10 && <div className="pagination"><span>{page + 1} / {Math.ceil(ranked.length / 10)}</span><button className="icon-button" aria-label="Previous page" title="Previous page" disabled={page === 0} onClick={() => setPage(value => value - 1)}><ChevronLeft size={16} /></button><button className="icon-button" aria-label="Next page" title="Next page" disabled={(page + 1) * 10 >= ranked.length} onClick={() => setPage(value => value + 1)}><ChevronRight size={16} /></button></div>}</>}
          </section>
          <section id="recommendations" className="dashboard-section" aria-labelledby="recommendations-title">
            <div className="section-heading"><span className="section-kicker">03 / DECISION SUPPORT</span><h2 id="recommendations-title">AI Recommendations</h2></div>
            <div className="recommendation-toolbar flex flex-wrap items-end gap-3">
              <label className="filter-label">Recommendation area<select aria-label="Recommendation area" value={eligible.some(item => item.hotspot_id === selectedId) ? selectedId : ''} disabled={!!action || loading} onChange={event => setSelectedId(event.target.value)}><option value="">Select a scored hotspot</option>{eligible.map(item => <option key={item.hotspot_id} value={item.hotspot_id}>{item.location_name} / {item.category}</option>)}</select></label>
              <button className="primary-button" disabled={!!action || loading || !eligible.some(item => item.hotspot_id === selectedId)} onClick={() => void mutate('generate')}><Sparkles size={16} />{action === 'generate' ? 'Generating recommendation' : 'Generate recommendation'}</button>
              <span className="muted text-xs">Advisory only / human review required</span>
            </div>
            <Status resource={recommendations} />
            {recommendations.data && !shownAdvice.length && <p className="empty-message">{recommendations.data.length ? 'No recommendations match this category.' : 'No recommendations recorded.'}</p>}
            <div className="recommendation-grid">{shownAdvice.slice(0, visibleAdvice).map(item => <RecommendationCard key={item.recommendation_id} item={item} current={!hotspots.data ? null : hotspots.data.some(hotspot => hotspot.hotspot_id === item.hotspot_id && hotspot.created_at === item.evidence_snapshot.hotspot_created_at)} />)}</div>
            {shownAdvice.length > visibleAdvice && <button className="secondary-button" onClick={() => setVisibleAdvice(value => value + 4)}>Show more recommendations</button>}
          </section>
          <section id="analyzer" className="dashboard-section" aria-labelledby="analyzer-title">
            <div className="section-heading"><span className="section-kicker">04 / CITIZEN VOICE</span><h2 id="analyzer-title">Citizen Request Analyzer</h2></div>
            <RequestAnalyzer priorities={currentScores} recommendations={recommendations.data || []} onSaved={refresh} onBusy={setAnalyzing} onSelect={id => { setCategory('All'); setSelectedId(id) }} />
          </section>
          <footer className="page-footer flex flex-wrap items-center justify-between gap-3">
            <span>BRICS Innovation Hackathon <span className="footer-separator">/</span> Proof of concept</span>
            <a href="#main" className="flex items-center gap-1">Overview <ArrowUpRight size={14} aria-hidden="true" /></a>
          </footer>
        </main>
      </div>
    </div>
  )
}

export default App

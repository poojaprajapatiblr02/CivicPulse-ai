import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { api, getHealth } from './services/api'
import type { Analysis, Priority, Recommendation } from './types/dashboard'

vi.mock('./services/api', () => ({
  apiDocsUrl: 'http://127.0.0.1:8000/docs',
  getHealth: vi.fn(),
  api: Object.fromEntries(['summary', 'hotspots', 'priorities', 'gaps', 'recommendations', 'analyze', 'detect', 'generate'].map(name => [name, vi.fn()])),
}))

const priority: Priority = {
  hotspot_id: 'area-1', location_name: 'Test Ward', district: 'Test District', category: 'Healthcare',
  latitude: 12.9, longitude: 77.6, request_count: 27, affected_population: 8500,
  created_at: '2026-09-20T12:00:00Z', infrastructure_gap_score: 91, priority_score: 82.9,
  capacity_gap: 90, capacity_unit: 'beds', scoring_status: 'complete', data_issues: null,
}
const recommendation: Recommendation = {
  recommendation_id: 'rec-1', hotspot_id: 'area-1', recommended_intervention: 'Improve healthcare access',
  reasoning: ['Distance creates an access barrier.'], evidence: ['Request count: 27', 'Gap score: 91', 'Priority score: 82.9'],
  expected_impact: 'Better access to care.', confidence: 0.91, limitations: ['Synthetic evidence; field review required.'],
  created_at: '2026-09-20T12:01:00Z', evidence_snapshot: {
    hotspot_id: 'area-1', hotspot_created_at: priority.created_at, category: priority.category,
    location_name: priority.location_name, district: priority.district, facts: {}, limitations: [],
  },
}
const analysis: Analysis = {
  request_id: 'request-1', language: 'Hindi', category: 'Healthcare', problem: 'Hospital too far',
  location_name: 'Test Ward', district: 'Test District', urgency: 0.9, created_at: '2026-09-20T11:59:00Z',
}

beforeEach(() => {
  vi.mocked(getHealth).mockResolvedValue({ status: 'healthy', service: 'civicpulse-backend' })
  vi.mocked(api.summary).mockResolvedValue({ total_requests: 501, requests_by_category: { Healthcare: 27 }, total_population: 8500, infrastructure_records: 1, total_investment: '1200000' })
  vi.mocked(api.hotspots).mockResolvedValue([priority])
  vi.mocked(api.priorities).mockResolvedValue([priority])
  vi.mocked(api.gaps).mockResolvedValue([priority])
  vi.mocked(api.recommendations).mockResolvedValue([recommendation])
  vi.mocked(api.analyze).mockResolvedValue(analysis)
  vi.mocked(api.detect).mockResolvedValue([priority])
  vi.mocked(api.generate).mockResolvedValue(recommendation)
})
afterEach(() => { cleanup(); vi.resetAllMocks(); window.history.replaceState({}, '', '/') })

describe('sample citizen page', () => {
  it('previews photos through review and edit, removes them, and releases local URLs', () => {
    const createUrl = vi.fn(() => 'blob:photo-preview')
    const revokeUrl = vi.fn()
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: createUrl, revokeObjectURL: revokeUrl }))
    try {
      window.history.replaceState({}, '', '/complaint')
      const view = render(<App />)
      const photo = new File(['photo'], 'road.png', { type: 'image/png' })
      fireEvent.change(screen.getByLabelText('Add pictures (optional)'), { target: { files: [photo] } })
      expect(screen.getByAltText('Attachment: road.png')).toHaveAttribute('src', 'blob:photo-preview')
      fireEvent.change(screen.getByLabelText('District'), { target: { value: 'Mandya' } })
      fireEvent.change(screen.getByLabelText('Village'), { target: { value: 'Melukote' } })
      fireEvent.change(screen.getByLabelText('Issue details'), { target: { value: 'Damaged road' } })
      fireEvent.click(screen.getByRole('button', { name: 'Review complaint' }))
      expect(screen.getByAltText('Attachment: road.png')).toBeVisible()
      expect(screen.queryByRole('button', { name: 'Remove road.png' })).not.toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: 'Edit complaint' }))
      fireEvent.click(screen.getByRole('button', { name: 'Remove road.png' }))
      expect(screen.queryByAltText('Attachment: road.png')).not.toBeInTheDocument()
      expect(revokeUrl).toHaveBeenCalledWith('blob:photo-preview')
      expect(api.analyze).not.toHaveBeenCalled()
      view.unmount()
    } finally { vi.unstubAllGlobals() }
  })
  it('rejects unsupported, oversized and excess photos without making API calls', () => {
    window.history.replaceState({}, '', '/complaint')
    render(<App />)
    const input = screen.getByLabelText('Add pictures (optional)')
    fireEvent.change(input, { target: { files: [new File(['text'], 'note.txt', { type: 'text/plain' })] } })
    expect(screen.getByRole('alert')).toHaveTextContent('JPEG, PNG or WebP')
    const large = new File(['photo'], 'large.png', { type: 'image/png' })
    Object.defineProperty(large, 'size', { value: 5 * 1024 * 1024 + 1 })
    fireEvent.change(input, { target: { files: [large] } })
    expect(screen.getByRole('alert')).toHaveTextContent('5 MB')
    fireEvent.change(input, { target: { files: Array.from({ length: 6 }, () => new File(['photo'], 'road.png', { type: 'image/png' })) } })
    expect(screen.getByRole('alert')).toHaveTextContent('five pictures')
    expect(api.analyze).not.toHaveBeenCalled()
  })
  it('previews voice transcription without microphone or network access and preserves typed text', () => {
    window.history.replaceState({}, '', '/complaint')
    render(<App />)
    fireEvent.change(screen.getByLabelText('Issue details'), { target: { value: 'Existing details.' } })
    fireEvent.click(screen.getByRole('radio', { name: 'Record voice' }))
    fireEvent.click(screen.getByRole('button', { name: 'Start sample recording' }))
    expect(screen.getByRole('status')).toHaveTextContent('Microphone is off')
    fireEvent.click(screen.getByRole('button', { name: 'Stop sample recording' }))
    fireEvent.change(screen.getByLabelText('Sample transcript (English)'), { target: { value: 'The road near the bus stop needs repair.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add sample to complaint' }))
    expect(screen.getByLabelText('Issue details')).toHaveValue('Existing details.\n\nThe road near the bus stop needs repair.')
    expect(screen.getByLabelText('Complaint language')).toHaveValue('English')
    expect(screen.getByRole('button', { name: 'Add sample to complaint' })).toBeDisabled()
    expect(api.analyze).not.toHaveBeenCalled()
  })
  it('offers safe call, messaging and assisted registration previews', () => {
    window.history.replaceState({}, '', '/complaint')
    render(<App />)
    for (const channel of ['Call / IVR', 'WhatsApp', 'SMS', 'Assisted entry']) {
      fireEvent.click(screen.getByRole('radio', { name: channel }))
      fireEvent.click(screen.getByRole('button', { name: 'Preview conversation' }))
      expect(screen.getByText('Sample exchange / not connected')).toBeVisible()
    }
    expect(document.querySelector('a[href^="tel:"], a[href^="sms:"], a[href*="wa.me"]')).toBeNull()
    expect(api.analyze).not.toHaveBeenCalled()
    expect(getHealth).not.toHaveBeenCalled()
  })
  it('validates voice-note selection locally and labels the transcript as a sample', () => {
    window.history.replaceState({}, '', '/complaint')
    render(<App />)
    fireEvent.click(screen.getByRole('radio', { name: 'Voice note' }))
    const input = screen.getByLabelText('Choose an audio file (local preview only)')
    fireEvent.change(input, { target: { files: [new File(['text'], 'note.txt', { type: 'text/plain' })] } })
    expect(screen.getByRole('alert')).toHaveTextContent('Choose an audio file')
    fireEvent.change(input, { target: { files: [new File(['audio'], 'complaint.webm', { type: 'audio/webm' })] } })
    expect(screen.getByText('complaint.webm')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Show sample transcript' }))
    expect(screen.getByLabelText('Sample transcript (English)')).toBeVisible()
    expect(screen.getByText(/Not transcribed from your file/)).toBeVisible()
    expect(api.analyze).not.toHaveBeenCalled()
  })
  it('opens a separate complaint page without loading backend data', () => {
    window.history.replaceState({}, '', '/complaint')
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Register a complaint' })).toBeVisible()
    expect(screen.getByRole('link', { name: /Policymaker dashboard/ })).toHaveAttribute('href', '/')
    expect(api.summary).not.toHaveBeenCalled()
    expect(getHealth).not.toHaveBeenCalled()
  })
  it('reviews urban issue details without submitting or claiming registration', () => {
    window.history.replaceState({}, '', '/complaint')
    render(<App />)
    fireEvent.click(screen.getByLabelText('Urban'))
    fireEvent.change(screen.getByLabelText('District'), { target: { value: 'Bengaluru Urban' } })
    fireEvent.change(screen.getByLabelText('Ward / locality'), { target: { value: 'Whitefield' } })
    fireEvent.change(screen.getByLabelText('Issue details'), { target: { value: 'The road near the bus stop needs repair.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Review complaint' }))
    expect(screen.getByRole('heading', { name: 'Review your complaint' })).toBeVisible()
    expect(screen.getByText('Whitefield')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Finish preview' }))
    expect(screen.getByRole('status')).toHaveTextContent('Nothing was submitted or saved')
    expect(api.analyze).not.toHaveBeenCalled()
    expect(api.generate).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Edit complaint' }))
    expect(screen.getByLabelText('Issue details')).toHaveValue('The road near the bus stop needs repair.')
  })
  it('requires nonblank location and issue details', () => {
    window.history.replaceState({}, '', '/complaint')
    render(<App />)
    expect(screen.getByLabelText('Village')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Review complaint' })).toBeDisabled()
  })
})

async function ready() {
  render(<App />)
  await screen.findByText('501')
  await screen.findByRole('heading', { name: 'Improve healthcare access' })
}

function submit() {
  fireEvent.change(screen.getByLabelText('Tell us about a development issue in your area'), { target: { value: 'Hospital too far in Test Ward' } })
  fireEvent.click(screen.getByRole('button', { name: 'Analyze request' }))
}

describe('Phase 9 policymaker dashboard', () => {
  it('opens an accessible grouped marker with all required hotspot facts', async () => {
    vi.mocked(api.hotspots).mockResolvedValue([priority, { ...priority, hotspot_id: 'area-2', category: 'Water' }])
    await ready()
    fireEvent.click(screen.getByRole('button', { name: 'View Test Ward' }))
    const popup = document.querySelector('.leaflet-popup') as HTMLElement
    expect(popup).toHaveTextContent('Affected Population')
    expect(popup).toHaveTextContent('8,500')
    expect(popup).toHaveTextContent('Priority Score')
    expect(popup).toHaveTextContent('82.90')
    expect(popup).toHaveTextContent('Infrastructure Gap')
    expect(popup).toHaveTextContent('Water')
    fireEvent.click(within(popup).getByRole('button', { name: 'Select Water' }))
    expect(document.querySelector('.area-detail')).toHaveTextContent('Water')
  })
  it('renders backend totals, a Leaflet map, ranked scores and evidence', async () => {
    await ready()
    expect(screen.getByRole('heading', { name: 'CivicPulse AI', level: 1 })).toBeVisible()
    expect(document.querySelector('.leaflet-container')).toBeTruthy()
    expect(screen.getByRole('table', { name: 'Priority areas' })).toHaveTextContent('82.90')
    expect(screen.getByText('Request count: 27')).toBeVisible()
    expect(screen.getByText('91%')).toBeVisible()
    expect(screen.getByText('Backend connected')).toBeVisible()
    expect(api.generate).not.toHaveBeenCalled()
  })
  it('paginates priority rows and expands recommendation history', async () => {
    vi.mocked(api.priorities).mockResolvedValue(Array.from({ length: 11 }, (_, index) => ({ ...priority, hotspot_id: `area-${index}`, location_name: `Ward ${index + 1}` })))
    vi.mocked(api.recommendations).mockResolvedValue(Array.from({ length: 5 }, (_, index) => ({ ...recommendation, recommendation_id: `rec-${index}` })))
    render(<App />)
    await screen.findByRole('button', { name: 'Next page' })
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    expect(screen.getByRole('table')).toHaveTextContent('Ward 11')
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Previous page' }))
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled()
    expect(screen.getAllByRole('heading', { name: recommendation.recommended_intervention })).toHaveLength(4)
    fireEvent.click(screen.getByRole('button', { name: 'Show more recommendations' }))
    expect(screen.getAllByRole('heading', { name: recommendation.recommended_intervention })).toHaveLength(5)
  })
  it('marks capped counts as lower bounds and excludes unknown gaps', async () => {
    vi.mocked(api.recommendations).mockResolvedValue(Array.from({ length: 1000 }, (_, index) => ({ ...recommendation, recommendation_id: `rec-${index}` })))
    vi.mocked(api.gaps).mockResolvedValue([{ ...priority, infrastructure_gap_score: null }])
    render(<App />)
    expect(await screen.findByText('1,000+')).toBeVisible()
    expect(screen.getByText(/plus-marked counts are lower bounds/)).toBeVisible()
    expect(screen.getByText(/incomplete evidence excluded/)).toBeVisible()
  })
  it('reports health and map tile failures while keeping evidence available', async () => {
    vi.mocked(getHealth).mockRejectedValue(new Error('Network failure'))
    await ready()
    expect(screen.getByText('Backend unavailable')).toBeVisible()
    const tile = document.querySelector('.leaflet-tile')
    expect(tile).toBeTruthy()
    fireEvent.error(tile!)
    expect(screen.getByText(/Basemap unavailable/)).toBeVisible()
    expect(screen.getByRole('table')).toHaveTextContent('82.90')
  })
  it('keeps unknown snapshots distinct from historical ones during a read failure', async () => {
    vi.mocked(api.hotspots).mockRejectedValue(new Error('Hotspots unavailable'))
    await ready()
    expect(screen.getByText('Hotspots unavailable')).toBeVisible()
    expect(screen.getByText('Snapshot status unavailable')).toBeVisible()
  })
  it('supports filters, selecting an area and generating advice explicitly', async () => {
    await ready()
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'Water' } })
    expect(screen.getByText('No priority areas match this category.')).toBeVisible()
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'All' } })
    fireEvent.click(within(screen.getByRole('table')).getByRole('button', { name: 'Test Ward' }))
    fireEvent.click(screen.getByRole('button', { name: 'Generate recommendation' }))
    await waitFor(() => expect(api.generate).toHaveBeenCalledWith('area-1'))
    expect(await screen.findByText('Recommendation saved.')).toBeVisible()
  })
  it('analyzes text and displays matching current scores and advice', async () => {
    await ready()
    submit()
    const result = await screen.findByRole('region', { name: 'Request analysis' })
    expect(result).toHaveTextContent('Hindi')
    expect(result).toHaveTextContent('Hospital too far')
    expect(result).toHaveTextContent('High')
    await waitFor(() => expect(result).toHaveTextContent('91.00'))
    expect(result).toHaveTextContent('82.90')
    expect(result).toHaveTextContent('Improve healthcare access')
    expect(api.analyze).toHaveBeenCalledWith('Hospital too far in Test Ward')
    expect(api.detect).not.toHaveBeenCalled()
  })
  it('does not link old snapshots to a newer request', async () => {
    vi.mocked(api.analyze).mockResolvedValue({ ...analysis, created_at: '2026-09-20T13:00:00Z' })
    await ready()
    submit()
    const result = await screen.findByRole('region', { name: 'Request analysis' })
    expect(result).toHaveTextContent('Not available')
    expect(result).not.toHaveTextContent('Improve healthcare access')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh hotspot scores' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Refresh hotspot scores' }))
    await waitFor(() => expect(api.detect).toHaveBeenCalledOnce())
  })
  it('does not match an unresolved request location', async () => {
    vi.mocked(api.analyze).mockResolvedValue({ ...analysis, district: null, location_name: null, urgency: 0.2 })
    await ready()
    submit()
    const result = await screen.findByRole('region', { name: 'Request analysis' })
    expect(result).toHaveTextContent('Low')
    expect(result).toHaveTextContent('Unresolved')
    expect(result).toHaveTextContent('Not available')
  })
  it('shows pending analysis, prevents duplicates and handles errors', async () => {
    let reject!: (error: Error) => void
    vi.mocked(api.analyze).mockReturnValue(new Promise((_, fail) => { reject = fail }))
    await ready()
    expect(screen.getByRole('button', { name: 'Analyze request' })).toBeDisabled()
    submit()
    expect(screen.getByRole('button', { name: 'Analyzing request' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Refresh hotspot scores' })).toBeDisabled()
    reject(new Error('Analysis unavailable'))
    expect(await screen.findByText('Analysis unavailable')).toBeVisible()
  })
  it('keeps loaded sections available when another API fails and retries reads', async () => {
    vi.mocked(api.summary).mockRejectedValue(new Error('Summary unavailable'))
    render(<App />)
    expect(await screen.findByText('Summary unavailable')).toBeVisible()
    expect(await screen.findByRole('heading', { name: 'Improve healthcare access' })).toBeVisible()
    vi.mocked(api.summary).mockResolvedValue({ total_requests: 502, requests_by_category: {}, total_population: 0, infrastructure_records: 0, total_investment: '0' })
    fireEvent.click(screen.getByRole('button', { name: 'Refresh dashboard' }))
    expect(await screen.findByText('502')).toBeVisible()
  })
  it('shows genuine empty states without inventing scores or recommendations', async () => {
    vi.mocked(api.hotspots).mockResolvedValue([])
    vi.mocked(api.priorities).mockResolvedValue([])
    vi.mocked(api.gaps).mockResolvedValue([])
    vi.mocked(api.recommendations).mockResolvedValue([])
    render(<App />)
    expect(await screen.findByText('No active hotspots in the current snapshot.')).toBeVisible()
    expect(await screen.findByText('No recommendations recorded.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Generate recommendation' })).toBeDisabled()
  })
  it('labels old recommendation history and incomplete scores', async () => {
    vi.mocked(api.priorities).mockResolvedValue([{ ...priority, priority_score: null, infrastructure_gap_score: null, scoring_status: 'insufficient_data', data_issues: 'Missing infrastructure' }])
    vi.mocked(api.hotspots).mockResolvedValue([{ ...priority, created_at: '2026-09-20T13:00:00Z' }])
    await ready()
    expect(screen.getByText('Historical snapshot')).toBeVisible()
    expect(screen.getByRole('table')).toHaveTextContent('Not available')
    expect(screen.getByRole('button', { name: 'Generate recommendation' })).toBeDisabled()
  })
  it('handles detection and generation failures without discarding the dashboard', async () => {
    vi.mocked(api.detect).mockRejectedValue(new Error('Detection failed'))
    vi.mocked(api.generate).mockRejectedValue(new Error('Generation failed'))
    await ready()
    fireEvent.click(screen.getByRole('button', { name: 'Refresh hotspot scores' }))
    expect(await screen.findByText('Detection failed')).toBeVisible()
    fireEvent.change(screen.getByLabelText('Recommendation area'), { target: { value: priority.hotspot_id } })
    fireEvent.click(screen.getByRole('button', { name: 'Generate recommendation' }))
    expect(await screen.findByText('Generation failed')).toBeVisible()
  })
})
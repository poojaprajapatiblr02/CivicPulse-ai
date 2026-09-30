import type { HealthResponse } from '../types/api'
import type { Analysis, Hotspot, Priority, Recommendation, Summary } from '../types/dashboard'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '')
export const apiDocsUrl = `${apiBaseUrl}/docs`

async function request<Response>(path: string, body?: object, timeout = 60000): Promise<Response> {
  let response: ResponseType
  try {
    response = await fetch(`${apiBaseUrl}/api/v1/${path}`, {
      signal: AbortSignal.timeout(timeout),
      ...(body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}),
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new Error('The operation timed out. Its outcome may be unknown; refresh before submitting again.')
    }
    throw new Error('Cannot reach the backend. Check your connection. For a submission, refresh before retrying; it may have been saved.')
  }
  if (!response.ok) {
    const messages: Record<number, string> = {
      409: 'Evidence is incomplete or out of date. Refresh hotspot scores before generating advice.',
      422: 'The request could not be analyzed. Check the text and supported language (English, Hindi or Kannada).',
      502: 'AI output did not pass validation. No recommendation is available.',
      503: 'The backend service is unavailable. Refresh before retrying a submission.',
      504: 'The AI operation timed out. Refresh before submitting again.',
    }
    throw new Error(messages[response.status] || 'The operation failed. Refresh before retrying a submission.')
  }
  try {
    return await response.json() as Response
  } catch {
    throw new Error('Unexpected response from the backend. Refresh before retrying a submission.')
  }
}

type ResponseType = Awaited<ReturnType<typeof fetch>>

export const api = {
  summary: () => request<Summary>('dashboard/summary'),
  hotspots: () => request<Hotspot[]>('hotspots?limit=1000'),
  priorities: () => request<Priority[]>('priorities?limit=1000'),
  gaps: () => request<Priority[]>('gaps?limit=1000'),
  recommendations: () => request<Recommendation[]>('recommendations?limit=1000'),
  analyze: (text: string) => request<Analysis>('requests/analyze', { text }, 240000),
  detect: () => request<Hotspot[]>('hotspots/detect', {}, 180000),
  generate: (hotspot_id: string) => request<Recommendation>('recommendations/generate', { hotspot_id }, 120000),
}

export async function getHealth(signal: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/health`, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]),
  })
  if (!response.ok) throw new Error('Health check failed')
  const body: unknown = await response.json()
  if (
    !body || typeof body !== 'object' ||
    !('status' in body) || body.status !== 'healthy' ||
    !('service' in body) || body.service !== 'civicpulse-backend'
  ) throw new Error('Unexpected health response')
  return { status: body.status, service: body.service }
}
import { afterEach, describe, expect, it, vi } from 'vitest'
import { getHealth, api } from './api'

afterEach(() => vi.unstubAllGlobals())

describe('dashboard API', () => {
  it('loads the backend summary and bounded history', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] })
    vi.stubGlobal('fetch', fetchMock)
    await api.summary()
    await api.hotspots()
    await api.priorities()
    await api.gaps()
    await api.recommendations()
    expect(fetchMock.mock.calls.map(([url]) => new URL(url).pathname + new URL(url).search)).toEqual([
      '/api/v1/dashboard/summary', '/api/v1/hotspots?limit=1000',
      '/api/v1/priorities?limit=1000', '/api/v1/gaps?limit=1000', '/api/v1/recommendations?limit=1000',
    ])
  })

  it('posts only citizen text or the selected hotspot identifier', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)
    await api.analyze('Hospital too far')
    await api.generate('hotspot-id')
    await api.detect()
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST', body: JSON.stringify({ text: 'Hospital too far' }) })
    expect(fetchMock.mock.calls[1][1].body).toBe(JSON.stringify({ hotspot_id: 'hotspot-id' }))
    expect(fetchMock.mock.calls[2][1].method).toBe('POST')
  })

  it.each([409, 422, 502, 503, 504, 500])('reports HTTP %s without exposing server content', async (status) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status, json: async () => ({ detail: 'private details' }) }))
    await expect(api.summary()).rejects.toThrow()
    await expect(api.summary()).rejects.not.toThrow('private details')
  })

  it('reports network failure and timeout safely', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private network details')))
    await expect(api.summary()).rejects.toThrow('Cannot reach the backend')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('timeout', 'TimeoutError')))
    await expect(api.analyze('test')).rejects.toThrow('timed out')
  })
  it('redacts malformed response bodies', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => { throw new SyntaxError('private response content') } }))
    await expect(api.summary()).rejects.toThrow('Unexpected response from the backend')
  })
})

describe('health API', () => {
  it('uses the configured API URL and validates a healthy response', async () => {
    const body = { status: 'healthy', service: 'civicpulse-backend' }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => body })
    vi.stubGlobal('fetch', fetchMock)

    await expect(getHealth(new AbortController().signal)).resolves.toEqual(body)
    const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '')
    expect(fetchMock).toHaveBeenCalledWith(`${baseUrl}/api/v1/health`, expect.objectContaining({ signal: expect.any(AbortSignal) }))
  })

  it('rejects failed HTTP responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }))
    await expect(getHealth(new AbortController().signal)).rejects.toThrow('Health check failed')
  })

  it.each([null, {}, { status: 'healthy', service: 'different-service' }])(
    'rejects unexpected response data: %j', async (body) => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => body }))
      await expect(getHealth(new AbortController().signal)).rejects.toThrow('Unexpected health response')
    },
  )
})
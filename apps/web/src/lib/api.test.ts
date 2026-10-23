import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiUnavailable, fetchHealth, fetchRegions } from './api'

/**
 * These cover the failure paths, not the happy one. An unguarded
 * `response.json()` on a truncated body throws a bare SyntaxError that escapes
 * every handler and renders the whole board as an opaque 500 — which is
 * exactly what a half-written Next fetch cache produces.
 */

const REGIONS = [{ code: 'IN', name: 'India' }]

function jsonResponse(body: string, status = 200): Response {
  return new Response(body, { status, headers: { 'content-type': 'application/json' } })
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('get()', () => {
  it('returns parsed JSON on a healthy response', async () => {
    fetchMock.mockImplementation(async () => jsonResponse(JSON.stringify(REGIONS)))

    await expect(fetchRegions()).resolves.toEqual(REGIONS)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('retries once when a body comes back truncated', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(''))
      .mockResolvedValueOnce(jsonResponse(JSON.stringify(REGIONS)))

    await expect(fetchRegions()).resolves.toEqual(REGIONS)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('never stores responses in the on-disk fetch cache', () => {
    // That cache returned truncated bodies and threw inside Next, upstream of
    // anything this module can catch, which rendered as a blank 500.
    fetchMock.mockImplementation(async () => jsonResponse(JSON.stringify(REGIONS)))

    return fetchRegions().then(() => {
      for (const call of fetchMock.mock.calls) {
        expect(call[1]).toMatchObject({ cache: 'no-store' })
        expect(call[1]).not.toHaveProperty('next')
      }
    })
  })

  it('surfaces ApiUnavailable, not SyntaxError, when the retry is also unparseable', async () => {
    // A fresh Response per call: a body can only be read once, so reusing one
    // object would fail on the retry for a reason the product never hits.
    fetchMock.mockImplementation(async () => jsonResponse('{"trends": ['))

    // ApiUnavailable renders the explanatory board; a SyntaxError renders a 500.
    await expect(fetchRegions()).rejects.toBeInstanceOf(ApiUnavailable)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('does not retry a non-200, since the body was never the problem', async () => {
    fetchMock.mockImplementation(async () => jsonResponse('{"detail":"nope"}', 503))

    await expect(fetchRegions()).rejects.toBeInstanceOf(ApiUnavailable)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('reports an unreachable API rather than throwing the transport error', async () => {
    fetchMock.mockRejectedValue(new TypeError('fetch failed'))

    await expect(fetchRegions()).rejects.toBeInstanceOf(ApiUnavailable)
  })
})

describe('fetchHealth()', () => {
  it('returns null instead of throwing, so the top bar can render a dot', async () => {
    fetchMock.mockRejectedValue(new TypeError('fetch failed'))

    await expect(fetchHealth()).resolves.toBeNull()
  })

  it('returns null on an unparseable body too', async () => {
    fetchMock.mockImplementation(async () => jsonResponse(''))

    await expect(fetchHealth()).resolves.toBeNull()
  })
})

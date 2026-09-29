import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchStyles, fetchTranslation } from './client'

const API_BASE = 'http://localhost:8000'

function mockFetch(response) {
  const spy = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', spy)
  return spy
}

function ok(data) {
  return { ok: true, json: async () => ({ success: true, data }) }
}

function fail(error) {
  return { ok: false, json: async () => ({ success: false, error }) }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchStyles', () => {
  it('성공 시 스타일 맵을 반환한다 ({success, data} 언랩)', async () => {
    const styles = { general: '일반체', sns: 'SNS체' }
    const spy = mockFetch(ok(styles))

    await expect(fetchStyles()).resolves.toEqual(styles)
    expect(spy).toHaveBeenCalledWith(`${API_BASE}/styles`)
  })

  it('실패 시 에러를 던진다', async () => {
    mockFetch(fail(undefined))

    await expect(fetchStyles()).rejects.toThrow('스타일 목록을 불러오지 못했습니다.')
  })
})

describe('fetchTranslation', () => {
  it('target_lang으로 snake_case 변환해서 POST한다', async () => {
    const spy = mockFetch(ok({ candidates: ['결과1', '결과2', '결과3'], style: 'sns' }))

    await fetchTranslation({ text: '안녕', targetLang: '영어', style: 'sns' })

    const [url, options] = spy.mock.calls[0]
    expect(url).toBe(`${API_BASE}/translate`)
    expect(options.method).toBe('POST')
    expect(options.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(options.body)).toEqual({
      text: '안녕',
      target_lang: '영어',
      style: 'sns',
    })
  })

  it('성공 시 data 필드를 언랩해서 반환한다', async () => {
    const data = { candidates: ['결과1', '결과2', '결과3'], style: 'general' }
    mockFetch(ok(data))

    await expect(
      fetchTranslation({ text: '안녕', targetLang: '한국어', style: 'general' }),
    ).resolves.toEqual(data)
  })

  it('SHORT_LIMIT를 넘으면 /translate/long으로 보내고 candidates 형태로 맞춘다', async () => {
    const spy = mockFetch(ok({ translation: '장문 번역', style: 'general' }))

    await expect(
      fetchTranslation({ text: '가'.repeat(1001), targetLang: '영어', style: 'general' }),
    ).resolves.toEqual({ candidates: ['장문 번역'], style: 'general' })
    expect(spy.mock.calls[0][0]).toBe(`${API_BASE}/translate/long`)
  })

  // 백엔드 공통 error envelope({ success: false, error: { code, message } })에 의존하는 테스트.
  // 형식이 또 바뀌면 client.js의 unwrap()과 함께 여기도 수정해야 합니다.
  it('실패 시 error.message를 에러로 던지고 error.code를 실어 보낸다', async () => {
    mockFetch(fail({ code: 'UNKNOWN_STYLE', message: '알 수 없는 스타일: xxx' }))

    await expect(
      fetchTranslation({ text: '안녕', targetLang: '한국어', style: 'xxx' }),
    ).rejects.toMatchObject({ message: '알 수 없는 스타일: xxx', code: 'UNKNOWN_STYLE' })
  })

  it('error 필드가 없으면 기본 메시지로 대체한다', async () => {
    mockFetch(fail(undefined))

    await expect(
      fetchTranslation({ text: '안녕', targetLang: '한국어', style: 'general' }),
    ).rejects.toThrow('번역 요청이 실패했습니다.')
  })

  it('본문이 JSON이 아니어도 기본 메시지로 처리한다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        json: async () => {
          throw new Error('not json')
        },
      }),
    )

    await expect(
      fetchTranslation({ text: '안녕', targetLang: '한국어', style: 'general' }),
    ).rejects.toThrow('번역 요청이 실패했습니다.')
  })
})

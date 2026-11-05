import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setAlarmEnabled, useTabletAlarm } from '../lib/tabletAlarm'

let audioState: AudioContextState
let beeps: number

class FakeAudioContext {
  currentTime = 0
  destination = {}
  get state() {
    return audioState
  }
  resume() {
    return Promise.resolve()
  }
  createOscillator() {
    beeps += 1
    return { type: '', frequency: { value: 0 }, connect: (node: unknown) => node, start: vi.fn(), stop: vi.fn() }
  }
  createGain() {
    return {
      gain: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
      connect: (node: unknown) => node,
    }
  }
}

describe('tablet alarm', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('AudioContext', FakeAudioContext)
    audioState = 'running'
    beeps = 0
  })

  afterEach(() => {
    act(() => setAlarmEnabled(false))
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('stays silent until it is turned on for this device', () => {
    renderHook(() => useTabletAlarm(true))
    vi.advanceTimersByTime(10_000)
    expect(beeps).toBe(0)
  })

  it('repeats while an alert waits and stops when it is answered', () => {
    act(() => setAlarmEnabled(true))
    const { rerender } = renderHook(({ ring }) => useTabletAlarm(ring), { initialProps: { ring: true } })
    const afterFirst = beeps
    expect(afterFirst).toBeGreaterThan(0)

    act(() => vi.advanceTimersByTime(2400))
    expect(beeps).toBeGreaterThan(afterFirst)

    rerender({ ring: false })
    const afterStop = beeps
    act(() => vi.advanceTimersByTime(10_000))
    expect(beeps).toBe(afterStop)
  })

  it('says so when the browser is blocking the sound', () => {
    act(() => setAlarmEnabled(true))
    audioState = 'suspended'
    const { result } = renderHook(() => useTabletAlarm(true))
    expect(beeps).toBe(0)
    expect(result.current.blocked).toBe(true)
  })

  it('remembers the choice on this device', () => {
    act(() => setAlarmEnabled(true))
    expect(localStorage.getItem('tablet_alarm_on')).toBe('1')
    act(() => setAlarmEnabled(false))
    expect(localStorage.getItem('tablet_alarm_on')).toBe('0')
  })
})

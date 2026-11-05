import { useEffect, useSyncExternalStore } from 'react'

/**
 * A loud repeating alarm for a tablet or computer with DineOps SI open. It's off until someone
 * turns it on for this device, because browsers only allow sound after a tap on the page.
 */

const STORAGE_KEY = 'tablet_alarm_on'
const REPEAT_MS = 2400
const BEEPS: { frequency: number; start: number }[] = [
  { frequency: 988, start: 0 },
  { frequency: 784, start: 0.28 },
  { frequency: 988, start: 0.56 },
  { frequency: 784, start: 0.84 },
]

export interface AlarmState {
  enabled: boolean
  /** The alarm should be sounding, but the browser wants a tap first. */
  blocked: boolean
}

function readEnabled(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

let state: AlarmState = { enabled: readEnabled(), blocked: false }
const listeners = new Set<() => void>()
let audio: AudioContext | null = null
let timer: ReturnType<typeof setInterval> | undefined

function setState(next: AlarmState): void {
  if (next.enabled === state.enabled && next.blocked === state.blocked) return
  state = next
  listeners.forEach((listener) => listener())
}

function playOnce(context: AudioContext): void {
  for (const { frequency, start } of BEEPS) {
    const oscillator = context.createOscillator()
    const gain = context.createGain()
    const at = context.currentTime + start
    oscillator.type = 'square'
    oscillator.frequency.value = frequency
    gain.gain.setValueAtTime(0.25, at)
    gain.gain.exponentialRampToValueAtTime(0.001, at + 0.24)
    oscillator.connect(gain).connect(context.destination)
    oscillator.start(at)
    oscillator.stop(at + 0.24)
  }
}

function tick(): void {
  if (!audio) audio = new AudioContext()
  if (audio.state === 'suspended') void audio.resume()
  if (audio.state === 'running') {
    playOnce(audio)
    setState({ ...state, blocked: false })
  } else {
    setState({ ...state, blocked: true })
  }
}

function start(): void {
  if (timer !== undefined) return
  tick()
  timer = setInterval(tick, REPEAT_MS)
}

function stop(): void {
  clearInterval(timer)
  timer = undefined
  setState({ ...state, blocked: false })
}

/** Must be called from a tap, which is what gives the browser permission to play sound. */
export function setAlarmEnabled(enabled: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, enabled ? '1' : '0')
  } catch {
    // Still works until the page is reloaded.
  }
  if (enabled) {
    audio ??= new AudioContext()
    void audio.resume()
  } else {
    stop()
  }
  setState({ enabled, blocked: false })
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useAlarmState(): AlarmState {
  return useSyncExternalStore(subscribe, () => state)
}

/** Rings for as long as this device has the alarm on and any alert is waiting for a response. */
export function useTabletAlarm(shouldRing: boolean): AlarmState {
  const alarm = useAlarmState()
  const ringing = shouldRing && alarm.enabled

  useEffect(() => {
    if (!ringing) return
    start()
    return stop
  }, [ringing])

  useEffect(() => {
    if (!alarm.blocked) return
    const unblock = () => void audio?.resume().then(tick)
    window.addEventListener('pointerdown', unblock)
    return () => window.removeEventListener('pointerdown', unblock)
  }, [alarm.blocked])

  return alarm
}

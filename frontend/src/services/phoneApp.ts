import { Capacitor, registerPlugin } from '@capacitor/core'
import api from './api'

export interface PhoneStatus {
  firebaseReady: boolean
  notificationsAllowed: boolean
  ringEnabled: boolean
  batteryUnrestricted: boolean
}

interface DineOpsPushPlugin {
  status: () => Promise<PhoneStatus>
  requestPermission: () => Promise<PhoneStatus>
  getToken: () => Promise<{ token: string }>
  testRing: () => Promise<void>
  openNotificationSettings: () => Promise<void>
  openAppSettings: () => Promise<void>
}

export const phone = registerPlugin<DineOpsPushPlugin>('DineOpsPush')

export const isPhoneApp = (): boolean => Capacitor.isNativePlatform()

let registeredToken: string | null = null

/** Tells the server this phone should ring for whoever is signed in. */
export async function registerThisPhone(): Promise<PhoneStatus> {
  const status = await phone.requestPermission()
  if (status.firebaseReady) {
    const { token } = await phone.getToken()
    await api.post('/devices', { token })
    registeredToken = token
  }
  return status
}

/** Called at sign out, so the next person's phone doesn't ring for the last person's alerts. */
export async function unregisterThisPhone(): Promise<void> {
  if (!isPhoneApp()) return
  try {
    const token = registeredToken ?? (await phone.getToken()).token
    await api.post('/devices/unregister', { token })
  } catch {
    // Signing out must still work with no connection or no Firebase.
  }
  registeredToken = null
}

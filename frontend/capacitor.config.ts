import type { CapacitorConfig } from '@capacitor/cli'

// The app opens the live site, so screen fixes reach phones without a new install.
// The address is set when the app is built. Without one, it opens a built-in copy of the screens.
const serverUrl = process.env.CAP_SERVER_URL

const config: CapacitorConfig = {
  appId: 'com.dineopssi.app',
  appName: 'DineOps SI',
  webDir: 'dist',
  ...(serverUrl ? { server: { url: serverUrl, cleartext: false } } : {}),
}

export default config

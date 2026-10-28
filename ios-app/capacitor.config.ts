import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'com.aitradinglab.monitor',
  appName: 'AI Trading Lab',
  webDir: 'www',
  ios: {
    contentInset: 'automatic',
    limitsNavigationsToAppBoundDomains: false,
  },
  server: {
    // Local connect page → JS redirect to saved engine URL (local or cloud).
    // Navigation to any host is allowed (private engine deployment).
    cleartext: true,
  },
}

export default config

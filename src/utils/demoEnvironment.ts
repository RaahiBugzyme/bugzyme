/**
 * Safe Demo Mode Environment Utility
 *
 * Critical Safety Constraints:
 * 1. Demo profiles are strictly isolated and never written to the production database.
 * 2. Ordinary real users in production NEVER see demo profiles.
 * 3. Demo mode is only activated when explicitly requested via:
 *    - URL parameter `?demo=true` or `?demo=1`
 *    - localStorage item `raahi.demo_mode === 'true'`
 *    - Environment variable `VITE_ENABLE_DEMO_MODE === 'true'`
 */

export function isDemoModeEnabled(): boolean {
  // 1. Explicit URL parameter check (?demo=true / ?demo=1)
  try {
    const loc = typeof window !== 'undefined' ? window.location : (globalThis as unknown as { location?: Location }).location
    if (loc?.search) {
      const params = new URLSearchParams(loc.search)
      const demoParam = params.get('demo')
      if (demoParam === 'true' || demoParam === '1') {
        return true
      }
    }
  } catch {
    // location might not be available in non-browser runtimes
  }

  // 2. Explicit localStorage toggle
  try {
    const storage = typeof window !== 'undefined' ? window.localStorage : globalThis.localStorage
    if (storage?.getItem('raahi.demo_mode') === 'true') {
      return true
    }
  } catch {
    // localStorage may be disabled or unavailable
  }

  // 3. Explicit Vite environment variable
  try {
    const clientEnv = (import.meta as { env?: { VITE_ENABLE_DEMO_MODE?: string } }).env
    if (clientEnv?.VITE_ENABLE_DEMO_MODE === 'true') {
      return true
    }
  } catch {
    // ignore
  }

  return false
}

export function setDemoMode(enabled: boolean): void {
  try {
    const storage = typeof window !== 'undefined' ? window.localStorage : globalThis.localStorage
    if (enabled) {
      storage?.setItem('raahi.demo_mode', 'true')
    } else {
      storage?.removeItem('raahi.demo_mode')
    }
  } catch {
    // ignore
  }
}

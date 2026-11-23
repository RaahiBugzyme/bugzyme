import { describe, it } from 'node:test'
import assert from 'node:assert'
import fs from 'node:fs'
import path from 'node:path'
import { generationThemes } from '../src/data/generations.ts'

describe('Part 1: Global Theme Switching Architecture', () => {
  const themeContextTsx = fs.readFileSync(path.resolve('src/state/ThemeContext.tsx'), 'utf-8')
  const profilePageTsx = fs.readFileSync(path.resolve('src/pages/ProfilePage.tsx'), 'utf-8')
  const settingsPageTsx = fs.readFileSync(path.resolve('src/pages/SettingsPage.tsx'), 'utf-8')
  const settingsCss = fs.readFileSync(path.resolve('src/pages/settings.css'), 'utf-8')
  const mainCss = fs.readFileSync(path.resolve('src/styles/main.css'), 'utf-8')

  it('generationThemes defines distinct visual palettes for genz, zillenial, and millennial', () => {
    const keys = Object.keys(generationThemes)
    assert.deepStrictEqual(keys.sort(), ['genz', 'millennial', 'zillenial'].sort())

    // All eras have distinct primary and secondary colors
    assert.notStrictEqual(generationThemes.genz.primary, generationThemes.zillenial.primary)
    assert.notStrictEqual(generationThemes.genz.primary, generationThemes.millennial.primary)
    assert.notStrictEqual(generationThemes.zillenial.primary, generationThemes.millennial.primary)

    assert.ok(generationThemes.genz.emoji, 'genz has an emoji')
    assert.ok(generationThemes.zillenial.emoji, 'zillenial has an emoji')
    assert.ok(generationThemes.millennial.emoji, 'millennial has an emoji')
  })

  it('ThemeContext synchronizes data-theme and CSS variables to documentElement and document.body', () => {
    assert.ok(themeContextTsx.includes("document.documentElement.setAttribute('data-theme', generation)"), 'must set data-theme on html')
    assert.ok(themeContextTsx.includes("document.body.setAttribute('data-theme', generation)"), 'must set data-theme on body')
    assert.ok(themeContextTsx.includes("rootStyle.setProperty('--ep', curTheme.primary)"), 'must set --ep')
    assert.ok(themeContextTsx.includes("rootStyle.setProperty('--es', curTheme.secondary)"), 'must set --es')
    assert.ok(themeContextTsx.includes("rootStyle.setProperty('--glow', curTheme.glow)"), 'must set --glow')
    assert.ok(themeContextTsx.includes("rootStyle.setProperty('--cbg', curTheme.cardBackground)"), 'must set --cbg')
    assert.ok(themeContextTsx.includes("rootStyle.setProperty('--cbr', curTheme.cardBorder)"), 'must set --cbr')
    assert.ok(themeContextTsx.includes("rootStyle.setProperty('--bd', curTheme.background)"), 'must set --bd')
    assert.ok(themeContextTsx.includes("rootStyle.setProperty('--bg-deep', curTheme.background)"), 'must set --bg-deep')
    assert.ok(themeContextTsx.includes("document.body.style.backgroundColor = curTheme.background"), 'must set body background')
    assert.ok(themeContextTsx.includes("'raahiGenerationTheme.v1'"), 'must persist under raahiGenerationTheme.v1')
  })

  it('ProfilePage eliminates rogue theme resets on mount or backend profile fetch', () => {
    // Check that setGeneration is not called inside useEffect on profile load
    assert.ok(!profilePageTsx.includes('setGeneration(merged.era)'), 'must not reset era on merged profile')
    assert.ok(!profilePageTsx.includes('setGeneration(savedProfile.era)'), 'must not reset era on savedProfile change')
    // Ensure manual selection still works
    assert.ok(profilePageTsx.includes('setGeneration(era)'), 'manual era selector should update generation')
  })

  it('SettingsPage provides interactive theme selection for all generations with accessible radio buttons', () => {
    assert.ok(settingsPageTsx.includes('role="radiogroup" aria-label="Choose application theme"'), 'settings must have radiogroup')
    assert.ok(settingsPageTsx.includes('role="radio"'), 'settings must have role="radio"')
    assert.ok(settingsPageTsx.includes('aria-checked={isSelected}'), 'settings must indicate aria-checked')
    assert.ok(settingsPageTsx.includes('setGeneration(themeId)'), 'clicking an era option must call setGeneration')
    assert.ok(settingsPageTsx.includes('settings-theme-grid'), 'must render theme grid')
    assert.ok(settingsCss.includes('.settings-theme-grid'), 'settings.css must style theme grid')
    assert.ok(settingsCss.includes('.settings-theme-option'), 'settings.css must style theme options')
  })

  it('main.css defines theme-specific cascade tokens for genz, zillenial, and millennial', () => {
    assert.ok(mainCss.includes('[data-theme="genz"]'), 'main.css must define genz theme variables')
    assert.ok(mainCss.includes('[data-theme="zillenial"]'), 'main.css must define zillenial theme variables')
    assert.ok(mainCss.includes('[data-theme="millennial"]'), 'main.css must define millennial theme variables')
  })
})

describe('Part 2: Navigation Redesign – Hamburger Menu and Minimal Header', () => {
  const layoutTsx = fs.readFileSync(path.resolve('src/components/IntegrationLayout.tsx'), 'utf-8')
  const foundationCss = fs.readFileSync(path.resolve('src/components/integration-foundation.css'), 'utf-8')
  const matchesPagesTsx = fs.readFileSync(path.resolve('src/pages/MatchesPages.tsx'), 'utf-8')

  it('header contains ONLY Raahi logo on left and 3-line hamburger menu on right', () => {
    // Find the header element
    const headerMatch = layoutTsx.match(/<header className="integration-header">([\s\S]*?)<\/header>/)
    assert.ok(headerMatch, 'integration-header must exist')
    const headerContent = headerMatch[1]

    // Logo present
    assert.ok(headerContent.includes('integration-brand'), 'header must contain brand logo')
    assert.ok(headerContent.includes('to="/discover"'), 'logo must link to /discover')

    // Hamburger button present
    assert.ok(headerContent.includes('integration-hamburger-btn'), 'header must contain hamburger button')
    const lineMatches = headerContent.match(/className="hamburger-line"/g)
    assert.strictEqual(lineMatches?.length, 3, 'hamburger button must contain exactly 3 lines')

    // Direct navigation links removed from header
    assert.ok(!headerContent.includes('integration-nav'), 'direct integration-nav must be removed from header')
    assert.ok(!headerContent.includes('to="/matches"'), 'direct matches link must not be in header')
    assert.ok(!headerContent.includes('to="/conversations"'), 'direct chat link must not be in header')
    assert.ok(!headerContent.includes('to="/profile"'), 'direct profile link must not be in header')
    assert.ok(!headerContent.includes('to="/settings"'), 'direct settings link must not be in header')
  })

  it('slide-in navigation drawer contains Main Navigation, Preferences & Support, and Account Actions', () => {
    const drawerMatch = layoutTsx.match(/<aside[\s\S]*?className=\{`integration-drawer[\s\S]*?<\/aside>/)
    assert.ok(drawerMatch, 'integration-drawer aside must exist')
    const drawerContent = drawerMatch[0]

    // 1. Main Navigation
    assert.ok(drawerContent.includes('Main Navigation'), 'must include Main Navigation section heading')
    assert.ok(drawerContent.includes('to="/discover"'), 'must include Discover link')
    assert.ok(drawerContent.includes('to="/matches"'), 'must include Matches link')
    assert.ok(drawerContent.includes('to="/conversations"'), 'must include Chat link')
    assert.ok(drawerContent.includes('to="/profile"'), 'must include Profiles link')

    // Verify Main Navigation icons
    assert.ok(drawerContent.includes('🧭'), 'Discover must have compass icon 🧭')
    assert.ok(drawerContent.includes('💖'), 'Matches must have heart icon 💖')
    assert.ok(drawerContent.includes('💬'), 'Chat must have chat bubble icon 💬')
    assert.ok(drawerContent.includes('👤'), 'Profiles must have user icon 👤')

    // 2. Preferences & Support
    assert.ok(drawerContent.includes('Preferences & Support'), 'must include Preferences & Support section heading')
    assert.ok(drawerContent.includes('to="/settings"'), 'must include Settings link')
    assert.ok(drawerContent.includes('to="/privacy"'), 'must include Privacy & Safety link')
    assert.ok(drawerContent.includes('to="/help"'), 'must include Help & Support link')

    // Verify Preferences & Support icons
    assert.ok(drawerContent.includes('⚙️'), 'Settings must have gear icon ⚙️')
    assert.ok(drawerContent.includes('🛡️'), 'Privacy must have shield icon 🛡️')
    assert.ok(drawerContent.includes('🛟'), 'Help must have lifebuoy icon 🛟')

    // 3. Account Actions & Logout
    assert.ok(drawerContent.includes('Account Actions'), 'must include Account Actions section heading')
    assert.ok(drawerContent.includes('drawer-logout-item'), 'must include drawer-logout-item button')
    assert.ok(drawerContent.includes('Logout'), 'must include Logout label')
    assert.ok(drawerContent.includes('🚪'), 'Logout must have door icon 🚪')

    // Subtle dividers
    const dividerMatches = drawerContent.match(/drawer-divider/g)
    assert.ok(dividerMatches && dividerMatches.length >= 2, 'must include subtle dividers between groups')

    // Total navigation/action links in drawer is 7 links + 1 logout action button = 8 items
    const navItemMatches = drawerContent.match(/drawer-nav-item/g)
    assert.strictEqual(navItemMatches?.length, 8, 'drawer must contain exactly 8 items (4 main + 3 pref/support + 1 logout)')
  })

  it('implements theme-styled logout confirmation dialog with cancel and confirm handlers', () => {
    assert.ok(layoutTsx.includes('logout-modal-backdrop'), 'must render logout modal backdrop')
    assert.ok(layoutTsx.includes('logout-modal-card'), 'must render logout modal card')
    assert.ok(layoutTsx.includes('Log Out of Raahi?'), 'dialog must prompt Log Out of Raahi?')
    assert.ok(layoutTsx.includes('logout-btn-cancel'), 'dialog must have cancel button')
    assert.ok(layoutTsx.includes('logout-btn-confirm'), 'dialog must have confirm button')
    assert.ok(layoutTsx.includes('logout()'), 'confirming logout must invoke auth logout')

    // Modal CSS in foundation
    assert.ok(foundationCss.includes('.logout-modal-backdrop'), 'foundation CSS must style modal backdrop')
    assert.ok(foundationCss.includes('.logout-modal-card'), 'foundation CSS must style modal card with theme variables')
    assert.ok(foundationCss.includes('.drawer-logout-item'), 'foundation CSS must style logout item with red/pink accent')
  })

  it('provides dedicated Privacy & Safety and Help & Support routes and pages', () => {
    const privacyPath = path.resolve('src/pages/PrivacySafetyPage.tsx')
    const helpPath = path.resolve('src/pages/HelpSupportPage.tsx')
    const privacyHelpCssPath = path.resolve('src/pages/privacy-help.css')
    const appTsx = fs.readFileSync(path.resolve('src/App.tsx'), 'utf-8')

    assert.ok(fs.existsSync(privacyPath), 'PrivacySafetyPage.tsx must exist')
    assert.ok(fs.existsSync(helpPath), 'HelpSupportPage.tsx must exist')
    assert.ok(fs.existsSync(privacyHelpCssPath), 'privacy-help.css must exist')

    assert.ok(appTsx.includes('path="/privacy"'), 'App.tsx must route /privacy')
    assert.ok(appTsx.includes('path="/help"'), 'App.tsx must route /help')
  })

  it('drawer implements slide-in animations, backdrop, Escape key, auto-close, and scroll lock', () => {
    // Backdrop
    assert.ok(layoutTsx.includes('integration-drawer-backdrop'), 'must include drawer backdrop')
    assert.ok(layoutTsx.includes("onClick={() => setDrawerOpen(false)}"), 'backdrop click must close drawer')

    // Close button inside drawer
    assert.ok(layoutTsx.includes('integration-drawer-close'), 'must include close button inside drawer')

    // Escape key handling
    assert.ok(layoutTsx.includes("e.key === 'Escape'"), 'must listen for Escape key to close drawer')

    // Body scroll lock
    assert.ok(layoutTsx.includes("document.body.style.overflow = 'hidden'"), 'must lock body overflow when drawer is open')

    // Route auto-close
    assert.ok(layoutTsx.includes('setDrawerOpen(false)'), 'must close drawer upon route change')

    // Foundation CSS slide-in and backdrop styles
    assert.ok(foundationCss.includes('.integration-drawer'), 'foundation css must have drawer styles')
    assert.ok(foundationCss.includes('.integration-drawer.open'), 'foundation css must have drawer.open transform')
    assert.ok(foundationCss.includes('.integration-drawer-backdrop'), 'foundation css must have backdrop styles')
    assert.ok(foundationCss.includes('.drawer-nav-item.active'), 'foundation css must have active item styling')
  })

  it('eliminates redundant navigation bars across the application', () => {
    // No redundant mobile bottom nav bar in IntegrationLayout
    assert.ok(!layoutTsx.includes('app-mobile-nav-bar'), 'IntegrationLayout must not render app-mobile-nav-bar')

    // No redundant matches-bottom-bar in MatchesPages
    assert.ok(!matchesPagesTsx.includes('matches-bottom-bar'), 'MatchesPages must not render matches-bottom-bar')
  })
})

import { describe, it } from 'node:test'
import assert from 'node:assert'
import fs from 'node:fs'
import path from 'node:path'

describe('Onboarding Steps 1 and 2 List Layout Alignment', () => {
  const onboardingCss = fs.readFileSync(path.resolve('src/styles/onboarding-flow.css'), 'utf-8')
  const onboardingPageTsx = fs.readFileSync(path.resolve('src/pages/OnboardingPage.tsx'), 'utf-8')

  it('onboarding-flow.css configures .onboarding-choice-grid as a full-width vertical list', () => {
    assert.match(onboardingCss, /\.onboarding-choice-grid\s*\{[^}]*display:\s*flex;/, 'choice grid must use flex display')
    assert.match(onboardingCss, /\.onboarding-choice-grid\s*\{[^}]*flex-direction:\s*column;/, 'choice grid must be a column list')
    assert.match(onboardingCss, /\.onboarding-choice-grid\s*\{[^}]*gap:\s*12px;/, 'choice grid must match Step 3 12px gap')
    assert.match(onboardingCss, /\.onboarding-choice-grid\s*\{[^}]*width:\s*100%;/, 'choice grid must be 100% width')
  })

  it('onboarding-flow.css configures .onboarding-choice to match Step 3 row card layout', () => {
    assert.match(onboardingCss, /\.onboarding-choice\s*\{[^}]*display:\s*flex;/, 'choice card must use flex display')
    assert.match(onboardingCss, /\.onboarding-choice\s*\{[^}]*align-items:\s*center;/, 'choice card must align items center')
    assert.match(onboardingCss, /\.onboarding-choice\s*\{[^}]*min-height:\s*72px;/, 'choice card must match Step 3 min-height 72px')
    assert.match(onboardingCss, /\.onboarding-choice\s*\{[^}]*padding:\s*16px;/, 'choice card must match Step 3 padding 16px')
    assert.match(onboardingCss, /\.onboarding-choice\s*\{[^}]*border-radius:\s*18px;/, 'choice card must match Step 3 border radius 18px')
  })

  it('onboarding-flow.css includes radio indicator animations and selection states', () => {
    assert.match(onboardingCss, /\.onboarding-choice\s*\.match-radio-v3::after/, 'must include radio button pseudo-element styling')
    assert.match(onboardingCss, /\.onboarding-choice\.selected\s*\.match-radio-v3::after/, 'must activate radio indicator on selection')
    assert.match(onboardingCss, /match-era-bounce/, 'must use match-era-bounce animation')
  })

  it('OnboardingPage.tsx renders Step 1 and Step 2 using Step 3 row layout components', () => {
    // Step 1 check
    assert.ok(onboardingPageTsx.includes('role="radiogroup" aria-label="Pick your era"'), 'Step 1 must have accessible radiogroup')
    assert.ok(onboardingPageTsx.includes('match-emoji-wrap-v3'), 'Step 1 and 2 must use match-emoji-wrap-v3')
    assert.ok(onboardingPageTsx.includes('match-info-v3'), 'Step 1 and 2 must use match-info-v3')
    assert.ok(onboardingPageTsx.includes('match-name-v3'), 'Step 1 and 2 must use match-name-v3')
    assert.ok(onboardingPageTsx.includes('match-desc-v3'), 'Step 1 and 2 must use match-desc-v3')
    assert.ok(onboardingPageTsx.includes('match-radio-v3'), 'Step 1 and 2 must use match-radio-v3')
    assert.ok(onboardingPageTsx.includes('role="radio"'), 'Step 1 and 2 buttons must have role radio')
    assert.ok(onboardingPageTsx.includes('aria-checked={selectedEra === id}'), 'Step 1 buttons must have aria-checked')
    assert.ok(onboardingPageTsx.includes('aria-checked={draft.vibe === vibe.name}'), 'Step 2 buttons must have aria-checked')
  })

  it('preserves Step 3 and Step 4 without modification', () => {
    assert.ok(onboardingPageTsx.includes('className="match-grid-v3" role="radiogroup"'), 'Step 3 match-grid-v3 must be intact')
    assert.ok(onboardingPageTsx.includes('className="onboarding-profile-form"'), 'Step 4 onboarding-profile-form must be intact')
  })
})

import { describe, it } from 'node:test'
import assert from 'node:assert'
import fs from 'node:fs'
import path from 'node:path'

describe('Batch 1 Responsive Design Fixes', () => {
  const onboardingCss = fs.readFileSync(path.resolve('src/styles/onboarding-flow.css'), 'utf-8')
  const verificationCss = fs.readFileSync(path.resolve('src/styles/verification-v3.css'), 'utf-8')
  const matchesCss = fs.readFileSync(path.resolve('src/styles/matches.css'), 'utf-8')
  const loginTsx = fs.readFileSync(path.resolve('src/pages/LoginPage.tsx'), 'utf-8')
  const registerTsx = fs.readFileSync(path.resolve('src/pages/RegisterPage.tsx'), 'utf-8')
  const forgotPasswordTsx = fs.readFileSync(path.resolve('src/pages/ForgotPasswordPage.tsx'), 'utf-8')
  const resetPasswordTsx = fs.readFileSync(path.resolve('src/pages/ResetPasswordPage.tsx'), 'utf-8')
  const phoneAuthTsx = fs.readFileSync(path.resolve('src/components/PhoneAuth.tsx'), 'utf-8')

  it('Onboarding scroll fix: ensures vertical scrolling and eliminates overflow:hidden blocker', () => {
    assert.match(onboardingCss, /overflow-y:\s*auto/, 'onboarding-flow must permit vertical scrolling')
    assert.match(onboardingCss, /overflow-x:\s*hidden/, 'onboarding-flow must prevent horizontal overflow')
    assert.doesNotMatch(onboardingCss, /\.onboarding-flow\s*\{[^}]*overflow:\s*hidden/, '.onboarding-flow root must not have overflow:hidden')
    assert.match(onboardingCss, /padding-bottom/, 'onboarding-flow must have bottom padding for reachability')
    assert.match(onboardingCss, /font-size:\s*16px/, 'onboarding form inputs must specify 16px to prevent iOS auto-zoom')
  })

  it('Verification page scroll fix: ensures content can scroll and submit controls are reachable', () => {
    assert.match(verificationCss, /overflow-y:\s*auto/, 'verification screen must permit vertical scrolling')
    assert.match(verificationCss, /overflow-x:\s*hidden/, 'verification screen must prevent horizontal overflow')
    assert.match(verificationCss, /padding-bottom/, 'verification screen must have adequate bottom padding')
  })

  it('Authentication responsiveness: matches.css provides auth page padding and 16px input font size', () => {
    assert.match(matchesCss, /\.matches-auth-page/, 'matches.css must include .matches-auth-page')
    assert.match(matchesCss, /font-size:\s*16px\s*!important/, 'matches.css must enforce at least 16px on inputs to prevent iOS Safari auto-zoom')
    assert.match(matchesCss, /\.auth-method-switcher/, 'matches.css must define responsive auth-method-switcher')
    assert.match(matchesCss, /\.auth-method-tab/, 'matches.css must define responsive auth-method-tab')
    assert.match(matchesCss, /\.recovery-method-option/, 'matches.css must define responsive recovery-method-option')
    assert.match(matchesCss, /\.auth-action-row/, 'matches.css must define responsive auth-action-row')
  })

  it('Authentication pages integrate responsive layout and switcher classes', () => {
    assert.ok(loginTsx.includes('matches-auth-page'), 'LoginPage must use matches-auth-page')
    assert.ok(loginTsx.includes('auth-method-switcher'), 'LoginPage must use auth-method-switcher')
    assert.ok(loginTsx.includes('auth-method-tab'), 'LoginPage must use auth-method-tab')

    assert.ok(registerTsx.includes('matches-auth-page'), 'RegisterPage must use matches-auth-page')
    assert.ok(registerTsx.includes('auth-method-switcher'), 'RegisterPage must use auth-method-switcher')
    assert.ok(registerTsx.includes('auth-method-tab'), 'RegisterPage must use auth-method-tab')

    assert.ok(forgotPasswordTsx.includes('matches-auth-page'), 'ForgotPasswordPage must use matches-auth-page')
    assert.ok(forgotPasswordTsx.includes('recovery-method-option'), 'ForgotPasswordPage must use recovery-method-option')
    assert.ok(forgotPasswordTsx.includes('auth-action-row'), 'ForgotPasswordPage must use auth-action-row')

    assert.ok(resetPasswordTsx.includes('matches-auth-page'), 'ResetPasswordPage must use matches-auth-page')
    assert.ok(phoneAuthTsx.includes('auth-action-row'), 'PhoneAuth must use auth-action-row')
  })
})

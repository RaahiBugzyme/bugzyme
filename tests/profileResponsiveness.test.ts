import assert from 'node:assert/strict'
import test from 'node:test'
import fs from 'node:fs'
import path from 'node:path'

const cssContent = fs.readFileSync(path.resolve('src/pages/profile.css'), 'utf-8')
const pageContent = fs.readFileSync(path.resolve('src/pages/ProfilePage.tsx'), 'utf-8')

test('profile.css contains required responsive breakpoints for mobile, tablet, and desktop', () => {
  // Mobile breakpoints
  assert.ok(cssContent.includes('@media (max-width: 400px)'), 'Should include compact mobile breakpoint (360px-390px)')
  assert.ok(cssContent.includes('@media (max-width: 640px)'), 'Should include mobile breakpoint (430px)')

  // Tablet breakpoints
  assert.ok(cssContent.includes('@media (max-width: 860px)'), 'Should include tablet portrait breakpoint (768px)')
  assert.ok(cssContent.includes('@media (max-width: 1024px)'), 'Should include tablet landscape breakpoint (1024px)')

  // Desktop default styling
  assert.ok(cssContent.includes('.profile-view-grid'), 'Should define desktop two-column grid')
  assert.ok(cssContent.includes('max-width: 1140px'), 'Should define desktop max-width container')
})

test('buttons conform to touch target accessibility standards (min-height >= 44px)', () => {
  assert.match(cssContent, /min-height:\s*44px/, 'Profile buttons should have min-height of 44px')
  assert.ok(cssContent.includes('touch-action: manipulation'), 'Buttons should have touch-action manipulation')
})

test('Profile cover and photo grid adapt responsively for mobile and desktop', () => {
  // Desktop prominence
  assert.match(cssContent, /\.profile-cover\s*\{[^}]*height:\s*clamp\(380px/s, 'Desktop cover should have prominent height')

  // Mobile cover full width adapt
  assert.match(cssContent, /@media \(max-width: 640px\)[\s\S]*?\.profile-cover\s*\{[^}]*height:\s*clamp\(330px/s, 'Mobile cover should adapt to viewport width')

  // Photo grid columns
  assert.match(cssContent, /\.profile-photo-grid\s*\{[^}]*grid-template-columns:\s*repeat\(4/s, 'Desktop photo grid should have 4 columns')
  assert.match(cssContent, /@media \(max-width: 640px\)[\s\S]*?\.profile-photo-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2/s, 'Mobile photo grid should adapt to 2 columns')
})

test('Edit profile fields and inputs prevent overflow and fit viewports', () => {
  // Field grid 2 cols on desktop, 1 col on mobile
  assert.match(cssContent, /\.profile-field-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2/s, 'Desktop field grid should have 2 columns')
  assert.match(cssContent, /@media \(max-width: 640px\)[\s\S]*?\.profile-field-grid\s*\{[^}]*grid-template-columns:\s*1fr/s, 'Mobile field grid should stack to 1 column')

  // 16px font-size to prevent iOS Safari auto-zoom
  assert.match(cssContent, /font-size:\s*16px/, 'Mobile form inputs should use 16px font size to prevent iOS zoom')

  // Submit actions stack cleanly on mobile
  assert.match(cssContent, /\.profile-submit-actions/, 'Submit actions should be styled cleanly')
  assert.match(cssContent, /flex-direction:\s*column-reverse/, 'Mobile submit actions should stack with primary button on top')
})

test('ProfilePage markup includes responsive layout classes', () => {
  assert.ok(pageContent.includes('className="profile-heading-actions"'), 'Should use profile-heading-actions class')
  assert.ok(pageContent.includes('className="profile-photo-grid profile-gallery-grid"'), 'Should use profile-gallery-grid class')
  assert.ok(pageContent.includes('className="profile-gallery-thumb"'), 'Should use profile-gallery-thumb class')
  assert.ok(pageContent.includes('className="profile-submit-actions"'), 'Should use profile-submit-actions class')
})

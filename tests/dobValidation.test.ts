import assert from 'node:assert/strict'
import test from 'node:test'
import {
  validateDateOfBirth,
  mapApiValidationErrors,
  getLocalDateString,
  getMaxSelectableDob,
} from '../src/utils/dobValidation.ts'
import { ApiError } from '../src/api/client.ts'

test('DOB validation rejects invalid, empty, or unparseable dates with friendly message', () => {
  const invalidInputs = [
    '',
    '   ',
    'not-a-date',
    '2000-13-01', // invalid month
    '2000-00-10', // invalid month
    '2000-01-32', // invalid day
    '2001-02-29', // not a leap year
    '1899-12-31', // before 1900
    '0000-00-00',
    '2000/01/01', // wrong separator
    '01-01-2000', // wrong format
  ]

  for (const input of invalidInputs) {
    const result = validateDateOfBirth(input)
    assert.equal(result.valid, false, `Expected ${input} to be invalid`)
    assert.equal(result.error, 'Please enter a valid date of birth.')
  }
})

test('DOB validation rejects future dates with specific friendly message', () => {
  const refDate = new Date(2026, 10, 19) // 2026-11-19

  const futureDates = [
    '2026-11-20', // tomorrow
    '2026-12-01', // next month
    '2027-01-01', // next year
    '2030-05-15', // far future
  ]

  for (const input of futureDates) {
    const result = validateDateOfBirth(input, refDate)
    assert.equal(result.valid, false, `Expected ${input} to be rejected as future`)
    assert.equal(result.error, 'Date of birth cannot be in the future.')
  }
})

test('DOB validation enforces minimum age of 18 with accurate birthday calculation', () => {
  // Reference date: November 19, 2026
  const refDate = new Date(2026, 10, 19)

  // Underage cases (under 18)
  const underageCases = [
    '2026-11-19', // today (age 0)
    '2020-05-10', // age 6
    '2009-01-01', // age 17
    '2008-11-20', // turning 18 tomorrow (age 17)
    '2008-12-01', // turning 18 next month (age 17)
  ]

  for (const input of underageCases) {
    const result = validateDateOfBirth(input, refDate)
    assert.equal(result.valid, false, `Expected ${input} to be rejected as under 18`)
    assert.equal(result.error, 'You must be at least 18 years old to use Raahi.')
  }

  // Exactly 18 or older cases
  const validCases = [
    '2008-11-19', // exactly 18 today!
    '2008-11-18', // turned 18 yesterday
    '2008-01-01', // turned 18 earlier this year
    '2004-02-29', // leap day baby (age 22 in 2026)
    '2000-06-15', // age 26
    '1995-12-31', // age 30
  ]

  for (const input of validCases) {
    const result = validateDateOfBirth(input, refDate)
    assert.equal(result.valid, true, `Expected ${input} to be valid`)
    assert.equal(result.error, null)
  }
})

test('mapApiValidationErrors maps FastAPI 422 detail array to friendly field errors', () => {
  const pydanticAgeError = {
    detail: [
      {
        loc: ['body', 'date_of_birth'],
        msg: 'Value error, User must be at least 18 years old',
        type: 'value_error',
      },
    ],
  }

  const result1 = mapApiValidationErrors(pydanticAgeError)
  assert.equal(result1.fieldErrors.date_of_birth, 'You must be at least 18 years old to use Raahi.')
  assert.equal(result1.generalMessage, 'You must be at least 18 years old to use Raahi.')

  const pydanticIsoError = {
    detail: [
      {
        loc: ['body', 'date_of_birth'],
        msg: 'date_of_birth must be a valid ISO date (YYYY-MM-DD)',
        type: 'value_error',
      },
    ],
  }

  const result2 = mapApiValidationErrors(pydanticIsoError)
  assert.equal(result2.fieldErrors.date_of_birth, 'Please enter a valid date of birth.')
  assert.equal(result2.generalMessage, 'Please enter a valid date of birth.')

  const otherFieldError = {
    detail: [
      {
        loc: ['body', 'city'],
        msg: 'String should have at most 60 characters',
        type: 'string_too_long',
      },
    ],
  }

  const result3 = mapApiValidationErrors(otherFieldError)
  assert.equal(result3.fieldErrors.city, 'String should have at most 60 characters')
  assert.equal(result3.generalMessage, 'String should have at most 60 characters')
})

test('mapApiValidationErrors maps string detail 422 gracefully without exposing raw 422', () => {
  const stringAgeError = {
    detail: 'User must be at least 18 years old',
  }

  const result = mapApiValidationErrors(stringAgeError)
  assert.equal(result.fieldErrors.date_of_birth, 'You must be at least 18 years old to use Raahi.')
  assert.doesNotMatch(result.generalMessage, /422|Unprocessable/i)

  const emptyError = {
    detail: [],
  }
  const resultEmpty = mapApiValidationErrors(emptyError)
  assert.doesNotMatch(resultEmpty.generalMessage, /422|Unprocessable/i)
  assert.equal(resultEmpty.generalMessage, 'Please check the information you entered and try again.')
})

test('getLocalDateString returns local YYYY-MM-DD without UTC conversion offset', () => {
  const testDate = new Date(2026, 4, 9) // May 9, 2026
  assert.equal(getLocalDateString(testDate), '2026-05-09')

  const testDate2 = new Date(2026, 11, 25) // Dec 25, 2026
  assert.equal(getLocalDateString(testDate2), '2026-12-25')
})

test('getMaxSelectableDob returns date exactly 18 years before reference date', () => {
  // Nov 19, 2026 -> max selectable is Nov 19, 2008
  const testDate1 = new Date(2026, 10, 19)
  assert.equal(getMaxSelectableDob(testDate1), '2008-11-19')

  // Jan 1, 2025 -> max selectable is Jan 1, 2007
  const testDate2 = new Date(2025, 0, 1)
  assert.equal(getMaxSelectableDob(testDate2), '2007-01-01')

  // Leap year boundary: Feb 29, 2024 (18 years ago was 2006, non-leap year) -> clamped to Feb 28, 2006
  const leapDate = new Date(2024, 1, 29)
  assert.equal(getMaxSelectableDob(leapDate), '2006-02-28')
})

test('Exact 18th birthday boundary validation', () => {
  const refDate = new Date(2026, 10, 19) // Nov 19, 2026

  // Exactly on 18th birthday: eligible!
  const birthdayToday = validateDateOfBirth('2008-11-19', refDate)
  assert.equal(birthdayToday.valid, true)
  assert.equal(birthdayToday.error, null)

  // Day after 18th birthday: 18 years and 1 day old: eligible!
  const turnedYesterday = validateDateOfBirth('2008-11-18', refDate)
  assert.equal(turnedYesterday.valid, true)
  assert.equal(turnedYesterday.error, null)

  // Day before 18th birthday: 17 years and 364 days old: under 18!
  const turnsTomorrow = validateDateOfBirth('2008-11-20', refDate)
  assert.equal(turnsTomorrow.valid, false)
  assert.equal(turnsTomorrow.error, 'You must be at least 18 years old to use Raahi.')
})

test('DOB input CSS prevents overflow on mobile with box-sizing border-box and max-width 100%', async () => {
  const fs = await import('node:fs')
  const path = await import('node:path')
  const css = fs.readFileSync(path.resolve('src/styles/onboarding-flow.css'), 'utf-8')
  const dobRuleMatch = css.match(/\.onboarding-profile-form input\[type="date"\]\s*\{([^}]+)\}/)
  assert.ok(dobRuleMatch, 'DOB rule must exist in onboarding-flow.css')
  const ruleBody = dobRuleMatch[1]
  assert.match(ruleBody, /box-sizing:\s*border-box/, 'DOB input must explicitly set box-sizing: border-box')
  assert.match(ruleBody, /max-width:\s*100%/, 'DOB input must explicitly set max-width: 100%')
})

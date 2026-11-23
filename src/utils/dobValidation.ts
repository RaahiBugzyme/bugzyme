export interface DobValidationResult {
  valid: boolean
  error: string | null
}

export interface ApiValidationMapping {
  fieldErrors: Record<string, string>
  generalMessage: string
}

/**
 * Returns YYYY-MM-DD for a given date in local time (avoiding UTC offset bugs).
 */
export function getLocalDateString(date: Date = new Date()): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/**
 * Returns YYYY-MM-DD for the date exactly 18 years before today in local time.
 * This represents the maximum selectable birthdate (a user becomes eligible on their 18th birthday).
 */
export function getMaxSelectableDob(referenceDate: Date = new Date()): string {
  const targetYear = referenceDate.getFullYear() - 18
  const targetMonth = referenceDate.getMonth()
  const targetDay = referenceDate.getDate()

  const d = new Date(targetYear, targetMonth, targetDay)
  // Handle Feb 29 leap year boundary: if 18 years ago was not a leap year, clamp to Feb 28
  if (d.getMonth() !== targetMonth) {
    d.setDate(0)
  }
  return getLocalDateString(d)
}

/**
 * Validates date of birth string:
 * - Must be a valid YYYY-MM-DD calendar date
 * - Cannot be in the future
 * - Must be at least 18 years old based on accurate birthday calculation
 */
export function validateDateOfBirth(
  dob: string | null | undefined,
  referenceDate: Date = new Date()
): DobValidationResult {
  if (!dob || typeof dob !== 'string' || !dob.trim()) {
    return { valid: false, error: 'Please enter a valid date of birth.' }
  }

  const trimmed = dob.trim()
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(trimmed)
  if (!match) {
    return { valid: false, error: 'Please enter a valid date of birth.' }
  }

  const year = parseInt(match[1], 10)
  const month = parseInt(match[2], 10)
  const day = parseInt(match[3], 10)

  if (year < 1900 || month < 1 || month > 12 || day < 1 || day > 31) {
    return { valid: false, error: 'Please enter a valid date of birth.' }
  }

  // Check actual calendar validity (e.g. leap years, 30-day months)
  const dateObj = new Date(year, month - 1, day)
  if (
    dateObj.getFullYear() !== year ||
    dateObj.getMonth() !== month - 1 ||
    dateObj.getDate() !== day
  ) {
    return { valid: false, error: 'Please enter a valid date of birth.' }
  }

  const refYear = referenceDate.getFullYear()
  const refMonth = referenceDate.getMonth() + 1
  const refDay = referenceDate.getDate()

  // Future date check
  const isFuture =
    year > refYear ||
    (year === refYear && month > refMonth) ||
    (year === refYear && month === refMonth && day > refDay)

  if (isFuture) {
    return { valid: false, error: 'Date of birth cannot be in the future.' }
  }

  // Calculate age accurately (must be 18 on or before reference date)
  let age = refYear - year
  if (refMonth < month || (refMonth === month && refDay < day)) {
    age--
  }

  if (age < 18) {
    return { valid: false, error: 'You must be at least 18 years old to use Raahi.' }
  }

  return { valid: true, error: null }
}

/**
 * Inspects API error payload (particularly HTTP 422) and maps validation issues
 * into readable field-level and general user messages without exposing raw 422 details.
 */
export function mapApiValidationErrors(payload: unknown): ApiValidationMapping {
  const fieldErrors: Record<string, string> = {}
  let generalMessage = 'Please check the information you entered and try again.'

  if (!payload || typeof payload !== 'object') {
    return { fieldErrors, generalMessage }
  }

  const detail = 'detail' in payload ? (payload as { detail: unknown }).detail : payload

  if (typeof detail === 'string') {
    const lower = detail.toLowerCase()
    if (lower.includes('18') || lower.includes('at least')) {
      fieldErrors.date_of_birth = 'You must be at least 18 years old to use Raahi.'
      generalMessage = fieldErrors.date_of_birth
    } else if (lower.includes('future')) {
      fieldErrors.date_of_birth = 'Date of birth cannot be in the future.'
      generalMessage = fieldErrors.date_of_birth
    } else if (lower.includes('date_of_birth') || lower.includes('iso date')) {
      fieldErrors.date_of_birth = 'Please enter a valid date of birth.'
      generalMessage = fieldErrors.date_of_birth
    } else {
      generalMessage = detail
    }
    return { fieldErrors, generalMessage }
  }

  if (Array.isArray(detail)) {
    const messages: string[] = []

    for (const item of detail) {
      if (!item || typeof item !== 'object') continue

      const loc = Array.isArray(item.loc) ? item.loc : []
      const field = loc.length > 0 ? String(loc[loc.length - 1]) : ''
      const rawMsg =
        typeof item.msg === 'string'
          ? item.msg
          : typeof item.message === 'string'
            ? item.message
            : ''
      const cleanMsg = rawMsg.replace(/^Value error,\s*/i, '').trim()

      if (field === 'date_of_birth' || rawMsg.toLowerCase().includes('date_of_birth')) {
        const lower = rawMsg.toLowerCase()
        let mapped = 'Please enter a valid date of birth.'
        if (lower.includes('18') || lower.includes('at least')) {
          mapped = 'You must be at least 18 years old to use Raahi.'
        } else if (lower.includes('future')) {
          mapped = 'Date of birth cannot be in the future.'
        }
        fieldErrors.date_of_birth = mapped
        messages.push(mapped)
      } else if (field) {
        const userFriendly = cleanMsg || `Invalid ${field.replace(/_/g, ' ')}`
        fieldErrors[field] = userFriendly
        messages.push(userFriendly)
      } else if (cleanMsg) {
        messages.push(cleanMsg)
      }
    }

    if (messages.length > 0) {
      generalMessage = messages[0]
    }
  }

  return { fieldErrors, generalMessage }
}

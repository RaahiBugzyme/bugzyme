import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { Card } from '../components/Card'
import { LoadingState } from '../components/LoadingState'
import { PageContainer } from '../components/PageContainer'
import { searchProfiles, submitSwipe, type SearchCandidate, type SearchParams } from '../api/discover'
import { resolveMediaUrl } from '../api/client'
import { isDemoModeEnabled } from '../utils/demoEnvironment'
import { FIVE_DEMO_PROFILES } from '../data/demoProfiles'
import { swipeDemoCandidate } from '../data/demoAppData'
import '../styles/search.css'

const POPULAR_INTERESTS = [
  'Travel', 'Coffee', 'Music', 'Reading', 'Photography', 'Bollywood',
  'Foodie', 'Fitness', 'Art', 'Tech', 'Dogs', 'Cats', 'Cinema', 'Cricket', 'Cooking'
]

const RELATIONSHIP_OPTIONS = [
  { value: '', label: 'Any intention' },
  { value: 'Long-term relationship', label: 'Long-term relationship' },
  { value: 'Short-term relationship', label: 'Short-term relationship' },
  { value: 'Casual dating', label: 'Casual dating' },
  { value: 'Marriage / Matrimony', label: 'Marriage / Matrimony' },
  { value: 'Friendship first', label: 'Friendship first' },
  { value: 'Not sure yet', label: 'Not sure yet' },
]

const ERA_OPTIONS = [
  { value: '', label: 'All generations' },
  { value: 'genz', label: 'Gen Z' },
  { value: 'zillenial', label: 'Zillennial' },
  { value: 'millennial', label: 'Millennial' },
]

function filterDemoCandidates(params: SearchParams): SearchCandidate[] {
  const qLower = params.q?.toLowerCase()
  const cityLower = params.city?.toLowerCase()
  const professionLower = params.profession?.toLowerCase()
  const intentionLower = params.relationship_intentions?.toLowerCase()

  return FIVE_DEMO_PROFILES.filter(profile => {
    if (qLower) {
      const matchName = profile.name.toLowerCase().includes(qLower)
      const matchCity = profile.city.toLowerCase().includes(qLower)
      const matchProf = (profile.profession || '').toLowerCase().includes(qLower)
      const matchEdu = (profile.education || '').toLowerCase().includes(qLower)
      const matchBio = (profile.bio || '').toLowerCase().includes(qLower)
      const matchInterests = profile.interests.some(i => i.toLowerCase().includes(qLower))
      if (!matchName && !matchCity && !matchProf && !matchEdu && !matchBio && !matchInterests) {
        return false
      }
    }
    if (cityLower && !profile.city.toLowerCase().includes(cityLower)) {
      return false
    }
    if (professionLower && !(profile.profession || '').toLowerCase().includes(professionLower)) {
      return false
    }
    if (intentionLower && !(profile.relationshipIntentions || '').toLowerCase().includes(intentionLower)) {
      return false
    }
    if (params.era && profile.era !== params.era) {
      return false
    }
    if (params.min_age !== undefined && (profile.age === null || profile.age < params.min_age)) {
      return false
    }
    if (params.max_age !== undefined && (profile.age === null || profile.age > params.max_age)) {
      return false
    }
    if (params.interests && params.interests.length > 0) {
      const hasInterests = params.interests.every(req =>
        profile.interests.some(pi => pi.toLowerCase().includes(req.toLowerCase()))
      )
      if (!hasInterests) return false
    }
    return true
  }).map(p => ({
    user_id: p.id,
    username: p.name.toLowerCase().replace(/\s+/g, '_'),
    full_name: p.name,
    age: p.age ?? 22,
    city: p.city,
    era: p.era,
    vibe_tag: p.vibeTag || null,
    bio: p.bio || '',
    profession: p.profession || '',
    education: p.education || '',
    relationship_intentions: p.relationshipIntentions || '',
    interests: p.interests,
    photos: p.photos,
    photo_url: p.photos[0] || null,
    is_verified: p.isVerified,
    shared_interests: p.interests.slice(0, 2),
    shared_interests_count: Math.min(p.interests.length, 2),
    relevance_score: 95,
  }))
}

export function SearchPage() {
  const [queryText, setQueryText] = useState('')
  const [cityFilter, setCityFilter] = useState('')
  const [professionFilter, setProfessionFilter] = useState('')
  const [intentionFilter, setIntentionFilter] = useState('')
  const [eraFilter, setEraFilter] = useState('')
  const [minAge, setMinAge] = useState<number | ''>('')
  const [maxAge, setMaxAge] = useState<number | ''>('')
  const [selectedInterests, setSelectedInterests] = useState<string[]>([])
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false)

  const [results, setResults] = useState<SearchCandidate[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [likedUserIds, setLikedUserIds] = useState<Set<number>>(new Set())
  const [matchNotification, setMatchNotification] = useState<string | null>(null)

  const performSearch = useCallback(async (paramsOverride?: Partial<SearchParams>) => {
    setIsLoading(true)
    setErrorMessage(null)

    const params: SearchParams = {
      q: (paramsOverride?.q !== undefined ? paramsOverride.q : queryText).trim() || undefined,
      city: (paramsOverride?.city !== undefined ? paramsOverride.city : cityFilter).trim() || undefined,
      profession: (paramsOverride?.profession !== undefined ? paramsOverride.profession : professionFilter).trim() || undefined,
      relationship_intentions: (paramsOverride?.relationship_intentions !== undefined ? paramsOverride.relationship_intentions : intentionFilter) || undefined,
      era: (paramsOverride?.era !== undefined ? paramsOverride.era : eraFilter) || undefined,
      min_age: typeof (paramsOverride?.min_age !== undefined ? paramsOverride.min_age : minAge) === 'number'
        ? Number(paramsOverride?.min_age !== undefined ? paramsOverride.min_age : minAge)
        : undefined,
      max_age: typeof (paramsOverride?.max_age !== undefined ? paramsOverride.max_age : maxAge) === 'number'
        ? Number(paramsOverride?.max_age !== undefined ? paramsOverride.max_age : maxAge)
        : undefined,
      interests: paramsOverride?.interests !== undefined ? paramsOverride.interests : (selectedInterests.length > 0 ? selectedInterests : undefined),
    }

    if (isDemoModeEnabled()) {
      const candidates = filterDemoCandidates(params)
      setResults(candidates)
      setTotalCount(candidates.length)
      setIsLoading(false)
      return
    }

    try {
      const response = await searchProfiles(params)
      setResults(response.results)
      setTotalCount(response.total)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to search profiles'
      setErrorMessage(message)
      setResults([])
      setTotalCount(0)
    } finally {
      setIsLoading(false)
    }
  }, [queryText, cityFilter, professionFilter, intentionFilter, eraFilter, minAge, maxAge, selectedInterests])

  useEffect(() => {
    void performSearch()
  }, []) // Initial search on mount

  const handleSearchSubmit = (e: FormEvent) => {
    e.preventDefault()
    void performSearch()
  }

  const toggleInterest = (interest: string) => {
    setSelectedInterests(prev => {
      const next = prev.includes(interest)
        ? prev.filter(i => i !== interest)
        : [...prev, interest]
      void performSearch({ interests: next.length > 0 ? next : undefined })
      return next
    })
  }

  const handleResetFilters = () => {
    setQueryText('')
    setCityFilter('')
    setProfessionFilter('')
    setIntentionFilter('')
    setEraFilter('')
    setMinAge('')
    setMaxAge('')
    setSelectedInterests([])
    void performSearch({
      q: '',
      city: '',
      profession: '',
      relationship_intentions: undefined,
      era: undefined,
      min_age: undefined,
      max_age: undefined,
      interests: undefined,
    })
  }

  const handleLike = async (candidate: SearchCandidate) => {
    if (likedUserIds.has(candidate.user_id)) return

    if (isDemoModeEnabled()) {
      const res = swipeDemoCandidate(candidate.user_id, 'like')
      setLikedUserIds(prev => new Set(prev).add(candidate.user_id))
      if (res.isMatch) {
        setMatchNotification(`It's a Match with ${candidate.full_name || candidate.username}! 💖`)
      } else {
        setMatchNotification(`Liked ${candidate.full_name || candidate.username}! ✨`)
      }
      setTimeout(() => setMatchNotification(null), 3500)
      return
    }

    try {
      const res = await submitSwipe(candidate.user_id, 'like')
      setLikedUserIds(prev => new Set(prev).add(candidate.user_id))
      if (res.is_match) {
        setMatchNotification(`It's a Match with ${candidate.full_name || candidate.username}! 💖`)
      } else {
        setMatchNotification(`Liked ${candidate.full_name || candidate.username}! ✨`)
      }
      setTimeout(() => setMatchNotification(null), 3500)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Could not submit like'
      setErrorMessage(msg)
    }
  }

  return (
    <PageContainer className="search-page">
      <header className="search-header">
        <p className="integration-eyebrow">RAAHI SEARCH & DISCOVERY</p>
        <h1>Find Your <span>Kindred Spirits</span></h1>
        <p>Explore real profiles filtered by interests, profession, lifestyle, and values.</p>
      </header>

      {matchNotification && (
        <div className="discover-feedback-toast" role="status">
          {matchNotification}
        </div>
      )}

      <Card className="search-controls-card">
        <form onSubmit={handleSearchSubmit}>
          <div className="search-main-bar">
            <div className="search-input-wrapper">
              <span className="search-input-icon" aria-hidden="true">🔍</span>
              <input
                type="text"
                className="search-input-field"
                placeholder="Search by name, profession, city, or keywords..."
                value={queryText}
                onChange={e => setQueryText(e.target.value)}
              />
              {queryText && (
                <button
                  type="button"
                  className="search-clear-btn"
                  onClick={() => {
                    setQueryText('')
                    void performSearch({ q: '' })
                  }}
                  aria-label="Clear search"
                >
                  ✕
                </button>
              )}
            </div>
            <button type="submit" className="search-submit-btn">
              Search ✦
            </button>
          </div>

          <div className="search-filters-toggle-row">
            <button
              type="button"
              className="search-filter-toggle-btn"
              onClick={() => setShowAdvancedFilters(prev => !prev)}
            >
              <span>{showAdvancedFilters ? '▾ Hide Filters' : '▸ Filter by City, Age, Era & Intentions'}</span>
            </button>
            <button type="button" className="search-reset-btn" onClick={handleResetFilters}>
              Reset all filters
            </button>
          </div>

          {showAdvancedFilters && (
            <div className="search-filters-panel">
              <div className="search-filter-group">
                <label>City / Location</label>
                <input
                  type="text"
                  className="search-filter-input"
                  placeholder="e.g. Mumbai, Bengaluru..."
                  value={cityFilter}
                  onChange={e => setCityFilter(e.target.value)}
                />
              </div>

              <div className="search-filter-group">
                <label>Profession</label>
                <input
                  type="text"
                  className="search-filter-input"
                  placeholder="e.g. Designer, Founder..."
                  value={professionFilter}
                  onChange={e => setProfessionFilter(e.target.value)}
                />
              </div>

              <div className="search-filter-group">
                <label>Relationship Intention</label>
                <select
                  className="search-select"
                  value={intentionFilter}
                  onChange={e => setIntentionFilter(e.target.value)}
                >
                  {RELATIONSHIP_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              <div className="search-filter-group">
                <label>Generation / Era</label>
                <select
                  className="search-select"
                  value={eraFilter}
                  onChange={e => setEraFilter(e.target.value)}
                >
                  {ERA_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              <div className="search-filter-group">
                <label>Age Range</label>
                <div className="search-age-range">
                  <input
                    type="number"
                    min={18}
                    max={100}
                    placeholder="Min"
                    className="search-filter-input"
                    value={minAge}
                    onChange={e => setMinAge(e.target.value ? Number(e.target.value) : '')}
                  />
                  <span>—</span>
                  <input
                    type="number"
                    min={18}
                    max={100}
                    placeholder="Max"
                    className="search-filter-input"
                    value={maxAge}
                    onChange={e => setMaxAge(e.target.value ? Number(e.target.value) : '')}
                  />
                </div>
              </div>
            </div>
          )}

          <div className="search-interests-section">
            <span className="search-interests-label">Filter by interests:</span>
            <div className="search-interests-chips">
              {POPULAR_INTERESTS.map(interest => {
                const isSelected = selectedInterests.includes(interest)
                return (
                  <button
                    key={interest}
                    type="button"
                    className={`search-interest-chip${isSelected ? ' active' : ''}`}
                    onClick={() => toggleInterest(interest)}
                  >
                    {isSelected ? '✓ ' : ''}{interest}
                  </button>
                )
              })}
            </div>
          </div>
        </form>
      </Card>

      {errorMessage && (
        <div className="discover-api-error" role="alert" style={{ marginBottom: 24 }}>
          {errorMessage}
        </div>
      )}

      {isLoading ? (
        <LoadingState label="Searching real profiles..." />
      ) : (
        <>
          <div className="search-results-summary">
            <span className="search-results-count">
              Found <strong>{totalCount}</strong> {totalCount === 1 ? 'profile' : 'profiles'}
            </span>
          </div>

          {results.length === 0 ? (
            <Card className="search-empty-card">
              <span className="search-empty-icon" aria-hidden="true">🌌</span>
              <p className="integration-eyebrow">NO PROFILES MATCHED</p>
              <h2>Broaden your search criteria</h2>
              <p>
                We couldn't find anyone matching all your active filters.
                Try relaxing the age range, removing selected interests, or clearing the search text.
              </p>
              <button type="button" className="search-submit-btn" onClick={handleResetFilters}>
                Clear All Filters ✦
              </button>
            </Card>
          ) : (
            <div className="search-grid">
              {results.map(candidate => {
                const displayName = candidate.full_name || candidate.username
                const isLiked = likedUserIds.has(candidate.user_id)
                const primaryPhoto = candidate.photo_url || (candidate.photos && candidate.photos[0])

                return (
                  <div key={candidate.user_id} className="search-candidate-card">
                    <div className="search-card-photo-wrapper">
                      {primaryPhoto ? (
                        <img
                          src={resolveMediaUrl(primaryPhoto)}
                          alt={displayName}
                          className="search-card-img"
                          loading="lazy"
                        />
                      ) : (
                        <div className="search-card-photo-placeholder">
                          <span>{displayName.charAt(0).toUpperCase()}</span>
                        </div>
                      )}

                      <div className="search-card-overlay-badges">
                        {candidate.shared_interests_count > 0 ? (
                          <span className="search-shared-badge">
                            ✨ {candidate.shared_interests_count} shared
                          </span>
                        ) : <span />}
                        <span className="search-verified-pill">✓ Verified</span>
                      </div>
                    </div>

                    <div className="search-card-content">
                      <div className="search-card-identity">
                        <h2 className="search-card-name">{displayName}</h2>
                        {candidate.age && <span className="search-card-age">{candidate.age}</span>}
                      </div>

                      <div className="search-card-location">
                        📍 {candidate.city || 'India'}
                        {candidate.era ? ` • ${candidate.era.toUpperCase()}` : ''}
                      </div>

                      <div className="search-card-meta">
                        {candidate.profession && (
                          <span className="search-meta-tag">💼 {candidate.profession}</span>
                        )}
                        {candidate.education && (
                          <span className="search-meta-tag">🎓 {candidate.education}</span>
                        )}
                        {candidate.relationship_intentions && (
                          <span className="search-meta-tag">💫 {candidate.relationship_intentions}</span>
                        )}
                      </div>

                      {candidate.bio && (
                        <p className="search-card-bio">{candidate.bio}</p>
                      )}

                      {candidate.interests && candidate.interests.length > 0 && (
                        <div className="search-card-interests">
                          {candidate.interests.slice(0, 5).map((interest, idx) => {
                            const isShared = candidate.shared_interests?.some(
                              si => si.toLowerCase() === interest.toLowerCase()
                            )
                            return (
                              <span
                                key={idx}
                                className={`search-card-interest-tag${isShared ? ' shared' : ''}`}
                              >
                                {interest}
                              </span>
                            )
                          })}
                          {candidate.interests.length > 5 && (
                            <span className="search-card-interest-tag">
                              +{candidate.interests.length - 5}
                            </span>
                          )}
                        </div>
                      )}

                      <div className="search-card-actions">
                        <Link
                          to={`/discover/${candidate.user_id}`}
                          className="search-action-btn search-view-btn"
                        >
                          View Profile
                        </Link>
                        <button
                          type="button"
                          className={`search-action-btn search-like-btn${isLiked ? ' liked' : ''}`}
                          onClick={() => handleLike(candidate)}
                          disabled={isLiked}
                        >
                          {isLiked ? 'Liked 💖' : 'Like ✦'}
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}
    </PageContainer>
  )
}
export default SearchPage

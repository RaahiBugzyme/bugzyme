import { useNavigate, useParams } from 'react-router'
import { Button } from '../components/Button'
import { Card } from '../components/Card'

interface IntegrationRoutePlaceholderProps {
  page: 'matches' | 'match'
}

export function IntegrationRoutePlaceholder({ page }: IntegrationRoutePlaceholderProps) {
  const navigate = useNavigate()
  const { profileId } = useParams()
  const isMatch = page === 'match'

  return (
    <Card className="integration-placeholder-card">
      <div className="integration-placeholder-icon" aria-hidden="true">{isMatch ? '💞' : '✨'}</div>
      <p className="integration-eyebrow">Phase 1 foundation</p>
      <h1>{isMatch ? 'Match celebration route' : 'Matches and conversations route'}</h1>
      <p className="integration-placeholder-copy">
        {isMatch
          ? `The match result page is ready to be added here${profileId ? ` for ${profileId}` : ''}.`
          : 'The matches list page is ready to be added here.'}
      </p>
      <Button variant="secondary" onClick={() => navigate('/onboarding')}>Return to onboarding</Button>
    </Card>
  )
}

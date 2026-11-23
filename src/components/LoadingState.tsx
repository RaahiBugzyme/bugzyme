interface LoadingStateProps {
  label?: string
  fullPage?: boolean
}

export function LoadingState({ label = 'Loading', fullPage = false }: LoadingStateProps) {
  return (
    <div className={`integration-loading${fullPage ? ' full-page' : ''}`} role="status" aria-live="polite">
      <span className="integration-spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}

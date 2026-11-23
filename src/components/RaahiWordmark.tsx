export function RaahiWordmark({ label = 'raahi', className = '' }: { label?: string; className?: string }) {
  return <span className={`raahi-script-wordmark ${className}`.trim()} aria-label="Raahi">{label}</span>
}

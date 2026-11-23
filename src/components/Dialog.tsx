import { useEffect, useId, type ReactNode } from 'react'

interface DialogProps {
  open: boolean
  title: string
  children: ReactNode
  onClose: () => void
}

export function Dialog({ open, title, children, onClose }: DialogProps) {
  const titleId = useId()

  useEffect(() => {
    if (!open) return
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="integration-dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
      <section className="integration-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="integration-dialog-heading">
          <h2 id={titleId}>{title}</h2>
          <button type="button" className="integration-dialog-close" onClick={onClose} aria-label="Close dialog">×</button>
        </div>
        <div>{children}</div>
      </section>
    </div>
  )
}

import { useEffect, useRef, type FormEvent } from 'react'
import { Button } from './Button'

interface EditNameModalProps {
  open: boolean
  value: string
  onChange: (value: string) => void
  onClose: () => void
  onSave: () => void
}

export default function EditNameModal({ open, value, onChange, onClose, onSave }: EditNameModalProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    const focusTimer = window.setTimeout(() => inputRef.current?.focus(), 100)
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.clearTimeout(focusTimer)
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [open, onClose])

  if (!open) return null

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSave()
  }

  return (
    <div
      className="modal-overlay open"
      onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}
      onTouchEnd={event => { if (event.target === event.currentTarget) onClose() }}
    >
      <form className="modal" role="dialog" aria-modal="true" aria-labelledby="edit-name-title" onSubmit={submit}>
        <h3 id="edit-name-title">✏️ Edit App Name</h3>
        <input
          ref={inputRef}
          type="text"
          id="nameInput"
          maxLength={20}
          placeholder="raahi"
          value={value}
          onChange={event => onChange(event.target.value)}
        />
        <div className="modal-actions">
          <Button type="button" variant="google" className="modal-button" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" className="modal-button">Save ✓</Button>
        </div>
      </form>
    </div>
  )
}

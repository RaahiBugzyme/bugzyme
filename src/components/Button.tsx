import type { ButtonHTMLAttributes, ReactNode } from 'react'

type ButtonVariant = 'primary' | 'secondary' | 'google'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant: ButtonVariant
  children: ReactNode
}

export function Button({ variant, className = '', children, ...props }: ButtonProps) {
  return <button className={`btn btn-${variant} ${className}`.trim()} {...props}>{children}</button>
}

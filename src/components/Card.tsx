import type { HTMLAttributes, ReactNode } from 'react'

interface CardProps extends HTMLAttributes<HTMLElement> {
  children: ReactNode
  as?: 'article' | 'section' | 'div'
}

export function Card({ children, as: Element = 'article', className = '', ...props }: CardProps) {
  return <Element className={`integration-card${className ? ` ${className}` : ''}`} {...props}>{children}</Element>
}

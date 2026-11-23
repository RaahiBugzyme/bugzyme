import type { HTMLAttributes, ReactNode } from 'react'

interface PageContainerProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  width?: 'reading' | 'wide'
}

export function PageContainer({ children, className = '', width = 'wide', ...props }: PageContainerProps) {
  return <div className={`integration-page-container ${width}${className ? ` ${className}` : ''}`} {...props}>{children}</div>
}

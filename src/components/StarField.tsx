import { useMemo, type CSSProperties } from 'react'

interface StarStyle extends CSSProperties {
  '--d': string
  '--delay': string
}

export default function StarField() {
  const stars = useMemo(() => Array.from({ length: 55 }, (_, index) => {
    const size = Math.random() * 2.5 + 0.8
    return {
      id: index,
      style: {
        width: `${size}px`,
        height: `${size}px`,
        left: `${Math.random() * 100}%`,
        top: `${Math.random() * 80}%`,
        '--d': `${2 + Math.random() * 4}s`,
        '--delay': `-${Math.random() * 5}s`,
      } as StarStyle,
    }
  }), [])

  return <div className="stars" aria-hidden="true">{stars.map(star => <span className="star" style={star.style} key={star.id} />)}</div>
}

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { generationThemes, type GenerationId } from '../data/generations'

const THEME_STORAGE_KEY = 'raahiGenerationTheme.v1'

function readSavedGeneration(): GenerationId {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY)
    if (saved && saved in generationThemes) return saved as GenerationId
  } catch {
    // Keep the default theme when browser storage is unavailable.
  }
  return 'genz'
}

interface ThemeContextValue {
  generation: GenerationId
  setGeneration: (generation: GenerationId) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [generation, setGenerationState] = useState<GenerationId>(readSavedGeneration)

  const setGeneration = useCallback((next: GenerationId) => {
    if (!next || !(next in generationThemes)) return
    setGenerationState(next)
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next)
    } catch {
      // Theme still changes for this session when browser storage is unavailable.
    }
  }, [])

  const theme = generationThemes[generation] || generationThemes.genz

  // Authoritative global DOM and CSS variable synchronization
  useEffect(() => {
    if (typeof document === 'undefined') return
    const curTheme = generationThemes[generation] || generationThemes.genz

    document.documentElement.setAttribute('data-theme', generation)
    document.body.setAttribute('data-theme', generation)

    const rootStyle = document.documentElement.style
    rootStyle.setProperty('--ep', curTheme.primary)
    rootStyle.setProperty('--es', curTheme.secondary)
    rootStyle.setProperty('--glow', curTheme.glow)
    rootStyle.setProperty('--cbg', curTheme.cardBackground)
    rootStyle.setProperty('--cbr', curTheme.cardBorder)
    rootStyle.setProperty('--bd', curTheme.background)
    rootStyle.setProperty('--bg-deep', curTheme.background)
    rootStyle.setProperty('--purple', curTheme.primary)
    rootStyle.setProperty('--pink', curTheme.secondary)
    rootStyle.setProperty('--pink-purple', `linear-gradient(135deg, ${curTheme.secondary} 0%, ${curTheme.primary} 100%)`)
    rootStyle.setProperty('--era-accent', curTheme.primary)
    rootStyle.setProperty('--era-bg', curTheme.cardBackground)
    rootStyle.setProperty('--ring-color', curTheme.primary)
    document.body.style.backgroundColor = curTheme.background
  }, [generation])

  return (
    <ThemeContext.Provider value={useMemo(() => ({ generation, setGeneration }), [generation, setGeneration])}>
      <div
        className="app-shell"
        data-theme={generation}
        style={{
          '--ep': theme.primary,
          '--es': theme.secondary,
          '--glow': theme.glow,
          '--cbg': theme.cardBackground,
          '--cbr': theme.cardBorder,
          '--bd': theme.background,
          '--bg-deep': theme.background,
          '--purple': theme.primary,
          '--pink': theme.secondary,
          '--pink-purple': `linear-gradient(135deg, ${theme.secondary} 0%, ${theme.primary} 100%)`,
          '--era-accent': theme.primary,
          '--era-bg': theme.cardBackground,
          '--ring-color': theme.primary,
        } as React.CSSProperties}
      >
        {children}
      </div>
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('useTheme must be used inside ThemeProvider')
  return value
}

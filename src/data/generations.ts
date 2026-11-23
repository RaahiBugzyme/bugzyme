export type GenerationId = 'genz' | 'zillenial' | 'millennial'

export interface GenerationTheme {
  id: GenerationId
  name: string
  emoji: string
  emojiAnimation: string
  primary: string
  secondary: string
  glow: string
  cardBackground: string
  cardBorder: string
  background: string
  eraDescription: string
  eraTags: string[]
  vibeTitle: string
  vibeHeadingEmoji: string
  vibeHeadingAnimation: string
  vibeSubtitle: string
  matchTitle: string
  matchHeadingEmoji: string
  matchHeadingAnimation: string
  vibes: Array<{ icon: string; animation: string; name: string; description: string }>
}

// Copy and theme values are transcribed from reference-prototypes/raahi-v3.html.
export const generationThemes: Record<GenerationId, GenerationTheme> = {
  genz: {
    id: 'genz', name: 'Gen Z', emoji: '💀', emojiAnimation: 'e-shake',
    primary: '#a855f7', secondary: '#ec4899', glow: 'rgba(168,85,247,.35)',
    cardBackground: 'rgba(168,85,247,.1)', cardBorder: 'rgba(168,85,247,.35)', background: '#0d0a1a',
    eraDescription: 'Born 1997–2012 · Chronically online',
    eraTags: ['slay', 'no cap', "it's giving", 'lowkey'],
    vibeTitle: "What's your situationship status?", vibeHeadingEmoji: '🫠', vibeHeadingAnimation: 'e-melt',
    vibeSubtitle: 'Pick the vibe that hits different. No cap.',
    matchTitle: 'Who you tryna link with?', matchHeadingEmoji: '👀', matchHeadingAnimation: 'e-wiggle',
    vibes: [
      { icon: '🫠', animation: 'e-melt', name: 'Situationship', description: "we're talking but make it complicated" },
      { icon: '📱', animation: 'e-bounce', name: 'Talking stage', description: "still deciding if you're built different" },
      { icon: '🤳', animation: 'e-float', name: 'Soft launch', description: 'low-key posting, high-key hoping' },
      { icon: '🌟', animation: 'e-spin', name: 'Main character era', description: 'looking for your supporting cast' },
      { icon: '🎯', animation: 'e-spin', name: 'No strings fr fr', description: 'just vibes, zero drama energy' },
      { icon: '🍞', animation: 'e-bounce', name: 'Breadcrumbing? Nah.', description: 'done with games, want something real' },
    ],
  },
  zillenial: {
    id: 'zillenial', name: 'Zillenial', emoji: '🎭', emojiAnimation: 'e-flip',
    primary: '#f59e0b', secondary: '#ef4444', glow: 'rgba(245,158,11,.35)',
    cardBackground: 'rgba(245,158,11,.1)', cardBorder: 'rgba(245,158,11,.35)', background: '#1a0e04',
    eraDescription: 'Born 1993–1998 · Caught between eras',
    eraTags: ['both worlds', 'hybrid', 'lowkey boomer'],
    vibeTitle: "What's the vibe this season?", vibeHeadingEmoji: '🌀', vibeHeadingAnimation: 'e-orbit',
    vibeSubtitle: 'You get both eras. Pick your chaos level.',
    matchTitle: 'Who matches your hybrid energy?', matchHeadingEmoji: '🔀', matchHeadingAnimation: 'e-flip',
    vibes: [
      { icon: '🌀', animation: 'e-orbit', name: 'Undefined but vibing', description: 'talking stage + casual dating mashup' },
      { icon: '🎭', animation: 'e-flip', name: 'Low-key exclusive', description: 'half old school, half situationship' },
      { icon: '🤷', animation: 'e-wiggle', name: 'Half-official', description: 'Instagram official, group chat unofficial' },
      { icon: '🌉', animation: 'e-float', name: 'Caught between', description: 'wants labels but also wants freedom' },
      { icon: '🏠', animation: 'e-bounce', name: 'Adulting together', description: 'split the rent, share the feelings' },
      { icon: '💫', animation: 'e-orbit', name: 'Hybrid feels', description: 'Gen Z heart, Millennial schedule' },
    ],
  },
  millennial: {
    id: 'millennial', name: 'Millennial', emoji: '✌️', emojiAnimation: 'e-wave',
    primary: '#3b82f6', secondary: '#06b6d4', glow: 'rgba(59,130,246,.35)',
    cardBackground: 'rgba(59,130,246,.1)', cardBorder: 'rgba(59,130,246,.35)', background: '#040d1a',
    eraDescription: 'Born 1981–1996 · Adulting is hard',
    eraTags: ['vibe check', 'Netflix?', 'goals'],
    vibeTitle: 'What are we actually doing here?', vibeHeadingEmoji: '☕', vibeHeadingAnimation: 'e-steam',
    vibeSubtitle: 'Old school vibes. Honest intentions.',
    matchTitle: 'Who do you want to meet?', matchHeadingEmoji: '🌊', matchHeadingAnimation: 'e-float',
    vibes: [
      { icon: '☕', animation: 'e-steam', name: 'Casual dating', description: 'coffee first, see where it goes' },
      { icon: '🌹', animation: 'e-swing', name: 'Taking it slow', description: 'real connection over quick flings' },
      { icon: '💌', animation: 'e-float', name: 'Old school romance', description: 'letters, flowers, the whole nine yards' },
      { icon: '🤝', animation: 'e-bounce', name: 'Friends first', description: 'build the foundation, bloom later' },
      { icon: '💍', animation: 'e-glint', name: 'Exclusive', description: 'all in, one person, no confusion' },
      { icon: '🌊', animation: 'e-wave', name: 'Go with the flow', description: 'no labels, no pressure, just vibes' },
    ],
  },
}

import type { GenerationId } from './generations'

export interface Profile {
  name: string
  age: number
  city: string
  era: GenerationId
  emoji: string
  emojiAnimation: string
  bio: string
  tags: string[]
  compatibility: number
}

export const profilesByGeneration: Record<GenerationId, Profile[]> = {
  genz: [
    { name: 'Zara K.', age: 22, city: 'Mumbai', era: 'genz', emoji: '🧿', emojiAnimation: 'e-orbit', bio: "it's giving main character energy tbh. looking for someone who doesn't ghost 👻", tags: ['situationship survivor', 'chronically online', 'slay everyday'], compatibility: 88 },
    { name: 'Aryan V.', age: 21, city: 'Bangalore', era: 'genz', emoji: '🫧', emojiAnimation: 'e-float', bio: "no cap this app lowkey slaps. I'm a vibe check kinda person fr fr", tags: ['rizz unlocked', 'soft launch ready', 'zero drama'], compatibility: 82 },
    { name: 'Nisha R.', age: 23, city: 'Delhi', era: 'genz', emoji: '✨', emojiAnimation: 'e-spin', bio: 'bestie if you\'re still reading this we should probably just talk already lol', tags: ["it's giving energy", 'lowkey shy', 'highly selective'], compatibility: 91 },
  ],
  millennial: [
    { name: 'Priya M.', age: 31, city: 'Pune', era: 'millennial', emoji: '🌿', emojiAnimation: 'e-float', bio: 'Coffee shop dates > club nights. Looking for someone who texts back ☕', tags: ['old school romantic', 'brunch enthusiast', 'emotionally available'], compatibility: 85 },
    { name: 'Rahul S.', age: 33, city: 'Delhi', era: 'millennial', emoji: '🎸', emojiAnimation: 'e-swing', bio: 'Adulting is hard but I\'m managing. Deep convos and Netflix marathons', tags: ['goals-oriented', 'vibe check passed', 'long-term ready'], compatibility: 79 },
    { name: 'Ananya T.', age: 29, city: 'Hyderabad', era: 'millennial', emoji: '🌸', emojiAnimation: 'e-wiggle', bio: "Harry Potter fan who somehow ended up in tech. Let's get dinner first?", tags: ['slow burn', 'emotionally mature', 'hikes on weekends'], compatibility: 87 },
  ],
  zillenial: [
    { name: 'Kiara T.', age: 27, city: 'Hyderabad', era: 'zillenial', emoji: '🌊', emojiAnimation: 'e-wave', bio: 'I grew up on MSN and now I\'m terminally online. Thriving chaotically', tags: ['hybrid energy', 'both worlds', 'lowkey boomer tbh'], compatibility: 93 },
    { name: 'Dev N.', age: 26, city: 'Chennai', era: 'zillenial', emoji: '🎭', emojiAnimation: 'e-flip', bio: 'Half LinkedIn half BeReal. Gets BOTH sides of the vibe spectrum', tags: ['undefined but vibing', 'adulting together', 'hybrid feels'], compatibility: 86 },
    { name: 'Meera S.', age: 25, city: 'Mumbai', era: 'zillenial', emoji: '🦋', emojiAnimation: 'e-orbit', bio: "Old enough for a mortgage, young enough to not want one. Let's vibe.", tags: ['caught between', 'adulting-ish', 'semi-chronically online'], compatibility: 90 },
  ],
}

export const matchEraOptions = [
  { id: 'genz', name: 'Gen Z', emoji: '💀', animation: 'e-shake', description: 'TikTok-brained, chronically online' },
  { id: 'zillenial', name: 'Zillenial', emoji: '🎭', animation: 'e-flip', description: 'Gets both eras, chaos but self-aware' },
  { id: 'millennial', name: 'Millennial', emoji: '✌️', animation: 'e-wave', description: 'Emotionally available (mostly)' },
  { id: 'any', name: 'Open to any era', emoji: '🌈', animation: 'e-spin', description: "Love doesn't check a birth certificate" },
] as const

export type MatchEraId = typeof matchEraOptions[number]['id']

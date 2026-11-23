import { getDemoCandidateById, getDemoMatches, ensureDemoConversation } from './demoAppData.ts'
import { TWENTY_DEMO_PROFILES } from './demoProfiles.ts'

export interface DemoProfile {
  id: number
  chatId: number
  name: string
  age: number
  era: 'Gen Z' | 'Zillenial' | 'Millennial'
  eraBadge: string
  eraIcon: string
  ringColor: string
  status: 'offline' | 'online'
  lastSeen: string
  lastMessage: string
  lastMessageTime: string
  unread: boolean
  isNew: boolean
  cornerEmoji: string
  vibeTag: string
  connectionText: string
  initials: string
  photo: string
  photos: string[]
  isMatch: boolean
}

export interface DemoChatMessage {
  id: number
  chatId: number
  senderId: number // 0 = current user, 1 = partner
  content: string | null
  createdAt: string
  isRead: boolean
  isDelivered: boolean
  messageType: 'text' | 'image' | 'voice'
  mediaUrl?: string
  duration?: number
  reactions: { reaction: string; userId: number }[]
}

export const DEMO_PROFILES: DemoProfile[] = TWENTY_DEMO_PROFILES.map(p => ({
  id: p.id,
  chatId: p.chatId,
  name: p.name,
  age: p.age ?? 22,
  era: p.era === 'zillenial' ? 'Zillenial' : p.era === 'millennial' ? 'Millennial' : 'Gen Z',
  eraBadge: p.eraBadge,
  eraIcon: p.eraIcon,
  ringColor: p.ringColor,
  status: p.status,
  lastSeen: p.lastSeen,
  lastMessage: p.lastMessage || 'Say hi! 👋',
  lastMessageTime: p.lastMessageTime || 'Just now',
  unread: p.unread ?? false,
  isNew: p.isNew ?? true,
  cornerEmoji: p.cornerEmoji,
  vibeTag: p.vibeTag || 'Vibing on Raahi',
  connectionText: 'You two are connected — say hi!',
  initials: p.initials,
  photo: p.photos[0],
  photos: p.photos,
  isMatch: p.isMatch,
}))

const DEMO_STORAGE_KEY = 'raahi_demo_chat_messages_v2'

function getInitialDemoMessages(): Record<number, DemoChatMessage[]> {
  const now = Date.now()
  return {
    901: [
      // Jeet starts clean as shown in the screenshot: Introduction card is prominent, initial conversation state
    ],
    902: [
      {
        id: 90201,
        chatId: 902,
        senderId: 1,
        content: "Hey! What's up?",
        createdAt: new Date(now - 3600000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    903: [
      {
        id: 90301,
        chatId: 903,
        senderId: 1,
        content: "Haha, that's funny 😂",
        createdAt: new Date(now - 18000000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    904: [
      {
        id: 90401,
        chatId: 904,
        senderId: 1,
        content: "Let's talk sometime.",
        createdAt: new Date(now - 86400000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    905: [
      {
        id: 90501,
        chatId: 905,
        senderId: 1,
        content: 'Hey there! ✨',
        createdAt: new Date(now - 172800000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    906: [
      {
        id: 90601,
        chatId: 906,
        senderId: 1,
        content: 'Hey! Loved your profile vibe ✨',
        createdAt: new Date(now - 600000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    907: [
      {
        id: 90701,
        chatId: 907,
        senderId: 1,
        content: 'Hey! Specialty coffee or bubble tea? ☕',
        createdAt: new Date(now - 1200000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    908: [
      {
        id: 90801,
        chatId: 908,
        senderId: 1,
        content: 'Hi! Great to connect with you on Raahi 🌸',
        createdAt: new Date(now - 1800000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    909: [
      {
        id: 90901,
        chatId: 909,
        senderId: 1,
        content: 'Hey! What kind of movies or shows are you into? 🎬',
        createdAt: new Date(now - 3600000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    910: [
      {
        id: 91001,
        chatId: 910,
        senderId: 1,
        content: 'Heyy! What song is stuck in your head today? 🎧',
        createdAt: new Date(now - 900000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    911: [
      {
        id: 91101,
        chatId: 911,
        senderId: 1,
        content: 'Hey! Your vibe is so cozy 🌿 Love the energy!',
        createdAt: new Date(now - 450000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    912: [
      {
        id: 91201,
        chatId: 912,
        senderId: 1,
        content: 'Khamma Ghani! Ever been out camping under the desert stars? 🪕',
        createdAt: new Date(now - 1500000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    913: [
      {
        id: 91301,
        chatId: 913,
        senderId: 1,
        content: 'Hey there! Quick question: iced coffee or hot coffee? 🍦',
        createdAt: new Date(now - 2200000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    914: [
      {
        id: 91401,
        chatId: 914,
        senderId: 1,
        content: 'Hello! Always happy to meet another reader on Raahi 📚',
        createdAt: new Date(now - 3000000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    915: [
      {
        id: 91501,
        chatId: 915,
        senderId: 1,
        content: 'Hey. Liked your music tastes 🎧',
        createdAt: new Date(now - 5000000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    916: [
      {
        id: 91601,
        chatId: 916,
        senderId: 1,
        content: 'Hey! Ready for an adventure? Great to connect 🏔️',
        createdAt: new Date(now - 7000000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    917: [
      {
        id: 91701,
        chatId: 917,
        senderId: 1,
        content: 'Hey! Fast chess or slow coffee? Let’s chat ♟️',
        createdAt: new Date(now - 8000000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    918: [
      {
        id: 91801,
        chatId: 918,
        senderId: 1,
        content: 'Heyy! Warm greetings from the coast 🪸 How is your week going?',
        createdAt: new Date(now - 9000000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    919: [
      {
        id: 91901,
        chatId: 919,
        senderId: 1,
        content: 'Hey! Glad we matched ✨ What are you watching lately?',
        createdAt: new Date(now - 10000000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    920: [
      {
        id: 92001,
        chatId: 920,
        senderId: 1,
        content: 'Hello! Hope you are having a smooth week ⚓',
        createdAt: new Date(now - 12000000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    921: [
      {
        id: 92101,
        chatId: 921,
        senderId: 1,
        content: 'Hey! What are you building or creating this week? 🏺',
        createdAt: new Date(now - 900000).toISOString(),
        isRead: false,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    922: [
      {
        id: 92201,
        chatId: 922,
        senderId: 1,
        content: 'That dosa recommendation was elite! 🎮',
        createdAt: new Date(now - 3600000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    924: [
      {
        id: 92401,
        chatId: 924,
        senderId: 1,
        content: 'Have you ever heard Dastangoi live? It will blow your mind 📖',
        createdAt: new Date(now - 10800000).toISOString(),
        isRead: false,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    926: [
      {
        id: 92601,
        chatId: 926,
        senderId: 1,
        content: 'Let us check out the new gallery opening this Thursday! 🍷',
        createdAt: new Date(now - 1800000).toISOString(),
        isRead: true,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
    930: [
      {
        id: 93001,
        chatId: 930,
        senderId: 1,
        content: 'Fresh cardamom buns just came out of the oven! 🥐',
        createdAt: new Date(now - 600000).toISOString(),
        isRead: false,
        isDelivered: true,
        messageType: 'text',
        reactions: [],
      },
    ],
  }
}

let memoryMessageStore: Record<number, DemoChatMessage[]> | null = null

export function loadDemoMessagesStore(): Record<number, DemoChatMessage[]> {
  try {
    if (typeof sessionStorage !== 'undefined') {
      const raw = sessionStorage.getItem(DEMO_STORAGE_KEY)
      if (raw) return JSON.parse(raw) as Record<number, DemoChatMessage[]>
    }
  } catch {
    // fallback
  }
  if (memoryMessageStore) return memoryMessageStore
  const initial = getInitialDemoMessages()
  memoryMessageStore = initial
  saveDemoMessagesStore(initial)
  return initial
}

export function saveDemoMessagesStore(data: Record<number, DemoChatMessage[]>) {
  memoryMessageStore = data
  try {
    if (typeof sessionStorage !== 'undefined') {
      sessionStorage.setItem(DEMO_STORAGE_KEY, JSON.stringify(data))
    }
  } catch {
    // ignore
  }
}

export function getDemoMessages(chatId: number): DemoChatMessage[] {
  const store = loadDemoMessagesStore()
  return store[chatId] || []
}

export function appendDemoMessage(chatId: number, message: DemoChatMessage): DemoChatMessage[] {
  const store = loadDemoMessagesStore()
  const list = store[chatId] || []
  const next = [...list, message]
  store[chatId] = next
  saveDemoMessagesStore(store)

  // Ensure this demo candidate is saved in conversations with updated message preview
  if (message.content) {
    ensureDemoConversation(chatId, message.content)
  }
  return next
}

export function addDemoReaction(chatId: number, messageId: number, reaction: string): DemoChatMessage[] {
  const store = loadDemoMessagesStore()
  const list = store[chatId] || []
  const next = list.map(msg => {
    if (msg.id !== messageId) return msg
    const exists = msg.reactions.some(r => r.reaction === reaction)
    const reactions = exists
      ? msg.reactions.filter(r => r.reaction !== reaction)
      : [...msg.reactions, { reaction, userId: 0 }]
    return { ...msg, reactions }
  })
  store[chatId] = next
  saveDemoMessagesStore(store)
  return next
}

export function isDemoChat(chatId: number): boolean {
  return chatId >= 901 && chatId <= 999
}

export function getDemoProfile(chatId: number): DemoProfile | undefined {
  const candidate = getDemoCandidateById(chatId)
  if (candidate) {
    const store = loadDemoMessagesStore()
    const msgs = store[chatId] || []
    const lastMsg = msgs.length ? msgs[msgs.length - 1] : null
    return {
      id: candidate.id,
      chatId: candidate.chatId,
      name: candidate.name,
      age: candidate.age,
      era: candidate.era === 'zillenial' ? 'Zillenial' : candidate.era === 'millennial' ? 'Millennial' : 'Gen Z',
      eraBadge: candidate.eraBadge,
      eraIcon: candidate.eraIcon,
      ringColor: candidate.ringColor,
      status: candidate.status,
      lastSeen: candidate.lastSeen,
      lastMessage: lastMsg?.content || candidate.lastMessage || 'Say hi! 👋',
      lastMessageTime: lastMsg ? 'Just now' : (candidate.lastMessageTime || 'Just now'),
      unread: candidate.unread ?? false,
      isNew: candidate.isNew ?? true,
      cornerEmoji: candidate.cornerEmoji,
      vibeTag: candidate.vibeTag || 'Vibing',
      connectionText: 'You two are connected — say hi!',
      initials: candidate.initials,
      photo: candidate.photos[0],
      photos: candidate.photos,
      isMatch: candidate.isMatch,
    }
  }

  const found = DEMO_PROFILES.find(p => p.chatId === chatId)
  if (found) {
    const store = loadDemoMessagesStore()
    const msgs = store[chatId] || []
    const lastMsg = msgs.length ? msgs[msgs.length - 1] : null
    if (lastMsg?.content) {
      return {
        ...found,
        lastMessage: lastMsg.content,
        lastMessageTime: 'Just now',
      }
    }
  }
  return found
}

export function getDemoConversationProfiles(): DemoProfile[] {
  const store = loadDemoMessagesStore()
  const matchedCandidates = getDemoMatches()
  const messagedIds = Object.keys(store)
    .map(Number)
    .filter(id => (store[id] || []).length > 0)

  // Merge unique candidate IDs that are matched or have messages
  const seenIds = new Set<number>()
  const result: DemoProfile[] = []

  // Add all matched candidates from demoAppData
  for (const c of matchedCandidates) {
    if (!seenIds.has(c.id)) {
      seenIds.add(c.id)
      const prof = getDemoProfile(c.id)
      if (prof) result.push(prof)
    }
  }

  // Add any other profiles that have active messages
  for (const id of messagedIds) {
    if (!seenIds.has(id)) {
      seenIds.add(id)
      const prof = getDemoProfile(id)
      if (prof) result.push(prof)
    }
  }

  // Fallback to initial match profiles so user always has conversations to see
  for (const p of DEMO_PROFILES) {
    if (p.isMatch && !seenIds.has(p.id)) {
      seenIds.add(p.id)
      const prof = getDemoProfile(p.id)
      if (prof) result.push(prof)
    }
  }

  return result
}

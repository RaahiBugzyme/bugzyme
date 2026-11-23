import { apiRequest, uploadForm, webSocketUrl } from './client.ts'

export interface PublicUser {
  id: number
  username: string
  full_name: string | null
  bio: string | null
  photo_url?: string | null
  photos?: string[]
  is_online: boolean
  last_seen: string | null
}

export interface ChatSummary {
  chat_id: number
  user: PublicUser
  last_message: ChatMessage | null
  unread_count: number
}

export interface Reaction {
  user_id: number
  reaction: string
}

export interface ChatMessage {
  id: number
  chat_id: number
  sender_id: number
  content: string | null
  created_at: string | null
  read_at: string | null
  is_delivered: boolean
  is_read: boolean
  is_deleted: boolean
  reply_to_id: number | null
  message_type: 'text' | 'image' | 'file' | 'voice' | string
  audio_url: string | null
  audio_duration: number | null
  audio_mime_type: string | null
  attachment_name: string | null
  attachment_mime_type: string | null
  attachment_size_bytes: number | null
  reactions: Reaction[]
  reaction_revision: number
}

export interface MatchItem {
  id: number
  chat_id: number
  matched_user: {
    id: number | null
    username: string | null
    full_name: string | null
    bio: string | null
    photo_url?: string | null
    photos?: string[]
  }
  compatibility_score: number
  compatibility_score_status: 'legacy_placeholder'
  profile_alignment: { score: number | null; confidence: number | null; adjusted_score: number | null; package_version: string | null; engine_version: string | null; score_type: 'profile_alignment'; is_success_probability: false; weights_validated: boolean } | null
  created_at: string
  age: number | null
  city: string | null
  era: string | null
  vibe_tag: string | null
  profession?: string | null
  education?: string | null
  relationship_intentions?: string | null
  interests?: string[]
  photos?: string[]
}

export interface MatchDetail extends MatchItem {}
export interface MatchesResponse { matches: MatchItem[]; total: number; limit: number; offset: number; has_more: boolean }

export interface Suggestion { suggestion_id?: number; style?: string; message: string }
export interface SuggestionResult { chat_id: number; suggestions: Suggestion[]; should_generate: boolean; eligible: boolean; death_zone: Record<string, unknown>; recovery: Record<string, unknown> }

export interface IncomingMessageEvent {
  type: 'message' | 'voice_message'
  chat_id: number
  message_id: number
  sender_id: number
  sender_name?: string
  content: string | null
  created_at: string | null
  is_delivered?: boolean
  is_read?: boolean
  read_at?: string | null
  reply_to_id?: number | null
  message_type?: string
  audio_url?: string | null
  audio_duration?: number | null
  audio_mime_type?: string | null
  attachment_name?: string | null
  attachment_mime_type?: string | null
  attachment_size_bytes?: number | null
}

export async function fetchMatches(offset = 0, limit = 50) {
  return apiRequest<MatchesResponse>(`/api/v1/matches?limit=${limit}&offset=${offset}`)
}

export async function fetchMatch(matchId: number) {
  return apiRequest<MatchDetail>(`/api/v1/matches/${matchId}`)
}

export async function fetchChats() {
  return apiRequest<ChatSummary[]>('/chats')
}

export async function fetchMessages(chatId: number, limit = 200, beforeId?: number) {
  const cursor = beforeId == null ? '' : `&before_id=${beforeId}`
  return apiRequest<ChatMessage[]>(`/messages/${chatId}?limit=${limit}${cursor}`)
}

export async function sendTextMessage(chatId: number, content: string, replyToId?: number | null) {
  return apiRequest<ChatMessage>('/messages', {
    method: 'POST',
    body: JSON.stringify({ chat_id: chatId, content, reply_to_id: replyToId ?? null }),
  })
}

export async function deleteMessage(messageId: number) {
  return apiRequest<{ ok: boolean; message_id: number }>(`/messages/${messageId}?for_everyone=true`, { method: 'DELETE' })
}

export async function deleteConversation(chatId: number) {
  return apiRequest<{ ok: boolean; message: string }>(`/chats/${chatId}`, { method: 'DELETE' })
}

export async function uploadAttachment(chatId: number, file: File, caption: string, onProgress: (value: number) => void) {
  const form = new FormData()
  form.append('file', file)
  if (caption.trim()) form.append('caption', caption.trim())
  return uploadForm<ChatMessage>(`/chats/${chatId}/attachments`, form, onProgress)
}

export async function uploadVoice(chatId: number, file: File, duration: number, onProgress: (value: number) => void) {
  const form = new FormData()
  form.append('file', file)
  return uploadForm<{ success: boolean; message: ChatMessage; delivered: boolean }>(`/upload-voice?chat_id=${chatId}&duration=${duration}`, form, onProgress)
}

export async function fetchSuggestions(chatId: number) {
  return apiRequest<SuggestionResult>(`/chats/${chatId}/suggestions`, { method: 'POST', body: JSON.stringify({}) })
}

export async function fetchCoach(chatId: number) {
  return apiRequest<Record<string, unknown>>(`/chats/${chatId}/coach`)
}

export async function fetchInsights(chatId: number) {
  return apiRequest<Record<string, unknown>>(`/chats/${chatId}/insights`)
}

export async function trackSuggestionEvent(suggestionId: number, eventType: 'selected' | 'edited' | 'sent', eventKey: string, details: Record<string, unknown> = {}) {
  return apiRequest<{ ok: boolean }>(`/ai-suggestions/${suggestionId}/events`, {
    method: 'POST',
    body: JSON.stringify({ event_type: eventType, event_key: eventKey, details }),
  })
}

export function chatSocketUrl(chatId: number, token: string) {
  return webSocketUrl(`/ws/${chatId}`, token)
}

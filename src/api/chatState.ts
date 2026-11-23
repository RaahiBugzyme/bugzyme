import type { ChatMessage, IncomingMessageEvent, Reaction } from './chat.ts'

export type ChatEvent = {
  type: string
  chat_id?: number
  message_id?: number
  sender_id?: number
  content?: string | null
  created_at?: string | null
  read_at?: string | null
  reply_to_id?: number | null
  is_delivered?: boolean
  is_read?: boolean
  message_type?: string
  audio_url?: string | null
  audio_duration?: number | null
  audio_mime_type?: string | null
  attachment_name?: string | null
  attachment_mime_type?: string | null
  attachment_size_bytes?: number | null
  revision?: number
  reactions?: Reaction[]
}

export function mergeChatMessage(messages: ChatMessage[], next: ChatMessage) {
  const index = messages.findIndex(message => message.id === next.id)
  if (index < 0) return [...messages, next].sort((a, b) => a.id - b.id)
  const copy = [...messages]
  copy[index] = { ...copy[index], ...next, reactions: next.reactions?.length ? next.reactions : copy[index].reactions }
  return copy
}

export function reduceChatMessages(messages: ChatMessage[], event: ChatEvent): ChatMessage[] {
  if ((event.type === 'message' || event.type === 'voice_message') && event.message_id && event.chat_id && event.sender_id) {
    const incoming = event as IncomingMessageEvent
    const message: ChatMessage = {
      id: incoming.message_id, chat_id: incoming.chat_id, sender_id: incoming.sender_id,
      content: incoming.content, created_at: incoming.created_at, read_at: incoming.read_at ?? null,
      is_delivered: Boolean(incoming.is_delivered), is_read: Boolean(incoming.is_read), is_deleted: false,
      reply_to_id: incoming.reply_to_id ?? null,
      message_type: incoming.message_type || (incoming.type === 'voice_message' ? 'voice' : 'text'),
      audio_url: incoming.audio_url ?? null, audio_duration: incoming.audio_duration ?? null,
      audio_mime_type: incoming.audio_mime_type ?? null, attachment_name: incoming.attachment_name ?? null,
      attachment_mime_type: incoming.attachment_mime_type ?? null, attachment_size_bytes: incoming.attachment_size_bytes ?? null,
      reactions: [], reaction_revision: 0,
    }
    return mergeChatMessage(messages, message)
  }
  if (event.type === 'message_delivered') return messages.map(message => message.id === event.message_id ? { ...message, is_delivered: true } : message)
  if (event.type === 'message_read') return messages.map(message => message.id === event.message_id ? { ...message, is_read: true, read_at: event.read_at ?? message.read_at } : message)
  if (event.type === 'message_deleted') return messages.map(message => message.id === event.message_id ? { ...message, is_deleted: true, content: null, attachment_name: null, audio_url: null } : message)
  if (event.type === 'message_reaction') {
    const revision = Number(event.revision ?? -1)
    const reactions = event.reactions ?? []
    return messages.map(message => message.id === event.message_id && revision >= message.reaction_revision
      ? { ...message, reactions, reaction_revision: revision }
      : message)
  }
  return messages
}

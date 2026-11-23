import assert from 'node:assert/strict'
import test from 'node:test'
import { reduceChatMessages } from '../src/api/chatState.ts'
import type { ChatMessage } from '../src/api/chat.ts'

const baseMessage: ChatMessage = {
  id: 20, chat_id: 9, sender_id: 3, content: 'hello', created_at: '2026-01-01T10:00:00Z', read_at: null,
  is_delivered: false, is_read: false, is_deleted: false, reply_to_id: null, message_type: 'text',
  audio_url: null, audio_duration: null, audio_mime_type: null, attachment_name: null,
  attachment_mime_type: null, attachment_size_bytes: null, reactions: [], reaction_revision: 0,
}

test('incoming WebSocket messages are ordered and duplicate IDs are merged', () => {
  const event = { type: 'message', chat_id: 9, message_id: 21, sender_id: 4, content: 'there', created_at: '2026-01-01T10:01:00Z' }
  const once = reduceChatMessages([baseMessage], event)
  const twice = reduceChatMessages(once, event)
  assert.deepEqual(once.map(message => message.id), [20, 21])
  assert.deepEqual(twice.map(message => message.id), [20, 21])
  assert.equal(twice[1].content, 'there')
})

test('delivery, read and global-delete events update the authoritative message state', () => {
  const delivered = reduceChatMessages([baseMessage], { type: 'message_delivered', message_id: 20 })
  const read = reduceChatMessages(delivered, { type: 'message_read', message_id: 20, read_at: '2026-01-01T10:02:00Z' })
  const deleted = reduceChatMessages(read, { type: 'message_deleted', message_id: 20 })
  assert.equal(delivered[0].is_delivered, true)
  assert.equal(read[0].is_read, true)
  assert.equal(read[0].read_at, '2026-01-01T10:02:00Z')
  assert.equal(deleted[0].is_deleted, true)
  assert.equal(deleted[0].content, null)
})

test('reaction snapshots apply in revision order and ignore stale events', () => {
  const latest = reduceChatMessages([baseMessage], { type: 'message_reaction', message_id: 20, revision: 2, reactions: [{ user_id: 4, reaction: '❤️' }] })
  const stale = reduceChatMessages(latest, { type: 'message_reaction', message_id: 20, revision: 1, reactions: [] })
  assert.equal(stale[0].reaction_revision, 2)
  assert.deepEqual(stale[0].reactions, [{ user_id: 4, reaction: '❤️' }])
})

test('voice WebSocket events preserve backend voice metadata', () => {
  const voice = reduceChatMessages([], { type: 'voice_message', chat_id: 9, message_id: 24, sender_id: 4, content: null, message_type: 'voice', audio_url: '/attachments/24/content', audio_duration: 17, audio_mime_type: 'audio/webm' })
  assert.equal(voice[0].message_type, 'voice')
  assert.equal(voice[0].audio_duration, 17)
  assert.equal(voice[0].audio_mime_type, 'audio/webm')
})

import { apiRequest } from './client.ts'

export interface RegisterAccountInput {
  username: string
  email: string
  password: string
}

export function registerAccount(input: RegisterAccountInput) {
  return apiRequest<{ id: number; username: string; full_name: string | null; email: string }>('/register', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

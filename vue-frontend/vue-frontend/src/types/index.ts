export interface SourceInfo {
  title: string
  snippet: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: SourceInfo[]
  reasoning?: string
  chartPath?: string
  badges?: string[]
  timestamp: number
}

export interface ChatRequest {
  question: string
  thread_id?: string | null
  provider: string
  stream?: boolean
}

export interface ChatResponse {
  answer: string
  sources: SourceInfo[]
  thread_id: string
  reasoning: string
  chart_path?: string
  is_interrupted: boolean
  interrupt_data?: InterruptData
}

export interface InterruptData {
  type: string
  question: string
  answer: string
  sources: SourceInfo[]
  reasoning: string
  actions: { action: string; label: string }[]
}

export interface ReviewRequest {
  thread_id: string
  action: 'approve' | 'retry' | 'reject'
}

export interface UploadResponse {
  filename: string
  chunk_count: number
  page_count: number
  status: string
}

export interface AppSettings {
  provider: string
  commMode: 'rest' | 'sse' | 'ws'
  apiUrl: string
  showReasoning: boolean
  showSources: boolean
}

export type ConnStatus = 'connected' | 'connecting' | 'disconnected'

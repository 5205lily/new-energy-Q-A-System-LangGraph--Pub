import axios from 'axios'
import type { ChatRequest, ChatResponse, ReviewRequest, UploadResponse } from '@/types'

class ApiService {
  private getBaseUrl() {
    // 开发环境用 Vite proxy，生产环境用配置地址
    return ''
  }

  // 新增：添加响应拦截器用于调试
  constructor() {
    axios.interceptors.response.use(
      (response) => {
        console.log('✅ [API 原始响应]:', response.data)
        return response
      },
      (error) => {
        console.error('❌ [API 错误响应]:', error.response?.data || error.message)
        return Promise.reject(error)
      }
    )
  }

  async chat(request: ChatRequest): Promise<ChatResponse> {
    const res = await axios.post<ChatResponse>(`/api/chat`, request)
    return res.data
  }

  async chatStream(request: ChatRequest, onChunk: (data: any) => void): Promise<void> {
    const res = await fetch(`/api/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request)
    })

    if (!res.ok) {
      // 修复：尝试解析后端的错误 JSON 信息
      let errorMsg = `HTTP ${res.status}`
      try {
        const errorData = await res.json()
        errorMsg = JSON.stringify(errorData)
      } catch {
        // 如果解析失败，保留原始状态码错误
      }
      throw new Error(errorMsg)
    }
    if (!res.body) throw new Error('No response body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const data = JSON.parse(line.slice(6))
          onChunk(data)
        } catch { /* ignore parse error */ }
      }
    }
  }

  async review(request: ReviewRequest): Promise<ChatResponse> {
    const res = await axios.post<ChatResponse>(`/api/review`, request)
    return res.data
  }

  async upload(file: File): Promise<UploadResponse> {
    const formData = new FormData()
    formData.append('file', file)
    const res = await axios.post<UploadResponse>(`/api/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    return res.data
  }

  async getHistory(threadId: string): Promise<any> {
    const res = await axios.get(`/api/history/${threadId}`)
    return res.data
  }

  async clearHistory(threadId: string): Promise<void> {
    await axios.delete(`/api/history/${threadId}`)
  }
}

export const api = new ApiService()
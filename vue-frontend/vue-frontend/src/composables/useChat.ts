import { ref } from 'vue'
import { useChatStore } from '@/stores/chat'
import { api } from '@/services/api'
import type { ChatMessage } from '@/types'

// 新增：安全字符串转换函数
function safeString(value: any): string {
  if (typeof value === 'string') return value
  if (value && typeof value === 'object') {
    const extracted = value.answer || value.content || value.message || value.detail
    if (extracted && typeof extracted === 'string') return extracted
    return JSON.stringify(value)
  }
  return String(value ?? '')
}

export function useChat() {
  const store = useChatStore()
  const ws = ref<WebSocket | null>(null)

  async function sendMessage(question: string) {
    if (store.isStreaming) return

    // 添加用户消息
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: question,
      timestamp: Date.now()
    }
    store.addMessage(userMsg)
    store.setStreaming(true)
    store.setInterrupted(false)

    const mode = store.settings.commMode
    const provider = store.settings.provider

    try {
      if (mode === 'sse') {
        await sendSSE(question, provider)
      } else if (mode === 'ws') {
        await sendWS(question, provider)
      } else {
        await sendREST(question, provider)
      }
    } catch (err: any) {
      store.addMessage({
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `❌ 请求失败: ${safeString(err.response?.data || err.message || err)}`,
        badges: ['错误'],
        timestamp: Date.now()
      })
    } finally {
      store.setStreaming(false)
    }
  }

  async function sendREST(question: string, provider: string) {
    const res = await api.chat({
      question,
      thread_id: store.threadId,
      provider
    })

    store.setThreadId(res.thread_id)

    if (res.is_interrupted && res.interrupt_data) {
      store.setInterrupted(true, res.interrupt_data)
    } else {
      store.addMessage({
        id: Date.now().toString(),
        role: 'assistant',
        content: safeString(res.answer || res), // 修复：安全提取
        sources: res.sources,
        reasoning: res.reasoning,
        chartPath: res.chart_path,
        badges: res.chart_path ? ['图表Agent'] : undefined,
        timestamp: Date.now()
      })
    }
  }

  async function sendSSE(question: string, provider: string) {
    let answer = ''
    let msgId = ''
    let sources: any[] = []
    let chartPath: string | undefined

    await api.chatStream(
      { question, thread_id: store.threadId, provider, stream: true },
      (data) => {
        if (data.type === 'start') {
          store.setThreadId(data.thread_id)
        } else if (data.type === 'token') {
          answer += safeString(data.content) // 修复：安全累加
          if (!msgId) {
            msgId = Date.now().toString()
            store.addMessage({
              id: msgId,
              role: 'assistant',
              content: answer,
              timestamp: Date.now()
            })
          } else {
            store.updateLastMessage({ content: answer })
          }
        } else if (data.type === 'end') {
          sources = data.sources || []
          chartPath = data.chart_path
          store.updateLastMessage({
            content: safeString(data.answer || answer), // 修复：安全提取
            sources,
            chartPath
          })
        } else if (data.type === 'error') {
          throw new Error(safeString(data.message || data)) // 修复：安全抛出
        }
      }
    )
  }

  async function sendWS(question: string, provider: string) {
    return new Promise<void>((resolve, reject) => {
      const clientId = 'client-' + Date.now()
      const wsUrl = store.settings.apiUrl
        .replace('http://', 'ws://')
        .replace('https://', 'wss://')

      ws.value = new WebSocket(`${wsUrl}/ws/chat/${clientId}`)
      store.setConnStatus('connecting')

      ws.value.onopen = () => {
        store.setConnStatus('connected')
        ws.value?.send(JSON.stringify({
          type: 'chat',
          question,
          thread_id: store.threadId,
          provider
        }))
      }

      ws.value.onmessage = (event) => {
        const data = JSON.parse(event.data)

        if (data.type === 'start') {
          store.setThreadId(data.thread_id)
        } else if (data.type === 'complete') {
          store.setThreadId(data.thread_id)
          store.addMessage({
            id: Date.now().toString(),
            role: 'assistant',
            content: safeString(data.answer || data), // 修复：安全提取
            sources: data.sources,
            reasoning: data.reasoning,
            chartPath: data.chart_path,
            badges: data.chart_path ? ['图表Agent'] : undefined,
            timestamp: Date.now()
          })
          ws.value?.close()
          resolve()
        } else if (data.type === 'interrupt') {
          store.setInterrupted(true, data.data)
          ws.value?.close()
          resolve()
        } else if (data.type === 'error') {
          ws.value?.close()
          reject(new Error(safeString(data.message || data))) // 修复：安全抛出
        }
      }

      ws.value.onerror = () => {
        store.setConnStatus('disconnected')
        reject(new Error('WebSocket 连接失败'))
      }

      ws.value.onclose = () => {
        store.setConnStatus('disconnected')
      }
    })
  }

  async function sendReview(action: 'approve' | 'retry' | 'reject') {
    if (!store.threadId) return
    store.setStreaming(true)
    store.setInterrupted(false)

    try {
      const res = await api.review({ thread_id: store.threadId, action })

      if (res.is_interrupted && res.interrupt_data) {
        store.setInterrupted(true, res.interrupt_data)
      } else {
        store.addMessage({
          id: Date.now().toString(),
          role: 'assistant',
          content: safeString(res.answer || res), // 修复：安全提取
          sources: res.sources,
          badges: ['人工审核'],
          timestamp: Date.now()
        })
      }
    } catch (err: any) {
      store.addMessage({
        id: Date.now().toString(),
        role: 'assistant',
        content: `❌ 审核失败: ${safeString(err.response?.data || err.message || err)}`, // 修复：安全提取
        badges: ['错误'],
        timestamp: Date.now()
      })
    } finally {
      store.setStreaming(false)
    }
  }

  return {
    sendMessage,
    sendReview
  }
}
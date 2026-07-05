import { useState, useEffect, useRef } from 'react'
import { getSocket } from '@shared/api/socket'
import type { Message } from '@entities/message/types'
import { MarkdownMessage } from '@shared/ui/MarkdownMessage'
import '@shared/ui/markdown.css'

export function ChatWidget() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isWaiting, setIsWaiting] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    const socket = getSocket()

    setIsConnected(socket.connected)

    const onConnect = () => {
      console.log('✅ ChatWidget: Socket подключен')
      setIsConnected(true)
    }

    const onDisconnect = () => {
      console.log('🔌 ChatWidget: Socket отключен')
      setIsConnected(false)
      setIsWaiting(false)
    }

    const onConnectError = () => {
      console.error('❌ ChatWidget: Ошибка подключения')
      setIsConnected(false)
      setIsWaiting(false)
    }

    const onAiThinking = () => {
      console.log('🤖 AI думает...')
      setIsWaiting(true)
    }

    // 🆕 ОБНОВЛЁННЫЙ ОБРАБОТЧИК — добавляет источники в ответ
    const onAiAnswer = (data: any) => {
      console.log('✅ Ответ от AI:', data)
      
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
        timeoutRef.current = null
      }
      
      setIsWaiting(false)
      
      // Берём основной текст ответа
      let answerText = data.answer || data.text || 'Ответ пустой'
      
      // 🆕 Добавляем блок источников, если они есть
      if (data.sources && Array.isArray(data.sources) && data.sources.length > 0) {
        const sourcesList = data.sources
          .map((s: any, i: number) => {
            const title = s.file_name || s.title || `Источник ${i + 1}`
            const url = s.file_url
            
            // Если есть ссылка — делаем её кликабельной
            if (url) {
              return `${i + 1}. [${title}](${url})`
            }
            return `${i + 1}. ${title}`
          })
          .join('\n')
        
        answerText += `\n\n---\n\n**📚 Источники:**\n${sourcesList}`
      }
      
      const botMsg: Message = {
        id: Date.now().toString() + '-bot',
        text: answerText,
        sender: 'bot',
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, botMsg])
    }

    const onError = (data: any) => {
      console.error('❌ Ошибка:', data)
      
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
        timeoutRef.current = null
      }
      
      setIsWaiting(false)
      const errorMsg: Message = {
        id: Date.now().toString() + '-error',
        text: `⚠️ ${data.error || 'Произошла ошибка'}`,
        sender: 'bot',
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, errorMsg])
    }

    socket.on('connect', onConnect)
    socket.on('disconnect', onDisconnect)
    socket.on('connect_error', onConnectError)
    socket.on('ai_thinking', onAiThinking)
    socket.on('ai_answer', onAiAnswer)
    socket.on('error', onError)

    return () => {
      socket.off('connect', onConnect)
      socket.off('disconnect', onDisconnect)
      socket.off('connect_error', onConnectError)
      socket.off('ai_thinking', onAiThinking)
      socket.off('ai_answer', onAiAnswer)
      socket.off('error', onError)
    }
  }, [])

  const handleSend = () => {
    const text = input.trim()
    if (!text || isWaiting) return

    const socket = getSocket()

    const userMsg: Message = {
      id: Date.now().toString(),
      text,
      sender: 'user',
      timestamp: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setIsWaiting(true)

    console.log('📤 Отправляем сообщение')
    socket.emit('user_message', { text })

    timeoutRef.current = setTimeout(() => {
      setIsWaiting(false)
      const timeoutMsg: Message = {
        id: Date.now().toString() + '-timeout',
        text: '⚠️ Превышено время ожидания (60с).',
        sender: 'bot',
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, timeoutMsg])
    }, 60000)
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="card shadow-sm">
      <div className="card-header d-flex justify-content-between align-items-center">
        <span>
          Сообщения
          <span
            className={`badge ms-2 ${isConnected ? 'bg-success' : 'bg-secondary'}`}
            style={{ fontSize: '0.7em' }}
          >
            {isConnected ? '● онлайн' : '○ оффлайн'}
          </span>
        </span>
        {isWaiting && (
          <span className="badge bg-warning text-dark">
            <span className="spinner-border spinner-border-sm me-1" />
            AI думает...
          </span>
        )}
      </div>

      <div className="card-body bg-light" style={{ height: '400px', overflowY: 'auto' }}>
        {messages.length === 0 && (
          <div className="text-center text-muted mt-5">
            Напишите сообщение
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`d-flex mb-2 ${
              msg.sender === 'user' ? 'justify-content-end' : 'justify-content-start'
            }`}
          >
            <div
              className={`px-3 py-2 rounded-3 ${
                msg.sender === 'user' ? 'bg-primary text-white' : 'bg-white border'
              }`}
              style={{ maxWidth: '70%' }}
            >
              {msg.sender === 'bot' ? (
                <MarkdownMessage content={msg.text} />
              ) : (
                <div>{msg.text}</div>
              )}
              <small className="opacity-75 d-block mt-1">
                {new Date(msg.timestamp).toLocaleTimeString()}
              </small>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="card-footer">
        <div className="input-group">
          <input
            type="text"
            className="form-control"
            placeholder="Введите сообщение..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyPress}
            disabled={isWaiting}
          />
          <button
            className="btn btn-primary"
            onClick={handleSend}
            disabled={!input.trim() || isWaiting}
          >
            {isWaiting ? 'Ожидание...' : 'Отправить'}
          </button>
        </div>
      </div>
    </div>
  )
}
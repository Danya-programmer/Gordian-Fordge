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

  // Авто-скролл
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ОДИН useEffect для всех обработчиков сокета
  useEffect(() => {
    const socket = getSocket()

    if (!socket.connected) {
      socket.connect()
    }

    // Обработчики соединения
    const onConnect = () => {
      console.log('✅ Socket подключен')
      setIsConnected(true)
    }

    const onDisconnect = () => {
      console.log('🔌 Socket отключен')
      setIsConnected(false)
      setIsWaiting(false)
    }

    const onConnectError = () => {
      console.error('❌ Ошибка подключения')
      setIsConnected(false)
      setIsWaiting(false)
    }

    // Обработчики AI (в одном месте!)
    const onAiThinking = () => {
      console.log('🤖 AI думает...')
      setIsWaiting(true)
    }

    const onAiAnswer = (data: any) => {
      console.log('✅ Ответ от AI:', data)
      
      // Отменяем таймаут
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
        timeoutRef.current = null
      }
      
      setIsWaiting(false)
      const botMsg: Message = {
        id: Date.now().toString() + '-bot',
        text: data.answer,
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

    // Регистрируем ВСЕ обработчики
    socket.on('connect', onConnect)
    socket.on('disconnect', onDisconnect)
    socket.on('connect_error', onConnectError)
    socket.on('ai_thinking', onAiThinking)
    socket.on('ai_answer', onAiAnswer)
    socket.on('error', onError)

    // Cleanup
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

    if (!socket.connected) {
      const errorMsg: Message = {
        id: Date.now().toString() + '-no-connection',
        text: '⚠️ Нет соединения с сервером.',
        sender: 'bot',
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, errorMsg])
      socket.connect()
      return
    }

    const userMsg: Message = {
      id: Date.now().toString(),
      text,
      sender: 'user',
      timestamp: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setIsWaiting(true)

    socket.emit('user_message', { text })

    // Таймаут 60 секунд
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
import { io, Socket } from 'socket.io-client'

let socket: Socket | null = null

export function getSocket(): Socket {
  if (!socket) {
    socket = io('http://localhost:8000', {
      transports: ['websocket', 'polling'],
      autoConnect: false, // Подключаемся вручную в ChatWidget
      timeout: 60000, // ✅ Увеличили таймаут подключения (было по умолчанию 20000)
      reconnection: true, // ✅ Автопереподключение при обрыве
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
    })
  }
  return socket
}

export function connectSocket(): Socket {
  const s = getSocket()
  if (!s.connected) {
    s.connect()
  }
  return s
}

export function disconnectSocket() {
  if (socket) {
    socket.disconnect()
  }
}
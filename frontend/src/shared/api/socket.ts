import { io, Socket } from 'socket.io-client'

let socket: Socket | null = null

export function getSocket(): Socket {
  if (!socket) {
    // ✅ Автоматически определяет ws:// или wss://
    socket = io({
      transports: ['websocket', 'polling'],
      autoConnect: true,
      timeout: 60000,
      reconnection: true,
      reconnectionAttempts: 10,
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

// export function disconnectSocket() {
//   if (socket) {
//     socket.disconnect()
//   }
// }
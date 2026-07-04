// import axios from 'axios'

// export const api = axios.create({
//   baseURL: 'http://localhost:8000',
// })


import axios from 'axios'

// ✅ Используем относительный URL — Nginx проксирует на backend
export const api = axios.create({
  baseURL: '/api',  // Вместо http://localhost:8000
  timeout: 60000,
})
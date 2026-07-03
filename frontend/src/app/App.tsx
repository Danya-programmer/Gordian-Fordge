import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from '@shared/ui/Layout'
import { ChatPage } from '@pages/ChatPage'
import { UploadPage } from '@pages/UploadPage'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<ChatPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App

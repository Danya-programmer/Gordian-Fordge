import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from '@shared/ui/Layout'
import { ChatPage } from '@pages/ChatPage'
import { UploadPage } from '@pages/UploadPage'

export default function App() {
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
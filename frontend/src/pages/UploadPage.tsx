import { useState } from 'react'
import { FileUploader } from '@features/upload/FileUploader'
import { DocumentsList } from '@features/documents/DocumentsList'
import type { PendingFile } from '@entities/document/types'

export function UploadPage() {
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([])
  

  const handleUploadStart = (filename: string, fileSize: number) => {
    const newPending: PendingFile = {
      tempId: `pending-${Date.now()}-${Math.random()}`,
      original_name: filename,
      file_size: fileSize,
      status: 'uploading',
    }
    // Добавляем в начало (стек — новые сверху)
    setPendingFiles((prev) => [newPending, ...prev])
  }

  const handleUploadSuccess = () => {
    // Ничего не делаем — реальный документ придёт через WebSocket
  }

  const handleUploadError = (error: string) => {
    // Убираем последний pending файл (он не дошёл до сервера)
    setPendingFiles((prev) => prev.slice(1))
    console.error('Upload error:', error)
  }

  return (
    <div>
      <h2 className="mb-4">📤 Загрузка файлов</h2>

      <FileUploader
        onUploadStart={handleUploadStart}
        onUploadSuccess={handleUploadSuccess}
        onUploadError={handleUploadError}
      />

      <div className="mt-4">
        <DocumentsList pendingFiles={pendingFiles} />
      </div>
    </div>
  )
}
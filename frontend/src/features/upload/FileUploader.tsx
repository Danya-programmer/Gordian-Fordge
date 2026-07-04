import { useState, type DragEvent, type ChangeEvent } from 'react'
import { api } from '@shared/api/http'

interface FileUploaderProps {
  // Вызывается сразу при начале загрузки (для оптимистичного UI)
  onUploadStart?: (filename: string, fileSize: number) => void
  // Вызывается при успехе
  onUploadSuccess?: () => void
  // Вызывается при ошибке
  onUploadError?: (error: string) => void
}

export function FileUploader({ onUploadStart, onUploadSuccess, onUploadError }: FileUploaderProps) {
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [notice, setNotice] = useState<{ type: 'success' | 'warning' | 'danger'; text: string } | null>(null)

  const showNotice = (type: 'success' | 'warning' | 'danger', text: string) => {
    setNotice({ type, text })
    setTimeout(() => setNotice(null), 4000)
  }

  const uploadFile = async (file: File) => {
    const ext = '.' + (file.name.split('.').pop()?.toLowerCase() || '')
    if (!['.pdf', '.docx', '.doc', '.pptx'].includes(ext)) {
      showNotice('danger', 'Разрешены только .pdf/.docx/.doc/.pptx')
      return
    }

    setUploading(true)
    setNotice(null)

    // 🆕 Сразу уведомляем родителя — файл "появился" в списке
    onUploadStart?.(file.name, file.size)

    const formData = new FormData()
    formData.append('file', file)

    try {
      await api.post('/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      showNotice('success', `Файл "${file.name}" отправлен на сервер`)
      onUploadSuccess?.()
    } catch (err: any) {
      const errorMsg = err?.response?.data?.detail || err?.message || 'Неизвестная ошибка'
      showNotice('danger', `Ошибка загрузки: ${errorMsg}`)
      onUploadError?.(errorMsg)
    } finally {
      setUploading(false)
    }
  }

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) uploadFile(file)
  }

  const handleFileInput = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) uploadFile(file)
    e.target.value = ''
  }

  return (
    <div>
      <div
        className={`border border-2 rounded-3 p-5 text-center ${
          dragOver ? 'border-primary bg-light' : 'border-secondary'
        } ${uploading ? 'opacity-50' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <h4>📎 Перетащите файл сюда</h4>
        <p className="text-muted mb-3">или</p>
        <label className={`btn btn-primary ${uploading ? 'disabled' : ''}`}>
          {uploading ? 'Загрузка...' : 'Выбрать файл'}
          <input
            type="file"
            onChange={handleFileInput}
            hidden
            disabled={uploading}
          />
        </label>
        <div className="mt-2 small text-muted">
          .pdf, .docx, .doc, .pptx
        </div>
      </div>

      {notice && (
        <div className={`alert alert-${notice.type} py-2 mt-3`}>{notice.text}</div>
      )}
    </div>
  )
}
import { useState, type DragEvent, type ChangeEvent } from 'react'
import { api } from '@shared/api/http'
import type { UploadedFile } from '@entities/file/types'

export function FileUploader() {
  // Локальное хранилище — работает всегда, даже без бэкенда
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [notice, setNotice] = useState<{ type: 'success' | 'warning' | 'danger'; text: string } | null>(null)

  const showNotice = (type: 'success' | 'warning' | 'danger', text: string) => {
    setNotice({ type, text })
    setTimeout(() => setNotice(null), 4000)
  }

  const addFileLocally = (file: File) => {
    const localFile: UploadedFile = {
      filename: file.name,
      size: file.size,
      extension: '.' + file.name.split('.').pop()?.toLowerCase(),
    }
    setFiles((prev) => [...prev, localFile])
  }

  const uploadFile = async (file: File) => {
    // Проверяем расширение
    const ext = '.' + (file.name.split('.').pop()?.toLowerCase() || '')
    if (!['.pdf', '.docx'].includes(ext)) {
      showNotice('danger', 'Разрешены только PDF и DOCX файлы')
      return
    }

    setUploading(true)
    setNotice(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      await api.post('/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      // Успех на сервере — добавляем локально (чтобы не дублировать)
      addFileLocally(file)
      showNotice('success', `Файл "${file.name}" загружен на сервер`)
    } catch (err: any) {
      // Сервер недоступен — сохраняем локально и предупреждаем
      addFileLocally(file)
      showNotice('warning', 'Сервер недоступен. Файл сохранён только локально в браузере.')
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

  const removeFile = (idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx))
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  }

  return (
    <div>
      <div
        className={`border border-2 rounded-3 p-5 text-center mb-4 ${
          dragOver ? 'border-primary bg-light' : 'border-secondary'
        }`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <h4>📎 Перетащите файл сюда</h4>
        <p className="text-muted mb-3">или</p>
        <label className="btn btn-primary">
          Выбрать файл (PDF/DOCX)
          <input type="file" accept=".pdf,.docx" onChange={handleFileInput} hidden />
        </label>
        {uploading && (
          <div className="mt-3">
            <div className="spinner-border spinner-border-sm" role="status" />
            <span className="ms-2">Загрузка...</span>
          </div>
        )}
      </div>

      {notice && (
        <div className={`alert alert-${notice.type} py-2`}>{notice.text}</div>
      )}

      <div className="card">
        <div className="card-header">
          <strong>Загруженные файлы ({files.length})</strong>
        </div>
        <ul className="list-group list-group-flush">
          {files.length === 0 && (
            <li className="list-group-item text-muted text-center">Файлов пока нет</li>
          )}
          {files.map((file, idx) => (
            <li
              key={idx}
              className="list-group-item d-flex justify-content-between align-items-center"
            >
              <div>
                <span className="me-2">{file.extension === '.pdf' ? '📄' : '📝'}</span>
                <strong>{file.filename}</strong>
              </div>
              <div>
                <span className="badge bg-secondary me-2">{formatSize(file.size)}</span>
                <button
                  className="btn btn-sm btn-outline-danger"
                  onClick={() => removeFile(idx)}
                >
                  ✕
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
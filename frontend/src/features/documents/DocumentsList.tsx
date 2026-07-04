import { useEffect, useState, useRef } from 'react'
import { getSocket } from '@shared/api/socket'
import type { Document, PendingFile } from '@entities/document/types'

interface DocumentsListProps {
  pendingFiles?: PendingFile[]
}

export function DocumentsList({ pendingFiles = [] }: DocumentsListProps) {
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [socketConnected, setSocketConnected] = useState(false)
  const requestedRef = useRef(false)

  useEffect(() => {
    const socket = getSocket()

    const handleConnect = () => {
      console.log('[DocumentsList] ✅ Socket подключен')
      setSocketConnected(true)

      if (!requestedRef.current) {
        console.log('[DocumentsList] 📤 Запрашиваю список документов...')
        requestedRef.current = true
        socket.emit('get_documents')
      }
    }

    const handleDocumentsList = (data: { documents: Document[] }) => {
      console.log('[DocumentsList] ✅ Получен список:', data.documents?.length, 'документов')
      setDocuments(data.documents || [])
      setLoading(false)
    }

    const handleStatusUpdate = (update: Document) => {
      console.log('[DocumentsList] 🔄 Обновление статуса:', update.id, update.status)
      setDocuments((prev) => {
        const exists = prev.some((d) => d.id === update.id)
        if (exists) {
          return prev.map((d) => (d.id === update.id ? { ...d, ...update } : d))
        }
        return [update, ...prev]
      })
    }

    const handleError = (err: any) => {
      console.error('[DocumentsList] ❌ Ошибка:', err)
      setLoading(false)
    }

    const handleDisconnect = () => {
      console.log('[DocumentsList] 🔌 Socket отключен')
      setSocketConnected(false)
    }

    socket.on('connect', handleConnect)
    socket.on('documents_list', handleDocumentsList)
    socket.on('document_status_update', handleStatusUpdate)
    socket.on('error', handleError)
    socket.on('disconnect', handleDisconnect)

    if (socket.connected && !requestedRef.current) {
      console.log('[DocumentsList] ✅ Socket уже подключен, запрашиваю список')
      setSocketConnected(true)
      requestedRef.current = true
      socket.emit('get_documents')
    }

    return () => {
      socket.off('connect', handleConnect)
      socket.off('documents_list', handleDocumentsList)
      socket.off('document_status_update', handleStatusUpdate)
      socket.off('error', handleError)
      socket.off('disconnect', handleDisconnect)
    }
  }, [])

  // Фильтруем: показываем только документы БЕЗ статуса failed
  const visibleDocuments = documents.filter((doc) => doc.status !== 'failed')
  
  // Pending файлы
  const visiblePending = pendingFiles.filter(
    (pf) => !documents.some((d) => d.original_name === pf.original_name)
  )

  const formatSize = (bytes: number) => {
    if (!bytes) return '—'
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'uploading':
        return (
          <span className="badge bg-warning text-dark">
            <span
              className="spinner-border spinner-border-sm me-1"
              style={{ width: '0.7rem', height: '0.7rem' }}
            />
            Загрузка
          </span>
        )
      case 'processing':
        return (
          <span className="badge bg-info text-dark">
            <span
              className="spinner-border spinner-border-sm me-1"
              style={{ width: '0.7rem', height: '0.7rem' }}
            />
            Обработка
          </span>
        )
      case 'ready':
        return <span className="badge bg-success">✓ Готов</span>
      default:
        return <span className="badge bg-secondary">{status}</span>
    }
  }

  const getIcon = (filename: string) => {
    const ext = filename.split('.').pop()?.toLowerCase()
    if (ext === 'pdf') return '📄'
    if (ext === 'docx' || ext === 'doc') return '📝'
    if (ext === 'pptx') return '📊'
    return '📎'
  }

  const totalCount = visibleDocuments.length + visiblePending.length

  return (
    <div className="card">
      <div className="card-header d-flex justify-content-between align-items-center">
        <strong>📚 Источники ({totalCount})</strong>
        <div className="d-flex align-items-center gap-2">
          {!socketConnected && (
            <small className="text-warning">⚠️ Нет соединения</small>
          )}
          {loading && (
            <span className="spinner-border spinner-border-sm" role="status" />
          )}
        </div>
      </div>

      <ul className="list-group list-group-flush" style={{ maxHeight: '500px', overflowY: 'auto' }}>
        {loading && totalCount === 0 && (
          <li className="list-group-item text-center text-muted py-4">
            <span className="spinner-border spinner-border-sm me-2" />
            Загрузка списка документов...
          </li>
        )}

        {!loading && !socketConnected && totalCount === 0 && (
          <li className="list-group-item text-center text-warning py-4">
            ⚠️ Нет соединения с сервером. Обновите страницу.
          </li>
        )}

        {!loading && socketConnected && totalCount === 0 && (
          <li className="list-group-item text-center text-muted py-4">
            📭 Источники еще не загружены.
            <br />
            <small>Загрузите первый файл выше, чтобы начать работу.</small>
          </li>
        )}

        {visiblePending.map((pf) => (
          <li
            key={pf.tempId}
            className="list-group-item d-flex justify-content-between align-items-center opacity-75"
          >
            <div className="d-flex align-items-center">
              <span className="me-2 fs-5">{getIcon(pf.original_name)}</span>
              <div>
                <div className="fw-semibold">{pf.original_name}</div>
                <small className="text-muted">{formatSize(pf.file_size)}</small>
              </div>
            </div>
            {getStatusBadge('uploading')}
          </li>
        ))}

        {visibleDocuments.map((doc) => (
          <li
            key={doc.id}
            className="list-group-item d-flex justify-content-between align-items-center"
          >
            <div className="d-flex align-items-center flex-grow-1 me-3" style={{ minWidth: 0 }}>
              <span className="me-2 fs-5">{getIcon(doc.original_name)}</span>
              <div style={{ minWidth: 0 }}>
                <div className="fw-semibold text-truncate" title={doc.original_name}>
                  {doc.original_name}
                </div>
                <small className="text-muted">
                  {formatSize(doc.file_size)}
                  {doc.status === 'ready' && doc.chunks_count > 0 && (
                    <> · {doc.chunks_count} чанков · {doc.nodes_count} узлов</>
                  )}
                  {doc.created_at && (
                    <> · {new Date(doc.created_at).toLocaleDateString('ru-RU')}</>
                  )}
                </small>
              </div>
            </div>
            <div className="d-flex align-items-center gap-2 flex-shrink-0">
              {getStatusBadge(doc.status)}
              {doc.status === 'ready' && doc.file_url && (
                <a
                  href={doc.file_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-sm btn-outline-primary"
                  title="Открыть файл"
                >
                  🔗
                </a>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
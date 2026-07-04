export type DocumentStatus = 'uploading' | 'processing' | 'ready' | 'failed'

export interface Document {
  id: string
  original_name: string
  file_size: number
  mime_type?: string
  status: DocumentStatus
  error_message?: string
  chunks_count: number
  nodes_count: number
  edges_count: number
  file_url?: string
  created_at?: string
  processed_at?: string
}

// Оптимистичная запись — пока сервер не прислал реальный документ
export interface PendingFile {
  tempId: string
  original_name: string
  file_size: number
  status: 'uploading'
}
import { FileUploader } from '@features/upload/FileUploader'

export function UploadPage() {
  return (
    <div>
      <h2 className="mb-4">Загрузка файлов</h2>
      <FileUploader />
    </div>
  )
}
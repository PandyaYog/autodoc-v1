import { useState, useCallback } from 'react'
import { ArrowLeft, ArrowRight, Loader2 } from 'lucide-react'
import DropZone from '../components/DropZone'
import Button from '../components/shared/Button'
import { useToast } from '../context/ToastContext'
import { uploadProject } from '../services/api'
import styles from './UploadPage.module.css'

export default function UploadPage({ setPage }) {
  const [selectedFile, setSelectedFile] = useState(null)
  const [isUploading, setIsUploading]   = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const { addToast } = useToast()

  /* ── File selection handlers ────────────────────────────────── */
  const handleFileSelect = useCallback((file) => {
    setSelectedFile(file)
  }, [])

  const handleFileClear = useCallback(() => {
    setSelectedFile(null)
    setUploadProgress(0)
  }, [])

  /* ── Upload handler (Step 3.2) ──────────────────────────────── */
  const handleSubmit = async () => {
    if (!selectedFile || isUploading) return

    setIsUploading(true)
    setUploadProgress(0)

    try {
      const data = await uploadProject(selectedFile, (progressEvent) => {
        if (progressEvent.total) {
          const pct = Math.round((progressEvent.loaded * 100) / progressEvent.total)
          setUploadProgress(pct)
        }
      })

      // Navigate to processing page, passing the task_id
      setPage('processing', { taskId: data.task_id })

    } catch (err) {
      setIsUploading(false)
      setUploadProgress(0)
      // Navigate to error page with the error message
      setPage('error', { error: err.message })
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>

        {/* ── Header ── */}
        <div className={styles.header}>
          <div className={styles.headerIcon}>
            <ArrowRight size={22} strokeWidth={2} />
          </div>
          <div>
            <h1 className={styles.title}>Upload Your Project</h1>
            <p className={styles.subtitle}>
              Zip your project folder and drop it below. AutoDoc will analyze your
              codebase and generate comprehensive PDF documentation.
            </p>
          </div>
        </div>

        {/* ── Drop Zone ── */}
        <DropZone
          selectedFile={selectedFile}
          onFileSelect={handleFileSelect}
          onFileClear={handleFileClear}
        />

        {/* ── Upload progress bar (shown during upload) ── */}
        {isUploading && uploadProgress > 0 && uploadProgress < 100 && (
          <div className={styles.progressWrap}>
            <div className={styles.progressBar}>
              <div
                className={styles.progressFill}
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
            <span className={styles.progressLabel}>Uploading… {uploadProgress}%</span>
          </div>
        )}

        {/* ── Actions ── */}
        <div className={styles.actions}>
          <Button
            variant="primary"
            size="lg"
            fullWidth
            disabled={!selectedFile}
            loading={isUploading}
            onClick={handleSubmit}
          >
            {isUploading ? 'Uploading…' : 'Generate Documentation'}
          </Button>

          <button
            className={styles.backLink}
            onClick={() => setPage('home')}
            disabled={isUploading}
          >
            <ArrowLeft size={14} strokeWidth={2.5} />
            Back to Home
          </button>
        </div>

        {/* ── Reassurance note ── */}
        <p className={styles.note}>
          🔒 Your files are processed locally and never stored permanently.
        </p>

      </div>
    </div>
  )
}

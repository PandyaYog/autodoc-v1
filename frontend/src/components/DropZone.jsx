import { useRef, useState, useCallback } from 'react'
import { UploadCloud, CheckCircle, FileArchive, X, AlertCircle } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { MAX_FILE_SIZE_BYTES } from '../config/api'
import styles from './DropZone.module.css'

/** Format bytes into a human-readable string (e.g., "2.4 MB") */
function formatBytes(bytes) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

/**
 * DropZone — drag-and-drop file input for .zip files.
 *
 * Props:
 *   onFileSelect(file) — called when a valid file is chosen or dropped
 *   onFileClear()      — called when the user clears the selection
 *   selectedFile       — the currently selected File object (or null)
 */
export default function DropZone({ onFileSelect, onFileClear, selectedFile }) {
  const [isDragging, setIsDragging] = useState(false)
  const inputRef = useRef(null)
  const dragCounter = useRef(0) // track nested drag-enter/leave correctly
  const { addToast } = useToast()

  /* ── Validation ─────────────────────────────────────────────── */
  const validate = useCallback((file) => {
    if (!file) return false

    if (!file.name.toLowerCase().endsWith('.zip')) {
      addToast({
        type: 'error',
        message: `"${file.name}" is not a ZIP file. Please upload a .zip archive.`,
      })
      return false
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
      addToast({
        type: 'error',
        message: `File is too large (${formatBytes(file.size)}). Maximum allowed size is 100 MB.`,
      })
      return false
    }

    return true
  }, [addToast])

  /* ── Drag event handlers ─────────────────────────────────────── */
  const handleDragEnter = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current += 1
    if (dragCounter.current === 1) setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current -= 1
    if (dragCounter.current === 0) setIsDragging(false)
  }, [])

  const handleDragOver = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
  }, [])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current = 0
    setIsDragging(false)

    const file = e.dataTransfer.files?.[0]
    if (file && validate(file)) {
      onFileSelect(file)
    }
  }, [validate, onFileSelect])

  /* ── Click to browse ────────────────────────────────────────── */
  const handleClick = () => {
    if (!selectedFile) inputRef.current?.click()
  }

  const handleInputChange = (e) => {
    const file = e.target.files?.[0]
    if (file && validate(file)) {
      onFileSelect(file)
    }
    // Reset so the same file can be re-selected after clearing
    e.target.value = ''
  }

  const handleClear = (e) => {
    e.stopPropagation()
    onFileClear()
  }

  /* ── Render ─────────────────────────────────────────────────── */
  const hasFile = Boolean(selectedFile)

  return (
    <div
      className={[
        styles.zone,
        isDragging && !hasFile ? styles.dragging : '',
        hasFile ? styles.hasFile : '',
      ].filter(Boolean).join(' ')}
      onClick={handleClick}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      role="button"
      tabIndex={0}
      aria-label="File upload zone"
      onKeyDown={(e) => e.key === 'Enter' && handleClick()}
    >
      {/* Hidden native file input */}
      <input
        ref={inputRef}
        type="file"
        accept=".zip,application/zip,application/x-zip-compressed"
        onChange={handleInputChange}
        className={styles.hiddenInput}
        aria-hidden="true"
        tabIndex={-1}
      />

      {/* ── File selected state ── */}
      {hasFile ? (
        <div className={styles.selectedState}>
          <div className={styles.fileIcon}>
            <CheckCircle size={32} strokeWidth={1.75} />
          </div>
          <div className={styles.fileInfo}>
            <span className={styles.fileName}>{selectedFile.name}</span>
            <span className={styles.fileSize}>{formatBytes(selectedFile.size)}</span>
          </div>
          <button
            className={styles.clearBtn}
            onClick={handleClear}
            aria-label="Remove selected file"
            title="Remove file"
          >
            <X size={16} strokeWidth={2.5} />
          </button>
        </div>
      ) : (
        /* ── Idle / drag-over state ── */
        <div className={styles.idleState}>
          <div className={`${styles.uploadIcon} ${isDragging ? styles.iconDragging : ''}`}>
            {isDragging
              ? <FileArchive size={40} strokeWidth={1.5} />
              : <UploadCloud size={40} strokeWidth={1.5} />
            }
          </div>
          <div className={styles.idleText}>
            {isDragging ? (
              <p className={styles.dropHint}>Release to upload</p>
            ) : (
              <>
                <p className={styles.primaryHint}>
                  Drag &amp; drop your <strong>.zip</strong> file here
                </p>
                <p className={styles.secondaryHint}>
                  or{' '}
                  <span className={styles.browseLink}>click to browse</span>
                </p>
              </>
            )}
          </div>
          <div className={styles.constraint}>
            <AlertCircle size={12} strokeWidth={2} />
            <span>ZIP files only · Max 100 MB</span>
          </div>
        </div>
      )}
    </div>
  )
}

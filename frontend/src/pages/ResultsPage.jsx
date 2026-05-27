import { useState } from 'react'
import { CheckCircle, Download, RefreshCw, FileText, Clock } from 'lucide-react'
import Button from '../components/shared/Button'
import buttonStyles from '../components/shared/Button.module.css'
import PDFPreview from '../components/PDFPreview'
import { useToast } from '../context/ToastContext'
import { ENDPOINTS } from '../config/api'
import styles from './ResultsPage.module.css'

/** Returns a formatted timestamp string, e.g. "27 May 2026, 10:45 PM" */
function formatTimestamp() {
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  }).format(new Date())
}

/**
 * Derive a clean filename from the download URL.
 * e.g. "http://…/download/abc-123" → "abc-123_documentation.pdf"
 */
function derivePdfFilename(downloadUrl) {
  if (!downloadUrl) return 'documentation.pdf'
  const taskId = downloadUrl.split('/').pop()
  return `${taskId}_documentation.pdf`
}

export default function ResultsPage({ setPage, downloadUrl }) {
  const { addToast } = useToast()

  // Construct the full download URL from the backend
  // downloadUrl may already be absolute or just a path
  const fullDownloadUrl = downloadUrl?.startsWith('http')
    ? downloadUrl
    : downloadUrl
      ? `${ENDPOINTS.download(downloadUrl.split('/').pop())}`
      : null

  const pdfFilename  = derivePdfFilename(fullDownloadUrl)
  const generatedAt  = formatTimestamp()

  return (
    <div className={styles.page}>

      {/* ── Left Sidebar ────────────────────────────────────────── */}
      <aside className={styles.sidebar}>

        {/* Success banner */}
        <div className={styles.successBanner}>
          <div className={styles.successIcon}>
            <CheckCircle size={28} strokeWidth={1.75} />
          </div>
          <div>
            <h2 className={styles.successTitle}>Documentation Generated!</h2>
            <p className={styles.successSub}>Your PDF is ready to download.</p>
          </div>
        </div>

        {/* File metadata */}
        <div className={styles.metaCard}>
          <div className={styles.metaRow}>
            <FileText size={16} strokeWidth={1.75} className={styles.metaIcon} />
            <div>
              <span className={styles.metaLabel}>File</span>
              <span className={styles.metaValue}>{pdfFilename}</span>
            </div>
          </div>
          <div className={styles.metaDivider} />
          <div className={styles.metaRow}>
            <Clock size={16} strokeWidth={1.75} className={styles.metaIcon} />
            <div>
              <span className={styles.metaLabel}>Generated</span>
              <span className={styles.metaValue}>{generatedAt}</span>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className={styles.actions}>
          <a
            href={fullDownloadUrl}
            download={pdfFilename}
            className={`${buttonStyles.btn} ${buttonStyles.primary} ${buttonStyles.lg} ${buttonStyles.fullWidth}`}
            style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
            disabled={!fullDownloadUrl}
          >
            <Download size={18} strokeWidth={2} />
            Download PDF
          </a>

          <Button
            variant="ghost"
            size="md"
            fullWidth
            onClick={() => setPage('upload')}
          >
            <RefreshCw size={16} strokeWidth={2} />
            Generate Another
          </Button>
        </div>

        {/* Note */}
        <p className={styles.note}>
          This session will expire after one hour. Download your PDF before then.
        </p>

      </aside>

      {/* ── Right Panel — PDF Preview ────────────────────────────── */}
      <main className={styles.previewPanel}>
        {fullDownloadUrl ? (
          <PDFPreview
            url={fullDownloadUrl}
            downloadUrl={fullDownloadUrl}
          />
        ) : (
          <div className={styles.noPreview}>
            <FileText size={48} strokeWidth={1} />
            <p>No download URL available.</p>
            <button
              className={styles.backLink}
              onClick={() => setPage('upload')}
            >
              ← Try again
            </button>
          </div>
        )}
      </main>

    </div>
  )
}

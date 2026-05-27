import { useState, useCallback } from 'react'
import { Document, Page } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'
import { ChevronLeft, ChevronRight, AlertTriangle, ExternalLink } from 'lucide-react'
import Spinner from './shared/Spinner'
import styles from './PDFPreview.module.css'

/**
 * PDFPreview — renders a paginated PDF from a backend URL.
 *
 * Props:
 *   url         — download URL from the backend (e.g. http://localhost:8000/api/v1/download/{id})
 *   downloadUrl — same URL, used for the fallback "Download directly" link
 */
export default function PDFPreview({ url, downloadUrl }) {
  const [numPages, setNumPages]   = useState(null)
  const [pageNumber, setPageNumber] = useState(1)
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState(null)

  /* ── react-pdf callbacks ─────────────────────────────────────── */
  const onDocumentLoadSuccess = useCallback(({ numPages }) => {
    setNumPages(numPages)
    setLoading(false)
    setError(null)
  }, [])

  const onDocumentLoadError = useCallback((err) => {
    console.error('[PDFPreview] Load error:', err)
    setLoading(false)
    setError('Unable to load PDF preview.')
  }, [])

  const onPageLoadSuccess = useCallback(() => {
    setLoading(false)
  }, [])

  /* ── Pagination ──────────────────────────────────────────────── */
  const prevPage = () => setPageNumber(p => Math.max(1, p - 1))
  const nextPage = () => setPageNumber(p => Math.min(numPages ?? 1, p + 1))

  /* ── Error state ─────────────────────────────────────────────── */
  if (error) {
    return (
      <div className={styles.errorState}>
        <AlertTriangle size={36} strokeWidth={1.5} />
        <p className={styles.errorText}>{error}</p>
        <a
          href={downloadUrl}
          target="_blank"
          rel="noopener noreferrer"
          className={styles.directLink}
        >
          <ExternalLink size={14} />
          Download directly instead
        </a>
      </div>
    )
  }

  return (
    <div className={styles.wrapper}>
      {/* ── PDF Document ── */}
      <div className={styles.documentWrap}>
        {/* Loading skeleton shown while PDF fetches */}
        {loading && (
          <div className={styles.skeleton}>
            <Spinner size="lg" label="Loading PDF preview…" />
            <p className={styles.skeletonText}>Loading preview…</p>
          </div>
        )}

        <Document
          file={url}
          onLoadSuccess={onDocumentLoadSuccess}
          onLoadError={onDocumentLoadError}
          loading={null}      /* we handle loading UI ourselves */
          className={styles.document}
        >
          <Page
            pageNumber={pageNumber}
            onLoadSuccess={onPageLoadSuccess}
            onLoadError={() => setError('Failed to render this page.')}
            width={Math.min(700, window.innerWidth - 80)}
            renderAnnotationLayer
            renderTextLayer
            loading={null}
            className={styles.page}
          />
        </Document>
      </div>

      {/* ── Pagination controls ── */}
      {numPages && numPages > 1 && (
        <div className={styles.pagination}>
          <button
            className={styles.pageBtn}
            onClick={prevPage}
            disabled={pageNumber <= 1}
            aria-label="Previous page"
          >
            <ChevronLeft size={18} strokeWidth={2} />
          </button>

          <span className={styles.pageLabel}>
            Page <strong>{pageNumber}</strong> of <strong>{numPages}</strong>
          </span>

          <button
            className={styles.pageBtn}
            onClick={nextPage}
            disabled={pageNumber >= numPages}
            aria-label="Next page"
          >
            <ChevronRight size={18} strokeWidth={2} />
          </button>
        </div>
      )}
    </div>
  )
}

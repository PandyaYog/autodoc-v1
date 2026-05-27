import { AlertTriangle, RefreshCcw, Home } from 'lucide-react'
import Button from '../components/shared/Button'
import styles from './ErrorPage.module.css'

export default function ErrorPage({ setPage, errorMessage }) {
  const displayError = errorMessage || 'An unexpected error occurred. Please try again.'

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        
        {/* ── Icon & Title ── */}
        <div className={styles.header}>
          <div className={styles.iconWrap}>
            <AlertTriangle size={48} strokeWidth={1.5} />
          </div>
          <h1 className={styles.title}>Something Went Wrong</h1>
          <p className={styles.subtitle}>
            We encountered an issue while generating your documentation.
          </p>
        </div>

        {/* ── Error Details ── */}
        <div className={styles.errorContainer}>
          <div className={styles.errorHeader}>Error Details:</div>
          <pre className={styles.errorBlock}>
            <code>{displayError}</code>
          </pre>
        </div>

        {/* ── Actions ── */}
        <div className={styles.actions}>
          <Button
            variant="primary"
            size="lg"
            fullWidth
            onClick={() => setPage('upload')}
          >
            <RefreshCcw size={18} strokeWidth={2} />
            Try Again
          </Button>
          
          <Button
            variant="ghost"
            size="md"
            fullWidth
            onClick={() => setPage('home')}
          >
            <Home size={18} strokeWidth={2} />
            Back to Home
          </Button>
        </div>
        
      </div>
    </div>
  )
}

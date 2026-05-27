import { useEffect } from 'react'
import { CheckCircle, AlertCircle, Info, AlertTriangle, X } from 'lucide-react'
import styles from './Toast.module.css'

const ICONS = {
  success: CheckCircle,
  error:   AlertCircle,
  warning: AlertTriangle,
  info:    Info,
}

/**
 * Toast — individual slide-in notification card.
 * Auto-dismisses after `duration` ms. Calls `onRemove` when dismissed.
 */
export default function Toast({ id, message, type = 'info', duration = 4000, onRemove }) {
  const Icon = ICONS[type] ?? Info

  useEffect(() => {
    const timer = setTimeout(() => onRemove(id), duration)
    return () => clearTimeout(timer)
  }, [id, duration, onRemove])

  return (
    <div className={`${styles.toast} ${styles[type]}`} role="alert" aria-live="polite">
      <span className={styles.icon}>
        <Icon size={18} strokeWidth={2} />
      </span>
      <p className={styles.message}>{message}</p>
      <button
        className={styles.close}
        onClick={() => onRemove(id)}
        aria-label="Dismiss notification"
      >
        <X size={14} strokeWidth={2.5} />
      </button>
    </div>
  )
}

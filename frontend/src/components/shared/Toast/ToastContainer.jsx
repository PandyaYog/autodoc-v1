import { useToast } from '../../../context/ToastContext'
import Toast from './Toast'
import styles from './ToastContainer.module.css'

/**
 * ToastContainer — fixed bottom-right portal that renders all active toasts.
 * Mount this once at the App root level.
 */
export default function ToastContainer() {
  const { toasts, removeToast } = useToast()

  if (toasts.length === 0) return null

  return (
    <div className={styles.container} aria-label="Notifications" role="region">
      {toasts.map(toast => (
        <Toast
          key={toast.id}
          {...toast}
          onRemove={removeToast}
        />
      ))}
    </div>
  )
}

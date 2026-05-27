import styles from './Spinner.module.css'

/**
 * Spinner — animated loading ring.
 *
 * @param {string} size    - 'sm' | 'md' | 'lg' | 'xl'
 * @param {string} color   - CSS color string (defaults to accent via CSS)
 * @param {string} label   - aria-label for screen readers
 */
export default function Spinner({ size = 'md', label = 'Loading...', className = '' }) {
  return (
    <div
      className={`${styles.spinner} ${styles[size]} ${className}`}
      role="status"
      aria-label={label}
    >
      <span className="sr-only">{label}</span>
    </div>
  )
}

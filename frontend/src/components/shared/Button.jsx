import styles from './Button.module.css'

/**
 * Button — reusable button with size and variant support.
 *
 * @param {string}  variant  - 'primary' | 'ghost' | 'danger' | 'success'
 * @param {string}  size     - 'sm' | 'md' | 'lg'
 * @param {boolean} loading  - shows a spinner and disables the button
 * @param {boolean} fullWidth - stretches button to 100% width
 */
export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  fullWidth = false,
  disabled = false,
  className = '',
  ...props
}) {
  const classes = [
    styles.btn,
    styles[variant],
    styles[size],
    fullWidth ? styles.fullWidth : '',
    loading ? styles.loading : '',
    className,
  ].filter(Boolean).join(' ')

  return (
    <button
      className={classes}
      disabled={disabled || loading}
      {...props}
    >
      {loading && (
        <span className={styles.spinner} aria-hidden="true" />
      )}
      <span
        className={loading ? styles.loadingText : ''}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 'inherit', justifyContent: 'center' }}
      >
        {children}
      </span>
    </button>
  )
}

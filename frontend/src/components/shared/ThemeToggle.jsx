import { Sun, Moon } from 'lucide-react'
import { useTheme } from '../../context/ThemeContext'
import styles from './ThemeToggle.module.css'

/**
 * ThemeToggle — pill-shaped button that swaps light ↔ dark mode.
 * Sun and Moon icons crossfade via CSS transitions.
 */
export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'

  return (
    <button
      className={styles.toggle}
      onClick={toggleTheme}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      <span className={`${styles.icon} ${isDark ? styles.hidden : styles.visible}`}>
        <Sun size={16} strokeWidth={2} />
      </span>
      <span className={`${styles.icon} ${isDark ? styles.visible : styles.hidden}`}>
        <Moon size={16} strokeWidth={2} />
      </span>
    </button>
  )
}

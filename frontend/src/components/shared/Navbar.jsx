import { FileText } from 'lucide-react'
import ThemeToggle from './ThemeToggle'
import styles from './Navbar.module.css'

/**
 * Navbar — top bar with logo, navigation links, and theme toggle.
 *
 * @param {function} onNavigate - called with page name when a nav link is clicked
 * @param {string}   currentPage - active page for highlight state
 */
export default function Navbar({ onNavigate, currentPage }) {
  return (
    <header className={styles.navbar}>
      <div className={`container ${styles.inner}`}>

        {/* Logo */}
        <button
          className={styles.logo}
          onClick={() => onNavigate('home')}
          aria-label="AutoDoc — go to home"
        >
          <span className={styles.logoIcon}>
            <FileText size={20} strokeWidth={2.5} />
          </span>
          <span className={styles.logoText}>
            Auto<span className={styles.logoAccent}>Doc</span>
          </span>
        </button>

        {/* Nav links */}
        <nav className={styles.nav} aria-label="Main navigation">
          <button
            className={`${styles.navLink} ${currentPage === 'home' ? styles.active : ''}`}
            onClick={() => onNavigate('home')}
          >
            Home
          </button>
          <a
            className={styles.navLink}
            href="https://github.com/PandyaYog/autodoc-v1"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub
          </a>
        </nav>

        {/* Right side controls */}
        <div className={styles.controls}>
          <ThemeToggle />
          <button
            className={styles.ctaBtn}
            onClick={() => onNavigate('upload')}
          >
            Try It Free
          </button>
        </div>

      </div>
    </header>
  )
}

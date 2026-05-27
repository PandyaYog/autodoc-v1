import { createContext, useContext, useState, useEffect, useCallback } from 'react'

const ThemeContext = createContext(null)

/**
 * ThemeProvider — wraps the entire app and manages light/dark theme.
 * Persists user preference to localStorage. Applies `data-theme` attribute
 * directly to the <html> element so CSS custom properties cascade globally.
 */
export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    // Read persisted preference, fall back to system preference, then 'light'
    const stored = localStorage.getItem('autodoc-theme')
    if (stored === 'light' || stored === 'dark') return stored
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    return prefersDark ? 'dark' : 'light'
  })

  // Sync `data-theme` on <html> whenever theme changes
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('autodoc-theme', theme)
  }, [theme])

  const toggleTheme = useCallback(() => {
    setTheme(prev => (prev === 'light' ? 'dark' : 'light'))
  }, [])

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

/** Convenience hook — throws if used outside ThemeProvider */
export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>')
  return ctx
}

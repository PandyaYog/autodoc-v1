import { useState } from 'react'
import { ThemeProvider } from './context/ThemeContext'
import { ToastProvider } from './context/ToastContext'
import Navbar from './components/shared/Navbar'
import ToastContainer from './components/shared/Toast/ToastContainer'
import LandingPage from './pages/LandingPage'
import UploadPage from './pages/UploadPage'
import ProcessingPage from './pages/ProcessingPage'
import ResultsPage from './pages/ResultsPage'
import ErrorPage from './pages/ErrorPage'
import './index.css'

/**
 * Page state machine:
 *   'home' → 'upload' → 'processing' → 'results'
 *                                     ↘ 'error' (from any async step)
 */
const PAGES = {
  home:       LandingPage,
  upload:     UploadPage,
  processing: ProcessingPage,
  results:    ResultsPage,
  error:      ErrorPage,
}

function AppContent() {
  const [page, setPage]               = useState('home')
  const [taskId, setTaskId]           = useState(null)
  const [downloadUrl, setDownloadUrl] = useState(null)
  const [markdown, setMarkdown]       = useState(null)
  const [errorMessage, setErrorMessage] = useState(null)

  /** Shared navigation handler — passed to Navbar and all pages */
  const navigate = (targetPage, meta = {}) => {
    if (meta.taskId)      setTaskId(meta.taskId)
    if (meta.downloadUrl) setDownloadUrl(meta.downloadUrl)
    if (meta.markdown)    setMarkdown(meta.markdown)
    if (meta.error)       setErrorMessage(meta.error)
    setPage(targetPage)
  }


  const PageComponent = PAGES[page] ?? LandingPage

  return (
    <>
      <Navbar onNavigate={navigate} currentPage={page} />

      <main>
        <PageComponent
          setPage={navigate}
          taskId={taskId}
          setTaskId={setTaskId}
          downloadUrl={downloadUrl}
          setDownloadUrl={setDownloadUrl}
          markdown={markdown}
          setMarkdown={setMarkdown}
          errorMessage={errorMessage}
          setErrorMessage={setErrorMessage}
        />
      </main>

      {/* Global toast portal — renders on top of everything */}
      <ToastContainer />
    </>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AppContent />
      </ToastProvider>
    </ThemeProvider>
  )
}

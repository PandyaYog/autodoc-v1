import { useEffect, useState, useRef } from 'react'
import { fetchTaskStatus } from '../services/api'
import { STATUS_POLL_INTERVAL_MS } from '../config/api'
import styles from './ProcessingPage.module.css'

/* ── Phase messages ─────────────────────────────────────────────
   Cycles every PHASE_INTERVAL_MS to keep the user engaged.
   Timed to roughly match real pipeline stages.
   ──────────────────────────────────────────────────────────────── */
const PHASES = [
  { label: 'Extracting file structure…',              icon: '📂' },
  { label: 'Building the code knowledge graph…',     icon: '🔗' },
  { label: 'Running AI summarization — this may take a few minutes…', icon: '🧠' },
  { label: 'Compiling documentation…',               icon: '📝' },
]

const PHASE_INTERVAL_MS = 8_000

/* ── Orbital animation ──────────────────────────────────────────
   Three concentric rings with orbiting dots, rendered purely in CSS.
   ──────────────────────────────────────────────────────────────── */
function OrbitalSpinner() {
  return (
    <div className={styles.orbital} aria-hidden="true">
      {/* Core pulsing center */}
      <div className={styles.core}>
        <div className={styles.corePulse} />
        <div className={styles.coreInner} />
      </div>

      {/* Ring 1 — innermost, fast */}
      <div className={`${styles.ring} ${styles.ring1}`}>
        <div className={`${styles.dot} ${styles.dotAccent}`} />
      </div>

      {/* Ring 2 — medium, counter-clockwise */}
      <div className={`${styles.ring} ${styles.ring2}`}>
        <div className={`${styles.dot} ${styles.dotBlue}`} />
        <div className={`${styles.dot} ${styles.dotBlue2}`} />
      </div>

      {/* Ring 3 — outermost, slow */}
      <div className={`${styles.ring} ${styles.ring3}`}>
        <div className={`${styles.dot} ${styles.dotGreen}`} />
      </div>
    </div>
  )
}

/* ── Main component ─────────────────────────────────────────────── */
export default function ProcessingPage({ taskId, setPage }) {
  const [phaseIndex, setPhaseIndex] = useState(0)
  const [fadePhase, setFadePhase]   = useState(true) // controls text fade-in/out
  const pollRef  = useRef(null)
  const phaseRef = useRef(null)

  /* ── Phase cycling ──────────────────────────────────────────── */
  useEffect(() => {
    phaseRef.current = setInterval(() => {
      // Fade out → update text → fade in
      setFadePhase(false)
      setTimeout(() => {
        setPhaseIndex(prev => (prev + 1) % PHASES.length)
        setFadePhase(true)
      }, 400)
    }, PHASE_INTERVAL_MS)

    return () => clearInterval(phaseRef.current)
  }, [])

  /* ── Status polling (Step 4.2) ──────────────────────────────── */
  useEffect(() => {
    if (!taskId) {
      // Guard: if we land here without a task ID, go back to upload
      setPage('upload')
      return
    }

    const poll = async () => {
      try {
        const data = await fetchTaskStatus(taskId)

        if (data.status === 'completed') {
          clearInterval(pollRef.current)
          setPage('results', {
            downloadUrl: data.download_url,
            // Pass markdown for potential future use; primary display is the PDF
            markdown: data.markdown,
          })
        } else if (data.status === 'failed') {
          clearInterval(pollRef.current)
          setPage('error', {
            error: data.error || 'Documentation generation failed. Please try again.',
          })
        }
        // 'pending' | 'processing' → do nothing, keep polling
      } catch (err) {
        // Network failure — keep polling; don't crash on a single missed poll
        console.warn('[ProcessingPage] Poll error:', err.message)
      }
    }

    // Fire immediately, then on interval
    poll()
    pollRef.current = setInterval(poll, STATUS_POLL_INTERVAL_MS)

    return () => clearInterval(pollRef.current)
  }, [taskId, setPage])

  const currentPhase = PHASES[phaseIndex]

  return (
    <div className={styles.page}>
      <div className={styles.card}>

        {/* ── Orbital animation ── */}
        <OrbitalSpinner />

        {/* ── Status copy ── */}
        <div className={styles.copy}>
          <h1 className={styles.headline}>Analyzing Your Codebase…</h1>

          <div className={`${styles.phaseWrap} ${fadePhase ? styles.fadeIn : styles.fadeOut}`}>
            <span className={styles.phaseIcon} aria-hidden="true">
              {currentPhase.icon}
            </span>
            <p className={styles.phaseText}>{currentPhase.label}</p>
          </div>

          <p className={styles.note}>
            Complex projects with many files may take 3–5 minutes.
            <br />
            Please keep this tab open.
          </p>
        </div>

        {/* ── Indeterminate progress bar ── */}
        <div className={styles.progressTrack} role="progressbar" aria-label="Processing">
          <div className={styles.progressSweep} />
        </div>

        {/* ── Phase dots (visual indicator of position) ── */}
        <div className={styles.phaseDots} aria-hidden="true">
          {PHASES.map((_, i) => (
            <span
              key={i}
              className={`${styles.phaseDot} ${i === phaseIndex ? styles.phaseDotActive : ''}`}
            />
          ))}
        </div>

      </div>
    </div>
  )
}

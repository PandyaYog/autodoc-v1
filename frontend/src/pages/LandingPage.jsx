import { ArrowRight, Code2, Brain, FileText, Zap, Globe, Layers } from 'lucide-react'
import Button from '../components/shared/Button'
import styles from './LandingPage.module.css'

/* ── Animated hero visual — mock pipeline ─────────────────────── */
const FILE_NODES = [
  { label: '.py',  color: '#3b82f6', delay: '0s'    },
  { label: '.tsx', color: '#a78bfa', delay: '0.4s'  },
  { label: '.css', color: '#ec4899', delay: '0.8s'  },
  { label: '.json',color: '#f59e0b', delay: '1.2s'  },
  { label: '.md',  color: '#10b981', delay: '1.6s'  },
]

const CODE_LINES = [
  { text: '## AuthContext',        width: '60%', color: '#7c6af5' },
  { text: 'Manages JWT tokens...', width: '85%', color: '#a8a8cc' },
  { text: '',                      width: '0',   color: 'transparent' },
  { text: '### login()',           width: '50%', color: '#7c6af5' },
  { text: 'Authenticates user...', width: '75%', color: '#a8a8cc' },
  { text: 'Returns: TokenPair',    width: '55%', color: '#2dd4a4' },
  { text: '',                      width: '0',   color: 'transparent' },
  { text: '### logout()',          width: '48%', color: '#7c6af5' },
  { text: 'Clears session data',   width: '65%', color: '#a8a8cc' },
]

function HeroVisual() {
  return (
    <div className={styles.heroVisual}>

      {/* Input: file nodes floating in */}
      <div className={styles.fileNodes}>
        {FILE_NODES.map(({ label, color, delay }) => (
          <div
            key={label}
            className={styles.fileChip}
            style={{ '--chip-color': color, '--chip-delay': delay }}
          >
            <Code2 size={12} />
            {label}
          </div>
        ))}
      </div>

      {/* Center: AutoDoc processing box */}
      <div className={styles.processorBox}>
        <div className={styles.processorIcon}>
          <Brain size={28} strokeWidth={1.5} />
        </div>
        <span className={styles.processorLabel}>AutoDoc AI</span>
        <div className={styles.processorDots}>
          <span /><span /><span />
        </div>
      </div>

      {/* Output: mock documentation card */}
      <div className={styles.docPreview}>
        <div className={styles.docHeader}>
          <FileText size={14} />
          <span>documentation.pdf</span>
          <span className={styles.docBadge}>✓ Ready</span>
        </div>
        <div className={styles.docLines}>
          {CODE_LINES.map((line, i) => (
            <div
              key={i}
              className={styles.docLine}
              style={{
                '--line-width': line.width,
                '--line-color': line.color,
                '--line-delay': `${i * 0.12}s`,
              }}
            />
          ))}
        </div>
      </div>

      {/* Animated flow arrows */}
      <div className={`${styles.flowArrow} ${styles.arrowLeft}`}>
        <ArrowRight size={16} />
      </div>
      <div className={`${styles.flowArrow} ${styles.arrowRight}`}>
        <ArrowRight size={16} />
      </div>

    </div>
  )
}

/* ── Feature cards ────────────────────────────────────────────── */
const FEATURES = [
  {
    icon: Globe,
    title: 'Multi-Language Support',
    description:
      'Understands Python, JavaScript, TypeScript, React, Next.js, HTML, CSS, JSON, YAML, and more — all in a single pipeline.',
    tags: ['.py', '.tsx', '.json', '.css', '.md'],
    accent: '#7c6af5',
  },
  {
    icon: Brain,
    title: 'AI-Powered Summaries',
    description:
      'Goes beyond syntax. AutoDoc maps your entire codebase architecture — functions, components, imports, and dependencies — then uses an LLM to write precise, human-readable documentation.',
    tags: ['CKG', 'LLM', 'Context-Aware'],
    accent: '#3b82f6',
  },
  {
    icon: Zap,
    title: 'Instant PDF Output',
    description:
      'Upload a ZIP, get a professionally formatted, download-ready PDF documentation file in minutes — no setup, no configuration needed.',
    tags: ['PDF', 'Markdown', 'Auto-Format'],
    accent: '#10b981',
  },
]

/* ── How It Works steps ───────────────────────────────────────── */
const HOW_STEPS = [
  {
    number: '01',
    title: 'Upload',
    description: 'Zip your project folder and drag it in. We handle the rest.',
    icon: Layers,
  },
  {
    number: '02',
    title: 'Analyze',
    description: 'AutoDoc builds a Code Knowledge Graph and runs AI summarization on every node.',
    icon: Brain,
  },
  {
    number: '03',
    title: 'Download',
    description: 'Receive a complete, structured PDF documentation file — ready to share.',
    icon: FileText,
  },
]

/* ── Main component ───────────────────────────────────────────── */
export default function LandingPage({ setPage }) {
  return (
    <div className={styles.landing}>

      {/* ─── Hero ─────────────────────────────────────────────── */}
      <section className={styles.hero}>
        {/* Noise texture overlay */}
        <div className={styles.noise} aria-hidden="true" />
        {/* Glow orbs */}
        <div className={`${styles.orb} ${styles.orb1}`} aria-hidden="true" />
        <div className={`${styles.orb} ${styles.orb2}`} aria-hidden="true" />

        <div className={`container ${styles.heroInner}`}>
          {/* Left — copy */}
          <div className={styles.heroCopy}>
            <div className={styles.heroBadge}>
              <span className={styles.heroBadgeDot} />
              AI-Powered · Open Source
            </div>

            <h1 className={styles.heroHeadline}>
              Turn Code into
              <span className={styles.heroGradient}> Clear Docs</span>
              <br />— Instantly.
            </h1>

            <p className={styles.heroSub}>
              AutoDoc analyzes your entire codebase — Python, React, Next.js, and more —
              and generates professional PDF documentation in minutes using a Code Knowledge Graph
              and LLM-powered summaries.
            </p>

            <div className={styles.heroActions}>
              <Button
                size="lg"
                onClick={() => setPage('upload')}
              >
                Upload Your Project
                <ArrowRight size={18} strokeWidth={2.5} />
              </Button>
              <button
                className={styles.learnMoreBtn}
                onClick={() => document.getElementById('features').scrollIntoView({ behavior: 'smooth' })}
              >
                See how it works ↓
              </button>
            </div>

            <div className={styles.heroMeta}>
              <span>✓ No account required</span>
              <span>✓ Free to use</span>
            </div>
          </div>

          {/* Right — animated visual */}
          <div className={styles.heroVisualWrap}>
            <HeroVisual />
          </div>
        </div>
      </section>

      {/* ─── Features ─────────────────────────────────────────── */}
      <section id="features" className={styles.features}>
        <div className="container">
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>
              Everything you need,
              <span className={styles.heroGradient}> nothing you don't</span>
            </h2>
            <p className={styles.sectionSub}>
              A focused tool built for developers who want documentation
              that actually reflects their codebase.
            </p>
          </div>

          <div className={styles.featureGrid}>
            {FEATURES.map(({ icon: Icon, title, description, tags, accent }) => (
              <div key={title} className={styles.featureCard}>
                <div className={styles.featureIconWrap} style={{ '--card-accent': accent }}>
                  <Icon size={24} strokeWidth={1.75} />
                </div>
                <h3 className={styles.featureTitle}>{title}</h3>
                <p className={styles.featureDesc}>{description}</p>
                <div className={styles.featureTags}>
                  {tags.map(tag => (
                    <span key={tag} className={styles.featureTag} style={{ '--card-accent': accent }}>
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── How It Works ─────────────────────────────────────── */}
      <section className={styles.howItWorks}>
        <div className="container">
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>How it works</h2>
            <p className={styles.sectionSub}>Three steps from codebase to documentation.</p>
          </div>

          <div className={styles.stepsRow}>
            {HOW_STEPS.map(({ number, title, description, icon: Icon }, i) => (
              <div key={number} className={styles.step}>
                {i < HOW_STEPS.length - 1 && (
                  <div className={styles.stepConnector} aria-hidden="true" />
                )}
                <div className={styles.stepNumber}>{number}</div>
                <div className={styles.stepIconWrap}>
                  <Icon size={22} strokeWidth={1.75} />
                </div>
                <h3 className={styles.stepTitle}>{title}</h3>
                <p className={styles.stepDesc}>{description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Footer CTA ───────────────────────────────────────── */}
      <section className={styles.footerCta}>
        <div className={`container ${styles.footerCtaInner}`}>
          <h2 className={styles.footerCtaTitle}>
            Ready to document your project?
          </h2>
          <p className={styles.footerCtaSub}>
            Drop your ZIP file and let AutoDoc do the heavy lifting.
          </p>
          <Button size="lg" onClick={() => setPage('upload')}>
            Get Started Free
            <ArrowRight size={18} strokeWidth={2.5} />
          </Button>
        </div>
      </section>

      {/* ─── Site Footer ──────────────────────────────────────── */}
      <footer className={styles.footer}>
        <div className={`container ${styles.footerInner}`}>
          <span className={styles.footerLogo}>
            Auto<span className={styles.heroGradient}>Doc</span>
          </span>
          <span className={styles.footerCopy}>
            MIT License © 2026
          </span>
        </div>
      </footer>

    </div>
  )
}

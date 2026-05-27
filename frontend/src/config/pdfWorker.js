/**
 * Configure the PDF.js worker for react-pdf v10 / pdfjs-dist v5.
 * Must be imported once before any <Document> is rendered.
 * Using the CDN build avoids Vite bundler conflicts with the worker binary.
 */
import { pdfjs } from 'react-pdf'

pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

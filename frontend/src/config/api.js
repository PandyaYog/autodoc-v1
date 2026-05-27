/**
 * API configuration — reads base URL from environment variable.
 * Set VITE_API_BASE_URL in your .env file for production deployments.
 */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const ENDPOINTS = {
  generate: `${API_BASE_URL}/api/v1/generate`,
  status: (taskId) => `${API_BASE_URL}/api/v1/status/${taskId}`,
  download: (taskId) => `${API_BASE_URL}/api/v1/download/${taskId}`,
};

/** Maximum allowed upload size in bytes (100 MB) */
export const MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024

/** Polling interval for task status (ms) */
export const STATUS_POLL_INTERVAL_MS = 5000

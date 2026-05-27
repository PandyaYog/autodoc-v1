import axios from 'axios'
import { ENDPOINTS } from '../config/api'

/**
 * Uploads a ZIP file to the backend and triggers documentation generation.
 *
 * @param {File} file - The ZIP file to upload.
 * @param {function} onUploadProgress - Optional Axios upload progress callback.
 * @returns {Promise<{task_id: string, message: string}>}
 * @throws {Error} with a user-friendly message on failure.
 */
export async function uploadProject(file, onUploadProgress) {
  const formData = new FormData()
  formData.append('upload_file', file)

  try {
    const response = await axios.post(ENDPOINTS.generate, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress,
    })
    return response.data
  } catch (err) {
    // Surface a clean, user-facing error message
    const detail =
      err?.response?.data?.message ||
      err?.response?.data?.detail ||
      err?.message ||
      'An unexpected error occurred during upload.'
    throw new Error(detail)
  }
}

/**
 * Polls the task status endpoint once.
 *
 * @param {string} taskId - The task ID returned by uploadProject.
 * @returns {Promise<{status: string, download_url: string|null, error: string|null, markdown: string|null}>}
 * @throws {Error} on network failure.
 */
export async function fetchTaskStatus(taskId) {
  try {
    const response = await axios.get(ENDPOINTS.status(taskId))
    return response.data
  } catch (err) {
    const detail =
      err?.response?.data?.message ||
      err?.message ||
      'Failed to fetch task status.'
    throw new Error(detail)
  }
}

import axios from 'axios'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let refreshRequest
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    const authEndpoint = /\/auth\/(?:login|register|logout|token\/refresh)\//.test(original?.url || '')
    if (error.response?.status !== 401 || original?._retry || authEndpoint) {
      return Promise.reject(error)
    }
    const refresh = localStorage.getItem('refresh_token')
    if (!refresh) {
      localStorage.removeItem('access_token')
      window.dispatchEvent(new Event('apex:session-expired'))
      return Promise.reject(error)
    }
    original._retry = true
    try {
      refreshRequest ||= axios.post(
        `${API_BASE_URL}/auth/token/refresh/`,
        { refresh },
      ).finally(() => { refreshRequest = undefined })
      const { data } = await refreshRequest
      localStorage.setItem('access_token', data.access)
      original.headers.Authorization = `Bearer ${data.access}`
      return api(original)
    } catch (refreshError) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      window.dispatchEvent(new Event('apex:session-expired'))
      return Promise.reject(refreshError)
    }
  },
)

export const unwrapList = (data) => Array.isArray(data) ? data : (data?.results || [])
export const getErrorMessage = (error) => {
  const data = error?.response?.data
  if (typeof data === 'string') return data
  if (data?.detail) return data.detail
  if (data?.error) return data.error
  if (data && typeof data === 'object') {
    const first = Object.values(data)[0]
    if (Array.isArray(first)) return first[0]
    if (typeof first === 'string') return first
  }
  return error?.message || 'Something went wrong. Please try again.'
}

export default api

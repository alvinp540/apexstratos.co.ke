import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(Boolean(localStorage.getItem('access_token')))
  const navigate = useNavigate()

  const clearSession = useCallback(() => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    setUser(null)
    setLoading(false)
  }, [])

  useEffect(() => {
    const expired = () => clearSession()
    window.addEventListener('apex:session-expired', expired)
    if (localStorage.getItem('access_token')) {
      api.get('/auth/me/').then(({ data }) => setUser(data)).catch(() => {
        if (!localStorage.getItem('refresh_token')) clearSession()
      }).finally(() => setLoading(false))
    }
    return () => window.removeEventListener('apex:session-expired', expired)
  }, [clearSession])

  const login = useCallback(async (credentials) => {
    const { data } = await api.post('/auth/login/', credentials)
    localStorage.setItem('access_token', data.access)
    localStorage.setItem('refresh_token', data.refresh)
    setUser(data.user)
    return data.user
  }, [])

  const register = useCallback((payload) => api.post('/auth/register/', payload), [])

  const logout = useCallback(async () => {
    const refresh = localStorage.getItem('refresh_token')
    try {
      if (refresh) await api.post('/auth/logout/', { refresh })
    } finally {
      clearSession()
      navigate('/')
    }
  }, [clearSession, navigate])

  const value = useMemo(() => ({ user, loading, login, register, logout, setUser }), [user, loading, login, register, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)

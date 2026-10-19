import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { getUnreadCount } from '../api/notificationAPI'
import { useAuth } from './AuthContext'
import { useWebSocket } from '../hooks/useWebSocket'

const NotificationContext = createContext(null)

export function NotificationProvider({ children }) {
  const { user } = useAuth()
  const [unreadCount, setUnreadCount] = useState(0)
  const [realtimeNotif, setRealtimeNotif] = useState(null)

  const wsUrl = user
    ? `${import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000'}/ws/notifications/`
    : null

  const handleRealtimeNotification = useCallback((msg) => {
    setRealtimeNotif(msg)
    setUnreadCount((c) => c + 1)
  }, [])
  useWebSocket(wsUrl, handleRealtimeNotification)

  const refreshCount = useCallback(async () => {
    if (!user) return
    try {
      const { data } = await getUnreadCount()
      setUnreadCount(data.unread_count)
    } catch (error) {
      console.error('Could not refresh notification count.', error)
    }
  }, [user])

  useEffect(() => { refreshCount() }, [refreshCount])

  return (
    <NotificationContext.Provider value={{ unreadCount, realtimeNotif, refreshCount }}>
      {children}
    </NotificationContext.Provider>
  )
}

export const useNotifications = () => useContext(NotificationContext)

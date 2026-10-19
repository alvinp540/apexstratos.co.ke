import { useEffect, useRef } from 'react'

export function useWebSocket(url, onMessage) {
  const wsRef = useRef(null)

  useEffect(() => {
    if (!url) return
    const token = localStorage.getItem('access_token')
    const fullUrl = token ? `${url}?token=${token}` : url
    const ws = new WebSocket(fullUrl)
    wsRef.current = ws

    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data))
      } catch (error) {
        console.error('Could not process a notification websocket message.', error)
      }
    }

    ws.onerror = () => console.error('Notification websocket connection failed.')

    return () => { ws.close() }
  }, [onMessage, url])

  return wsRef
}

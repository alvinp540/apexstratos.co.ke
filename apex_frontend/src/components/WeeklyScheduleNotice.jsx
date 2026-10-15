import { useEffect, useState } from 'react'
import api from '../api/axiosInstance'

const labels = {
  tutorials: 'Tutorials',
  sponsored_view: 'Sponsored View',
  main_contest: 'Main Contest',
}

function formatEAT(value) {
  if (!value) return 'Not scheduled'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? 'Not scheduled'
    : date.toLocaleString(undefined, {
      timeZone: 'Africa/Nairobi',
      weekday: 'long',
      hour: 'numeric',
      minute: '2-digit',
      day: 'numeric',
      month: 'short',
    })
}

export default function WeeklyScheduleNotice({ activity }) {
  const [schedule, setSchedule] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    api.get('/cohorts/weekly-schedule/')
      .then(({ data }) => { if (active) setSchedule(data) })
      .catch(() => { if (active) setError('Availability could not be confirmed. Starting remains controlled by the server.') })
    return () => { active = false }
  }, [])

  const state = schedule?.activities?.[activity]
  return <div className="info-note" role="status">
    <span>i</span>
    <p>{error || !state
      ? error || 'Checking the weekly schedule…'
      : !state.implemented
        ? `${labels[activity]} follow a Monday–Thursday EAT window, but starting is not enabled because the backend assessment and attempt feature is not implemented. ${state.available_now ? `The schedule window closes ${formatEAT(state.closes_at)}.` : `Next opening: ${formatEAT(state.opens_at)}.`}`
      : state.available_now
        ? `${labels[activity]} are available now (EAT). This window closes ${formatEAT(state.closes_at)}. Next opening: ${formatEAT(state.opens_at)}.`
        : `${labels[activity]} are currently closed. Next opening: ${formatEAT(state.opens_at)} (EAT).`}
    </p>
  </div>
}

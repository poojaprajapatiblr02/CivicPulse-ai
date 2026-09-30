import { useEffect, useState } from 'react'
import { CircleCheck, CircleDashed, CircleAlert, Server } from 'lucide-react'
import { getHealth } from '../services/api'

type ConnectionState = 'checking' | 'connected' | 'unavailable'

const states = {
  checking: { label: 'Checking backend', icon: CircleDashed },
  connected: { label: 'Backend connected', icon: CircleCheck },
  unavailable: { label: 'Backend unavailable', icon: CircleAlert },
}

export function HealthStatus() {
  const [connection, setConnection] = useState<ConnectionState>('checking')
  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal).then(
      () => { if (!controller.signal.aborted) setConnection('connected') },
      () => { if (!controller.signal.aborted) setConnection('unavailable') },
    )
    return () => controller.abort()
  }, [])

  const { label, icon: Icon } = states[connection]
  return (
    <div className="health-strip flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3"><Server size={18} aria-hidden="true" /><span>Local environment</span></div>
      <span role="status" className={`health-status status-${connection} flex items-center gap-2`}>
        <Icon size={16} aria-hidden="true" />{label}
      </span>
    </div>
  )
}
import { useEffect, useMemo, useState } from 'react'

/** Current time, ticking once a second, corrected for the gap between this device and the server. */
export function useNow(serverTime: string | undefined): number {
  const [now, setNow] = useState(() => Date.now())
  const offset = useMemo(() => (serverTime ? new Date(serverTime).getTime() - Date.now() : 0), [serverTime])

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])

  return now + offset
}

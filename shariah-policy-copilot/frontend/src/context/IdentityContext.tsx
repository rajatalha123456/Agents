import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import type { Identity } from '../api/client'
import type { Role } from '../api/types'

const STORAGE_KEY = 'spc.identity'

interface IdentityContextValue {
  identity: Identity
  setUserId: (userId: string) => void
  setRole: (role: Role) => void
}

const IdentityContext = createContext<IdentityContextValue | undefined>(undefined)

function loadStoredIdentity(): Identity {
  const fallback: Identity = { userId: 'owais', role: 'shariah_researcher' }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return fallback
    const parsed = JSON.parse(raw)
    if (typeof parsed?.userId === 'string' && typeof parsed?.role === 'string') {
      return parsed as Identity
    }
    return fallback
  } catch {
    return fallback
  }
}

function persist(identity: Identity) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(identity))
  } catch {
    // best-effort only — per-viewer convenience, not required for correctness
  }
}

export function IdentityProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<Identity>(() => loadStoredIdentity())

  const value = useMemo<IdentityContextValue>(
    () => ({
      identity,
      setUserId: (userId: string) => {
        setIdentity((prev) => {
          const next = { ...prev, userId }
          persist(next)
          return next
        })
      },
      setRole: (role: Role) => {
        setIdentity((prev) => {
          const next = { ...prev, role }
          persist(next)
          return next
        })
      },
    }),
    [identity],
  )

  return <IdentityContext.Provider value={value}>{children}</IdentityContext.Provider>
}

export function useIdentity(): IdentityContextValue {
  const ctx = useContext(IdentityContext)
  if (!ctx) throw new Error('useIdentity must be used within an IdentityProvider')
  return ctx
}

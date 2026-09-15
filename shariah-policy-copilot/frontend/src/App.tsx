import { useState } from 'react'
import { IdentityProvider } from './context/IdentityContext'
import { IdentityBar } from './components/IdentityBar'
import { DocumentsPage } from './pages/DocumentsPage'
import { AskPage } from './pages/AskPage'

type Tab = 'ask' | 'documents'

const TABS: { id: Tab; label: string }[] = [
  { id: 'ask', label: 'Ask' },
  { id: 'documents', label: 'Documents' },
]

function AppShell() {
  const [tab, setTab] = useState<Tab>('ask')

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto max-w-4xl px-4 py-3">
          <h1 className="text-lg font-semibold">Shariah Policy Copilot</h1>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Research assistant only — every answer requires human Shariah review and is never a fatwa.
          </p>
        </div>
        <IdentityBar />
        <nav className="mx-auto flex max-w-4xl gap-1 px-4">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`border-b-2 px-3 py-2 text-sm font-medium ${
                tab === t.id
                  ? 'border-emerald-600 text-emerald-700 dark:text-emerald-400'
                  : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-6">
        {tab === 'ask' ? <AskPage /> : <DocumentsPage />}
      </main>
    </div>
  )
}

function App() {
  return (
    <IdentityProvider>
      <AppShell />
    </IdentityProvider>
  )
}

export default App

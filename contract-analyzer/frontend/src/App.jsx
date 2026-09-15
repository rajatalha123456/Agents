import { useState } from 'react'
import { analyzeContract } from './api'
import ResultsView from './components/ResultsView'
import UploadForm from './components/UploadForm'

export default function App() {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [filename, setFilename] = useState('')

  async function handleAnalyze(file) {
    setIsLoading(true)
    setError('')
    setResult(null)
    try {
      const data = await analyzeContract(file)
      setResult(data)
      setFilename(file.name)
    } catch (err) {
      setError(err.message || 'Something went wrong while analyzing.')
    } finally {
      setIsLoading(false)
    }
  }

  function handleReset() {
    setResult(null)
    setError('')
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-3xl px-4 py-5">
          <h1 className="text-2xl font-semibold text-slate-900">Contract Analyzer</h1>
          <p className="mt-1 text-sm text-slate-500">
            Upload a contract and get fees, liability clauses, key dates, and conflicts extracted automatically.
          </p>
        </div>
      </header>

      <main className="px-4 py-10">
        {!result && (
          <UploadForm onAnalyze={handleAnalyze} isLoading={isLoading} />
        )}

        {error && (
          <p className="mx-auto mt-4 max-w-xl rounded-lg bg-red-50 p-3 text-center text-sm text-red-700">
            {error}
          </p>
        )}

        {result && (
          <div className="space-y-4">
            <ResultsView filename={filename} result={result} />
            <div className="mx-auto max-w-3xl">
              <button
                onClick={handleReset}
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Analyze another contract
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

import { useRef, useState } from 'react'

const ALLOWED_EXTENSIONS = ['.pdf', '.docx']

function isAllowed(file) {
  const name = file.name.toLowerCase()
  return ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext))
}

export default function UploadForm({ onAnalyze, isLoading }) {
  const [file, setFile] = useState(null)
  const [error, setError] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const inputRef = useRef(null)

  function pickFile(candidate) {
    if (!candidate) return
    if (!isAllowed(candidate)) {
      setError('Unsupported file type. Upload a .pdf or .docx file.')
      setFile(null)
      return
    }
    setError('')
    setFile(candidate)
  }

  function handleSubmit(e) {
    e.preventDefault()
    if (!file) {
      setError('Choose a .pdf or .docx file first.')
      return
    }
    onAnalyze(file)
  }

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-xl mx-auto">
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setIsDragging(false)
          pickFile(e.dataTransfer.files?.[0])
        }}
        onClick={() => inputRef.current?.click()}
        className={`cursor-pointer rounded-xl border-2 border-dashed p-10 text-center transition-colors ${
          isDragging
            ? 'border-indigo-500 bg-indigo-50'
            : 'border-slate-300 hover:border-indigo-400 hover:bg-slate-50'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx"
          className="hidden"
          onChange={(e) => pickFile(e.target.files?.[0])}
        />
        {file ? (
          <p className="text-slate-700 font-medium">{file.name}</p>
        ) : (
          <>
            <p className="text-slate-600 font-medium">
              Drop a contract here, or click to browse
            </p>
            <p className="text-sm text-slate-400 mt-1">Supports .pdf and .docx</p>
          </>
        )}
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={isLoading}
        className="mt-5 w-full rounded-lg bg-indigo-600 px-4 py-2.5 font-medium text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {isLoading ? 'Analyzing…' : 'Analyze contract'}
      </button>
    </form>
  )
}

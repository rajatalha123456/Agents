import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { UploadDocumentForm } from './UploadDocumentForm'

describe('UploadDocumentForm', () => {
  it('blocks submission and shows an error when no file is chosen', async () => {
    const onSubmit = vi.fn()
    render(<UploadDocumentForm onSubmit={onSubmit} submitting={false} />)

    await userEvent.type(screen.getByLabelText(/document name/i), 'Ta’widh Policy')
    await userEvent.type(screen.getByLabelText(/document type/i), 'policy')
    await userEvent.click(screen.getByRole('button', { name: /upload/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/choose a file/i)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('submits the file and metadata when the form is valid', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<UploadDocumentForm onSubmit={onSubmit} submitting={false} />)

    const file = new File(['content'], 'policy.txt', { type: 'text/plain' })
    await userEvent.upload(screen.getByLabelText(/^file/i), file)
    await userEvent.type(screen.getByLabelText(/document name/i), 'Ta’widh Policy')
    await userEvent.type(screen.getByLabelText(/document type/i), 'policy')
    await userEvent.click(screen.getByRole('button', { name: /upload/i }))

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        file,
        document_name: 'Ta’widh Policy',
        document_type: 'policy',
      }),
    )
  })

  it('disables the submit button while submitting', () => {
    render(<UploadDocumentForm onSubmit={vi.fn()} submitting />)
    expect(screen.getByRole('button', { name: /uploading/i })).toBeDisabled()
  })
})

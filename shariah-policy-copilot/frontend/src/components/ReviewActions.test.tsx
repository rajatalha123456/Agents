import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReviewActions } from './ReviewActions'
import { IdentityProvider } from '../context/IdentityContext'
import { makeEvidencePack } from '../test/fixtures'
import * as apiClient from '../api/client'

function setStoredIdentity(role: string) {
  localStorage.setItem('spc.identity', JSON.stringify({ userId: 'mufti_ahmad', role }))
}

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('ReviewActions', () => {
  it('renders nothing for a non-reviewer role', () => {
    setStoredIdentity('shariah_researcher')
    render(
      <IdentityProvider>
        <ReviewActions pack={makeEvidencePack()} onDecided={() => {}} />
      </IdentityProvider>,
    )
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument()
  })

  it('renders nothing once the pack is already decided', () => {
    setStoredIdentity('shariah_reviewer')
    render(
      <IdentityProvider>
        <ReviewActions pack={makeEvidencePack({ review_status: 'approved' })} onDecided={() => {}} />
      </IdentityProvider>,
    )
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument()
  })

  it('lets a reviewer approve a pending pack', async () => {
    setStoredIdentity('shariah_reviewer')
    const submitSpy = vi.spyOn(apiClient, 'submitReviewDecision').mockResolvedValue({
      id: 'pack-1',
      review_status: 'approved',
      reviewer_id: 'mufti_ahmad',
      reviewed_at: '2026-01-01',
    })
    const onDecided = vi.fn()

    render(
      <IdentityProvider>
        <ReviewActions pack={makeEvidencePack()} onDecided={onDecided} />
      </IdentityProvider>,
    )

    await userEvent.click(screen.getByRole('button', { name: /approve/i }))

    expect(submitSpy).toHaveBeenCalledWith(
      expect.objectContaining({ role: 'shariah_reviewer' }),
      'pack-1',
      true,
    )
    expect(onDecided).toHaveBeenCalledWith('approved')
  })
})

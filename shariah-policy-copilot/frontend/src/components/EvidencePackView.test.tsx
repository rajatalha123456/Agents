import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EvidencePackView } from './EvidencePackView'
import { IdentityProvider } from '../context/IdentityContext'
import { makeEvidencePack } from '../test/fixtures'

function renderPack(overrides = {}) {
  return render(
    <IdentityProvider>
      <EvidencePackView pack={makeEvidencePack(overrides)} />
    </IdentityProvider>,
  )
}

describe('EvidencePackView', () => {
  it('always shows the fixed disclaimer text', () => {
    renderPack()
    expect(
      screen.getByText(/does not constitute a fatwa or final Shariah determination/i),
    ).toBeInTheDocument()
  })

  it('flags a conflict when conflict_flagged is true', () => {
    renderPack({ conflict_flagged: true })
    expect(screen.getByText(/conflict flagged/i)).toBeInTheDocument()
  })

  it('does not show the conflict badge when nothing conflicts', () => {
    renderPack({ conflict_flagged: false })
    expect(screen.queryByText(/conflict flagged/i)).not.toBeInTheDocument()
  })

  it('renders the comparison table with the CONFLICT row', () => {
    renderPack()
    expect(screen.getByText('Late payment charge treatment')).toBeInTheDocument()
    expect(screen.getByText('CONFLICT')).toBeInTheDocument()
  })

  it('shows the review status', () => {
    renderPack({ review_status: 'human_review_required' })
    expect(screen.getByText(/human review required/i)).toBeInTheDocument()
  })
})

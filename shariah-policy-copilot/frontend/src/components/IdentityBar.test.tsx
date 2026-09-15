import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { IdentityBar } from './IdentityBar'
import { IdentityProvider } from '../context/IdentityContext'

afterEach(() => {
  localStorage.clear()
})

describe('IdentityBar', () => {
  it('updates the user id and persists it to localStorage', async () => {
    render(
      <IdentityProvider>
        <IdentityBar />
      </IdentityProvider>,
    )

    const input = screen.getByLabelText(/user id/i)
    await userEvent.clear(input)
    await userEvent.type(input, 'mufti_ahmad')

    expect(input).toHaveValue('mufti_ahmad')
    expect(JSON.parse(localStorage.getItem('spc.identity')!).userId).toBe('mufti_ahmad')
  })

  it('updates the role and persists it', async () => {
    render(
      <IdentityProvider>
        <IdentityBar />
      </IdentityProvider>,
    )

    const select = screen.getByLabelText(/role/i)
    await userEvent.selectOptions(select, 'shariah_reviewer')

    expect(select).toHaveValue('shariah_reviewer')
    expect(JSON.parse(localStorage.getItem('spc.identity')!).role).toBe('shariah_reviewer')
  })
})

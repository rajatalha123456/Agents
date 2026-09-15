import { describe, expect, it } from 'vitest'
import { approvalStatusTone, reviewStatusTone } from './status'

describe('approvalStatusTone', () => {
  it('maps known statuses to the right tone', () => {
    expect(approvalStatusTone('approved')).toBe('success')
    expect(approvalStatusTone('under_review')).toBe('warning')
    expect(approvalStatusTone('archived')).toBe('danger')
    expect(approvalStatusTone('draft')).toBe('neutral')
  })

  it('falls back to neutral for unknown statuses', () => {
    expect(approvalStatusTone('something_else')).toBe('neutral')
  })
})

describe('reviewStatusTone', () => {
  it('maps known statuses to the right tone', () => {
    expect(reviewStatusTone('approved')).toBe('success')
    expect(reviewStatusTone('rejected')).toBe('danger')
    expect(reviewStatusTone('human_review_required')).toBe('warning')
  })

  it('falls back to neutral for unknown statuses', () => {
    expect(reviewStatusTone('mystery')).toBe('neutral')
  })
})

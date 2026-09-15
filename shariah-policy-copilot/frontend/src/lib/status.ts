export function approvalStatusTone(status: string): 'success' | 'warning' | 'neutral' | 'danger' {
  switch (status) {
    case 'approved':
      return 'success'
    case 'under_review':
      return 'warning'
    case 'archived':
      return 'danger'
    default:
      return 'neutral'
  }
}

export function reviewStatusTone(status: string): 'success' | 'warning' | 'neutral' | 'danger' {
  switch (status) {
    case 'approved':
      return 'success'
    case 'rejected':
      return 'danger'
    case 'human_review_required':
      return 'warning'
    default:
      return 'neutral'
  }
}

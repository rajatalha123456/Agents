export type Role =
  | 'shariah_officer'
  | 'shariah_researcher'
  | 'shariah_reviewer'
  | 'product'
  | 'compliance'
  | 'auditor'

export const ROLES: Role[] = [
  'shariah_officer',
  'shariah_researcher',
  'shariah_reviewer',
  'product',
  'compliance',
  'auditor',
]

export type ApprovalStatus = 'approved' | 'under_review' | 'draft' | 'archived'

export const APPROVAL_STATUSES: ApprovalStatus[] = [
  'approved',
  'under_review',
  'draft',
  'archived',
]

export interface DocumentOut {
  id: string
  document_name: string
  document_type: string
  version: string
  approval_status: string
  status_emoji: string
  approval_date: string | null
  product_category: string | null
  jurisdiction: string | null
  is_current_version: number
}

export interface Citation {
  document_id: string
  document_name: string
  version: string
  section_label: string | null
  page_number: number | null
  approval_date: string | null
}

export interface EvidenceExcerpt {
  document_id: string
  document_name: string
  excerpt: string
  citation: Citation
}

export interface ComparisonRow {
  topic: string
  source_a: string
  source_a_citation: Citation
  source_b: string
  source_b_citation: Citation
  note: string | null
}

export interface EvidencePackOut {
  id: string
  question: string
  research_summary: string
  relevant_rulings: string[]
  relevant_standards: string[]
  key_evidence_excerpts: EvidenceExcerpt[]
  comparison_table: ComparisonRow[]
  open_issues: string[]
  citations: Citation[]
  conflict_flagged: boolean
  disclaimer: string
  review_status: string
  is_fallback: boolean
}

export interface QueryFilters {
  approved_only: boolean
  current_version_only: boolean
  product_category?: string
  document_type?: string
}

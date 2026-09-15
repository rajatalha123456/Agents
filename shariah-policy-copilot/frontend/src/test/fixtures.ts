import type { EvidencePackOut } from '../api/types'

export function makeEvidencePack(overrides: Partial<EvidencePackOut> = {}): EvidencePackOut {
  return {
    id: 'pack-1',
    question: 'What is the late payment charge for Murabaha?',
    research_summary: 'Two internal sources address this; they disagree on treatment.',
    relevant_rulings: ['Board Resolution — Ta’widh on Late Payment'],
    relevant_standards: [],
    key_evidence_excerpts: [
      {
        document_id: 'doc-a',
        document_name: 'Board Resolution — Ta’widh',
        excerpt: 'Late payment charges must be donated to charity, not recognised as income.',
        citation: {
          document_id: 'doc-a',
          document_name: 'Board Resolution — Ta’widh',
          version: '1.0',
          section_label: 'Clause 3',
          page_number: 1,
          approval_date: null,
        },
      },
    ],
    comparison_table: [
      {
        topic: 'Late payment charge treatment',
        source_a: 'Charity donation only',
        source_a_citation: {
          document_id: 'doc-a',
          document_name: 'Board Resolution — Ta’widh',
          version: '1.0',
          section_label: null,
          page_number: null,
          approval_date: null,
        },
        source_b: 'Recognised as fee income',
        source_b_citation: {
          document_id: 'doc-b',
          document_name: 'Murabaha Product Guideline',
          version: '1.0',
          section_label: null,
          page_number: null,
          approval_date: null,
        },
        note: 'CONFLICT',
      },
    ],
    open_issues: ['Reviewer must confirm which source takes precedence.'],
    citations: [
      {
        document_id: 'doc-a',
        document_name: 'Board Resolution — Ta’widh',
        version: '1.0',
        section_label: null,
        page_number: null,
        approval_date: null,
      },
    ],
    conflict_flagged: true,
    disclaimer:
      'This research output does not constitute a fatwa or final Shariah determination. Human Shariah review is required.',
    review_status: 'human_review_required',
    is_fallback: false,
    ...overrides,
  }
}

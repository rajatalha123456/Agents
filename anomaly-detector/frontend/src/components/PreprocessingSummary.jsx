import React from 'react';

const valueText = (value) => value === null || value === undefined ? '(unavailable)' : typeof value === 'object' ? JSON.stringify(value) : String(value);

export default function PreprocessingSummary({ report }) {
  if (!report) return null;
  const counts = report.counts || {};
  const metrics = [
    ['Rows retained', `${report.output_rows.toLocaleString()} / ${report.input_rows.toLocaleString()}`],
    ['Missing cells', ((counts.blank || 0) + (counts.missing_token || 0)).toLocaleString()],
    ['Invalid cells', (counts.invalid || 0).toLocaleString()],
    ['Not applicable', (counts.not_applicable || 0).toLocaleString()],
    ['Extra duplicate rows retained', report.duplicate_extra_rows.toLocaleString()],
    ['Known, valid cells', report.cell_quality_score == null ? 'N/A' : `${report.cell_quality_score.toFixed(2)}%`],
  ];
  return <section className="xai-score-card xai-preprocessing" aria-label="Preprocessing results">
    <div className="xai-map-head"><div><h2>Preprocessing completed</h2><span>{report.profile === 'bank_marketing' ? 'Bank Marketing data dictionary applied' : 'Generic data preparation'} · {report.scope === 'batch' ? 'Counts cover all batches; schema and model eligibility are fitted within each batch.' : 'Completed before anomaly detection.'}</span></div></div>
    <ol className="xai-pipeline-steps">{report.steps.map((step) => <li key={step}>{step}</li>)}</ol>
    <div className="xai-stat-metrics">{metrics.map(([label, value]) => <span key={label}>{label}<strong>{value}</strong></span>)}</div>
    <p className="xai-stat-note">{report.policy}</p>
    <p className="xai-stat-note">{report.quality_definition}</p>
    {(report.domain_notes || []).map((note) => <p className="xai-stat-note" key={note}>{note}</p>)}
    {!report.ratio_pairs.length && <p className="xai-stat-note">Ratio checks are disabled until meaningful column pairs are configured.</p>}
    <details>
      <summary>Column preparation and model eligibility ({report.columns.length})</summary>
      <div className="xai-preview-scroll"><table className="xai-data">
        <thead><tr><th>Column</th><th>Role</th><th>Model input</th><th>Missing / invalid</th><th>Reason</th></tr></thead>
        <tbody>{report.columns.slice(0, 100).map((column) => <tr key={column.name}>
          <td>{column.name}</td><td>{column.role}</td><td>{column.model_eligible ? 'Eligible' : 'Excluded'}</td>
          <td>{(column.counts.blank || 0) + (column.counts.missing_token || 0)} / {column.counts.invalid || 0}</td><td>{column.reason}{column.eligible_batches != null ? ` Eligible in ${column.eligible_batches} batches.` : ''}</td>
        </tr>)}</tbody>
      </table></div>
      {report.columns.length > 100 && <p>Showing the first 100 columns. Download JSON for the complete preparation report.</p>}
    </details>
    <details>
      <summary>Original vs prepared: transformation examples</summary>
      <p className="xai-stat-note">{report.evidence_scope}</p>
      {!report.examples.length ? <p>No transformations were needed.</p> : <div className="xai-preview-scroll"><table className="xai-data">
        <thead><tr><th>Source row</th><th>Column</th><th>Original</th><th>Prepared</th><th>Action</th></tr></thead>
        <tbody>{report.examples.map((example, index) => <tr key={index}><td>{example.row}</td><td>{example.column}</td><td>{valueText(example.original)}</td><td>{valueText(example.prepared)}</td><td>{example.reason.replaceAll('_', ' ')}</td></tr>)}</tbody>
      </table></div>}
    </details>
  </section>;
}

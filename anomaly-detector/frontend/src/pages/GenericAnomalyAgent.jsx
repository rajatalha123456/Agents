import React, { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api';
import StatisticalGraphs from '../components/StatisticalGraphs';
import PreprocessingSummary from '../components/PreprocessingSummary';

const SEVERITIES = ['all', 'critical', 'high', 'medium', 'low'];
const LAYERS = ['all', 'L1', 'L2', 'L3', 'L4'];
const VIEWS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'model', label: 'Model' },
  { id: 'explanations', label: 'Explanations' },
  { id: 'profile', label: 'Data profile' },
  { id: 'history', label: 'History' },
];
const SEVERITY_LABEL = { critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low' };
const SEVERITY_COLOR = { critical: '#dc2626', high: '#f97316', medium: '#f59e0b', low: '#0f766e' };

function Badge({ children, tone = 'neutral' }) {
  return <span className={`xai-badge ${tone}`}>{children}</span>;
}

function fmt(value, digits = 1) {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'number') return value.toLocaleString(undefined, { maximumFractionDigits: digits });
  return String(value);
}

function shortValue(value) {
  if (value === null || value === undefined || value === '') return '-';
  const text = String(value);
  return text.length > 72 ? `${text.slice(0, 69)}...` : text;
}

function pct(value, total) {
  if (!total) return 0;
  return Math.max(4, Math.round((value / total) * 100));
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function groupAnomalies(items) {
  const severityRank = { critical: 0, high: 1, medium: 2, low: 3 };
  const groups = new Map();
  for (const item of items) {
    const key = item.row ? `row-${item.row}` : `column-${item.column}-${item.type}`;
    if (!groups.has(key)) {
      groups.set(key, { key, row: item.row, items: [], primary: item, score: 0, severity: item.severity });
    }
    const group = groups.get(key);
    group.items.push(item);
    if (item.layer === 'L4' || item.score > group.primary.score) group.primary = item;
    group.score = Math.max(group.score, item.score);
    if (severityRank[item.severity] < severityRank[group.severity]) group.severity = item.severity;
  }
  return Array.from(groups.values()).sort((left, right) => right.score - left.score);
}

function DecisionBanner({ decision }) {
  return (
    <section className={`xai-decision ${decision.tone}`}>
      <div>
        <span>Review status</span>
        <strong>{decision.label}</strong>
        <small>{decision.rationale}</small>
      </div>
      <Badge tone={decision.tone === 'clear' ? 'low' : decision.tone}>Explainable AI</Badge>
    </section>
  );
}

function UploadDropzone({ busy, onFile, capacity }) {
  const [dragging, setDragging] = useState(false);
  function handleDrop(event) {
    event.preventDefault();
    setDragging(false);
    const picked = event.dataTransfer.files?.[0];
    if (picked && !busy) onFile(picked);
  }
  return (
    <label
      className={`xai-dropzone ${dragging ? 'dragging' : ''}`}
      onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <input aria-label="Choose dataset to analyze" type="file" accept=".csv,.json,.jsonl,.ndjson,application/json,text/csv" onChange={(event) => event.target.files?.[0] && onFile(event.target.files[0])} disabled={busy} />
      <svg className="xai-upload-icon" viewBox="0 0 48 48" fill="none" aria-hidden="true"><rect x="1" y="1" width="46" height="46" rx="14" fill="#e7f3ee"/><path d="M24 30V15m-6 6 6-6 6 6M14 29v6h20v-6" stroke="#247363" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
      <span>{busy ? 'Analyzing your dataset' : 'Drag & drop your dataset'}</span>
      <strong>{busy ? 'Building model evidence...' : 'Browse files'}</strong>
      <small>CSV, JSON or JSONL. {capacity} Large files upload in resumable chunks.</small>
    </label>
  );
}

function AnalystSummary({ items }) {
  return (
    <section className="xai-analyst-summary">
      <h2>AI analyst summary</h2>
      <div>
        {items.map((item, index) => <p key={index}>{item}</p>)}
      </div>
    </section>
  );
}

function AIReport({ report }) {
  if (!report) return null;
  const active = report.provider === 'gemini' && report.status === 'generated';
  const lines = report.text
    .split('\n')
    .map((line) => line.replace(/^\s*[-*]\s*/, '').replace(/\*\*/g, '').trim())
    .filter(Boolean);
  return (
    <section className={`xai-gemini-report ${active ? 'active' : 'fallback'}`}>
      <div className="xai-gemini-head">
        <div>
          <span>AI analyst</span>
          <strong>{active ? 'AI report generated' : 'Local report active'}</strong>
        </div>
        <Badge tone={active ? 'blue' : 'medium'}>{active ? 'AI model' : 'local model'}</Badge>
      </div>
      <div className="xai-gemini-text">
        {lines.map((line, index) => <p key={index}>{line}</p>)}
      </div>
    </section>
  );
}

function RiskDistribution({ bands }) {
  const max = Math.max(...bands.map((band) => band.count), 1);
  return (
    <div className="xai-chart-card">
      <h2>Risk distribution</h2>
      <div className="xai-risk-bars">
        {bands.map((band) => (
          <div className="xai-risk-bar" key={band.label}>
            <span>{band.label}</span>
            <div><b style={{ width: `${pct(band.count, max)}%` }} /></div>
            <strong>{band.count}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function SeverityChart({ items }) {
  const max = Math.max(...items.map((item) => item.count), 1);
  return (
    <div className="xai-chart-card">
      <h2>Anomaly severity</h2>
      <div className="xai-severity-bars">
        {items.map((item) => (
          <div className={`xai-severity-row ${item.severity}`} key={item.severity}>
            <span>{item.label}</span>
            <div><b style={{ width: `${pct(item.count, max)}%` }} /></div>
            <strong>{item.count}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function DriverBreakdown({ items }) {
  const max = Math.max(...items.map((item) => item.count), 1);
  return (
    <div className="xai-chart-card xai-driver-card">
      <h2>Top anomaly drivers</h2>
      {items.length === 0 ? <div className="xai-empty-mini">No anomaly drivers found.</div> : (
        <div className="xai-driver-list">
          {items.map((item) => (
            <div className="xai-driver-row" key={item.type}>
              <span>{item.label}</span>
              <div><b style={{ width: `${pct(item.count, max)}%` }} /></div>
              <strong>{item.count}</strong>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ModelInventory({ models, compact = false }) {
  const list = models || [];
  const active = list.filter((model) => model.active).length;
  const statistical = list.filter((model) => model.family.includes('statistical')).length;
  const ml = list.filter((model) => model.family.includes('ML')).length;
  const ai = list.filter((model) => model.family.includes('AI')).length;
  const families = [
    {
      id: 'statistical',
      name: 'Statistical baseline',
      subtitle: 'numeric outliers, data quality, category rarity',
      models: list.filter((model) => (
        model.name.includes('Data contract')
        || model.name.includes('Schema')
        || model.name.includes('Robust outlier')
        || model.name.includes('Frequency')
      )),
    },
    {
      id: 'relationship',
      name: 'Relationship models',
      subtitle: 'ratio breaks, correlation residuals, cross-column patterns',
      models: list.filter((model) => model.name.includes('Ratio') || model.name.includes('Correlation') || model.name.includes('Cross-column')),
    },
    {
      id: 'ml',
      name: 'ML ensemble',
      subtitle: 'nearest-neighbor distance across numeric features',
      models: list.filter((model) => model.family.includes('ML')),
    },
    {
      id: 'decision',
      name: 'Final decision layer',
      subtitle: 'combines all active evidence into one explainable risk score',
      models: list.filter((model) => model.family.includes('AI')),
    },
  ];

  if (compact) {
    return (
      <section className="xai-model-inventory compact">
        <div className="xai-inventory-head">
          <div>
            <h2>Models used</h2>
            <span>{list.length} detectors grouped into 4 model families</span>
          </div>
          <Badge tone="blue">{active} active on this file</Badge>
        </div>
        <div className="xai-family-grid">
          {families.map((family) => {
            const familyActive = family.models.filter((model) => model.active);
            const hits = family.models.reduce((total, model) => total + model.detections, 0);
            const maxScore = Math.max(...family.models.map((model) => model.max_score), 0);
            const avgConfidence = familyActive.length
              ? familyActive.reduce((total, model) => total + model.average_confidence, 0) / familyActive.length
              : 0;
            return (
              <div className={`xai-family-card ${familyActive.length ? 'active' : ''}`} key={family.id}>
                <div>
                  <strong>{family.name}</strong>
                  <span>{family.subtitle}</span>
                </div>
                <div className="xai-family-stats">
                  <span><b>{family.models.length}</b> detectors</span>
                  <span><b>{hits}</b> hits</span>
                  <span><b>{fmt(maxScore)}</b> max</span>
                  <span><b>{avgConfidence ? fmt(avgConfidence * 100, 0) : 0}%</b> confidence</span>
                </div>
              </div>
            );
          })}
        </div>
      </section>
    );
  }

  return (
    <section className={`xai-model-inventory ${compact ? 'compact' : ''}`}>
      <div className="xai-inventory-head">
        <div>
          <h2>Models used</h2>
          <span>{list.length} detectors: {statistical} statistical, {ml} ML, {ai} AI ensemble</span>
        </div>
        <Badge tone="blue">{active} active on this file</Badge>
      </div>
      <div className="xai-inventory-grid">
        {list.map((model) => (
          <div className={`xai-inventory-card ${model.active ? 'active' : ''}`} key={model.id}>
            <div>
              <Badge tone={model.active ? 'blue' : 'low'}>{model.layer}</Badge>
              <strong>{model.name}</strong>
              <small>{model.family}</small>
            </div>
            <p>{model.detects}</p>
            <div className="xai-model-stats">
              <span><b>{model.detections}</b> hits</span>
              <span><b>{fmt(model.max_score)}</b> max</span>
              <span><b>{model.average_confidence ? fmt(model.average_confidence * 100, 0) : 0}%</b> confidence</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function NumericDistributions({ distributions }) {
  return (
    <div className="xai-chart-card">
      <h2>Numeric distributions</h2>
      {distributions.length === 0 ? <div className="xai-empty-mini">No numeric columns found.</div> : distributions.slice(0, 4).map((dist) => {
        const max = Math.max(...dist.histogram.map((bucket) => bucket.count), 1);
        return (
          <div className="xai-histogram-block" key={dist.column}>
            <div className="xai-histogram-head">
              <strong>{dist.column}</strong>
              <span>median {fmt(dist.median)} | mean {fmt(dist.mean)}</span>
            </div>
            <div className="xai-histogram">
              {dist.histogram.map((bucket, index) => (
                <div className="xai-histogram-bin" key={`${dist.column}-${index}`}>
                  <b style={{ height: `${pct(bucket.count, max)}%` }} title={`${fmt(bucket.from)} to ${fmt(bucket.to)}: ${bucket.count}`} />
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function NumericOutliers({ plots }) {
  const [column, setColumn] = useState('');
  const plot = plots.find((item) => item.column === column) || plots[0];
  if (!plot) return null;
  const values = plot.points.map((p) => p.value);
  const batchMode = plot.scope === 'batch';
  const low = Math.min(...values, ...(batchMode ? [] : [plot.lower]));
  const high = Math.max(...values, ...(batchMode ? [] : [plot.upper]));
  const y = (value) => 250 - (value - low) / (high - low || 1) * 220;
  const lastRow = Math.max(1, ...plot.points.map((p) => p.row));
  return <section className="xai-score-card">
    <div className="xai-map-head"><div><h2>Numeric outliers</h2><span>{plot.outlier_count.toLocaleString()} outliers / {plot.total.toLocaleString()} numeric values. Showing {plot.points.length} sampled points; red = numeric outlier, blue = normal. Hover for row and value.</span></div>
      <select aria-label="Numeric column" value={plot.column} onChange={(event) => setColumn(event.target.value)}>{plots.map((item) => <option key={item.column}>{item.column}</option>)}</select></div>
    <svg viewBox="0 0 920 290" className="xai-scatter-svg" role="img" aria-label={`${plot.column} values by row with IQR bounds`}>
      {!batchMode && <rect x="70" y={y(plot.upper)} width="820" height={Math.max(1, y(plot.lower) - y(plot.upper))} fill="#dbeafe" opacity="0.5" />}
      {(batchMode ? [] : [[plot.lower, 'Lower IQR fence'], [plot.median, 'Median'], [plot.upper, 'Upper IQR fence']]).map(([value, label]) => <g key={label}><line x1="70" x2="890" y1={y(value)} y2={y(value)} stroke="#64748b" strokeDasharray="5 4"/><text x="74" y={y(value) - 5} fontSize="10">{label}: {fmt(value)}</text></g>)}
      {plot.points.map((point) => <circle key={point.row} cx={70 + point.row / lastRow * 820} cy={y(point.value)} r={point.outlier ? 4 : 2.5} fill={point.outlier ? '#dc2626' : '#2563eb'} opacity="0.75"><title>Row {point.row}: {point.value} ({point.outlier ? 'outlier' : 'normal'})</title></circle>)}
      <text x="70" y="278" fontSize="12">Row 1</text><text x="820" y="278" fontSize="12">Row {lastRow}</text>
    </svg><small>{batchMode ? 'Points are sampled across batches. Red means unusual within that row’s batch; there is no global IQR band.' : 'Shaded band: 1.5 × IQR fences. Red points use the numeric ensemble (MAD, z-score and IQR).'}</small>
  </section>;
}

function ScoreScatter({ points, selectedRow, onSelect }) {
  const visible = points || [];
  const plotW = 920;
  const plotH = 260;
  const padL = 44;
  const padR = 14;
  const padT = 12;
  const padB = 30;
  const innerW = plotW - padL - padR;
  const innerH = plotH - padT - padB;
  const lastRow = Math.max(1, ...visible.map((point) => point.row));
  const xFor = (index) => padL + ((visible[index]?.row || 1) - 1) / Math.max(1, lastRow - 1) * innerW;
  const yFor = (score) => padT + innerH - (Math.min(100, Math.max(0, score)) / 100) * innerH;
  return (
    <section className="xai-score-card">
      <div className="xai-map-head">
        <div>
          <h2>Model score scatter</h2>
          <span>Rows are plotted by file order and model risk score.</span>
        </div>
        <div className="xai-map-legend">
          {Object.entries(SEVERITY_COLOR).map(([key, color]) => <span key={key}><b style={{ background: color }} />{SEVERITY_LABEL[key]}</span>)}
        </div>
      </div>
      <svg viewBox={`0 0 ${plotW} ${plotH}`} className="xai-scatter-svg" role="img" aria-label="Risk score by row">
        {[0, 25, 50, 75, 100].map((score) => (
          <g key={score}>
            <line x1={padL} x2={plotW - padR} y1={yFor(score)} y2={yFor(score)} className="xai-gridline" />
            <text x={padL - 8} y={yFor(score) + 4} className="xai-axis-label" textAnchor="end">{score}</text>
          </g>
        ))}
        {[40, 65, 85].map((score) => (
          <g key={score}>
            <line x1={padL} x2={plotW - padR} y1={yFor(score)} y2={yFor(score)} className="xai-threshold-line" />
            <text x={plotW - padR} y={yFor(score) - 4} className="xai-threshold-label" textAnchor="end">score {score}</text>
          </g>
        ))}
        <line x1={padL} x2={padL} y1={padT} y2={plotH - padB} className="xai-axis" />
        <line x1={padL} x2={plotW - padR} y1={plotH - padB} y2={plotH - padB} className="xai-axis" />
        {visible.map((point, index) => {
          const color = SEVERITY_COLOR[point.severity] || SEVERITY_COLOR.low;
          const selected = point.row === selectedRow;
          return (
            <g key={point.row}>
              <circle cx={xFor(index)} cy={yFor(point.score)} r={12} fill="transparent" className="xai-scatter-hit" onClick={() => onSelect(point.row)}>
                <title>{`Row ${point.row}: score ${fmt(point.score)} | ${point.dominant_layer}`}</title>
              </circle>
              <circle cx={xFor(index)} cy={yFor(point.score)} r={selected ? 7 : 4.5} fill={color} className={selected ? 'xai-scatter-dot selected' : 'xai-scatter-dot'} pointerEvents="none" />
            </g>
          );
        })}
      </svg>
    </section>
  );
}

function RiskHeatmap({ points, selectedRow, onSelect }) {
  const visible = points || [];
  return (
    <section className="xai-heat-card">
      <div className="xai-map-head">
        <div>
          <h2>Row risk heatmap</h2>
          <span>Click a row cell to open its strongest anomaly.</span>
        </div>
      </div>
      <div className="xai-heatmap">
        {visible.map((point) => {
          const tone = point.score >= 85 ? 'critical' : point.score >= 65 ? 'high' : point.score >= 40 ? 'medium' : 'low';
          return (
            <button
              className={`xai-heat-cell ${tone} ${selectedRow === point.row ? 'selected' : ''}`}
              key={point.row}
              title={`Row ${point.row}: score ${fmt(point.score)}`}
              onClick={() => onSelect(point.row)}
            >
              {point.row}
            </button>
          );
        })}
      </div>
    </section>
  );
}

function RowSnapshot({ anomaly, analysis }) {
  if (!anomaly?.row) return null;
  const snapshot = analysis.row_snapshots?.[String(anomaly.row)];
  const values = anomaly.row_values || snapshot?.values || {};
  const entries = Object.entries(values).slice(0, 12);
  if (entries.length === 0) return null;
  return (
    <>
      <h3>Row snapshot</h3>
      <div className="xai-row-snapshot">
        {entries.map(([key, value]) => (
          <div className="xai-snapshot-field" key={key}>
            <span>{key}</span>
            <strong>{shortValue(value)}</strong>
          </div>
        ))}
      </div>
      {anomaly.prepared_row_values && <details><summary>Prepared model values</summary><div className="xai-row-snapshot">
        {Object.entries(anomaly.prepared_row_values).slice(0, 12).map(([key, value]) => <div className="xai-snapshot-field" key={key}><span>{key}</span><strong>{shortValue(value)}</strong></div>)}
      </div></details>}
      {snapshot?.layer_scores && Object.keys(snapshot.layer_scores).length > 0 && (
        <div className="xai-layer-score-strip">
          {Object.entries(snapshot.layer_scores).map(([key, value]) => <span key={key}>{key}<b>{fmt(value)}</b></span>)}
        </div>
      )}
    </>
  );
}

function DataPreview({ analysis }) {
  const [showPrepared, setShowPrepared] = useState(false);
  const prepared = showPrepared && Boolean(analysis.prepared_preview_rows);
  const columns = analysis.columns.slice(0, 8).map((column) => column.name);
  return (
    <div className="xai-preview-card">
      <h2>Data preview: {prepared ? 'prepared' : 'original values'}</h2>
      {analysis.prepared_preview_rows && <div className="xai-stat-buttons"><button className={`xai-filter-pill ${!prepared ? 'active' : ''}`} onClick={() => setShowPrepared(false)}>Original</button><button className={`xai-filter-pill ${prepared ? 'active' : ''}`} onClick={() => setShowPrepared(true)}>Prepared</button></div>}
      <div className="xai-preview-scroll">
        <table className="xai-data xai-preview-table">
          <thead>
            <tr>
              <th>Row</th>
              {columns.map((column) => <th key={column}>{column}</th>)}
            </tr>
          </thead>
          <tbody>
            {(prepared ? analysis.prepared_preview_rows : analysis.preview_rows).map((row) => (
              <tr key={row.row}>
                <td className="xai-tabular">{row.row}</td>
                {columns.map((column) => <td key={column}>{shortValue(row.values[column])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function selectedExplanation(anomaly) {
  if (!anomaly) return null;
  return anomaly.explanation || {
    plain_language: anomaly.message,
    feature_contributions: [],
    recommended_action: 'Review the source record and decide whether this is expected.',
  };
}

export default function GenericAnomalyAgent() {
  const [file, setFile] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [history, setHistory] = useState([]);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(null);
  const [capacity, setCapacity] = useState('Checking server capacity…');
  const uploadController = useRef(null);
  const [explainBusy, setExplainBusy] = useState(false);
  const [chatBusy, setChatBusy] = useState(false);
  const [error, setError] = useState('');
  const [severity, setSeverity] = useState('all');
  const [layer, setLayer] = useState('all');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState(null);
  const [view, setView] = useState('dashboard');
  const [chatText, setChatText] = useState('');
  const [chatMessages, setChatMessages] = useState([]);

  useEffect(() => {
    api.analyses().then(setHistory).catch(() => setHistory([]));
    api.uploadConfig().then((config) => setCapacity(config.max_file_bytes
      ? `Server limit: ${(config.max_file_bytes / 1024 ** 3).toLocaleString()} GiB per file.`
      : 'No configured file-size ceiling; available disk space still applies.')).catch(() => setCapacity('Server capacity unavailable.'));
    const pending = api.pendingUpload();
    if (pending) api.uploadStatus(pending.id).then(setProgress).catch(() => {});
    return () => uploadController.current?.abort();
  }, []);

  const selected = useMemo(
    () => (analysis?.anomalies || []).find((item) => item.id === selectedId) || analysis?.anomalies?.[0] || null,
    [analysis, selectedId],
  );
  const explanation = selectedExplanation(selected);
  const selectedRow = selected?.row || null;

  useEffect(() => {
    setChatText('');
    setChatMessages([]);
  }, [selectedId]);

  const anomalies = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (analysis?.anomalies || []).filter((item) => {
      const severityMatch = severity === 'all' || item.severity === severity;
      const layerMatch = layer === 'all' || item.layer === layer;
      const queryMatch = !q || [item.layer, item.column, item.type, item.model, item.method, item.message, item.value]
        .some((value) => String(value || '').toLowerCase().includes(q));
      return severityMatch && layerMatch && queryMatch;
    });
  }, [analysis, layer, query, severity]);

  const anomalyGroups = useMemo(() => groupAnomalies(anomalies), [anomalies]);

  async function runAnalysis(nextFile = file) {
    if (!nextFile || busy) return;
    setBusy(true);
    setError('');
    uploadController.current = new AbortController();
    try {
      const result = await api.analyzeFile(nextFile, setProgress, uploadController.current.signal);
      setAnalysis(result);
      setProgress(null);
      setSeverity('all');
      setLayer('all');
      setQuery('');
      setView('dashboard');
      setSelectedId(result.anomalies?.[0]?.id || null);
      api.analyses().then(setHistory).catch(() => {});
    } catch (err) {
      setError(err.name === 'AbortError' ? 'Paused. Select the same original file to resume its upload, or reconnect to the running analysis.' : err.message || 'Could not analyze this file.');
    } finally {
      setBusy(false);
    }
  }

  function loadFile(picked) {
    if (busy) return;
    setFile(picked);
    setAnalysis(null);
    runAnalysis(picked);
  }

  async function reconnectUpload() {
    if (!progress || busy) return;
    setBusy(true);
    setError('');
    uploadController.current = new AbortController();
    try {
      const result = await api.waitForUpload(progress.id, setProgress, uploadController.current.signal);
      setAnalysis(result);
      setSelectedId(result.anomalies?.[0]?.id || null);
      setProgress(null);
      setView('dashboard');
      api.analyses().then(setHistory).catch(() => {});
    } catch (err) {
      setError(err.name === 'AbortError' ? 'Disconnected from progress; the worker continues.' : err.message);
    } finally { setBusy(false); }
  }

  async function cancelUpload() {
    if (!progress) return;
    uploadController.current?.abort();
    try { await api.cancelUpload(progress.id); setProgress(null); }
    catch (err) { setError(err.message); }
  }

  function chooseFile(event) {
    const picked = event.target.files?.[0];
    event.target.value = '';
    if (picked) loadFile(picked);
  }

  async function openAnalysis(id) {
    setBusy(true);
    setError('');
    try {
      const result = await api.analysis(id);
      setAnalysis(result);
      setSelectedId(result.anomalies?.[0]?.id || null);
      setView('dashboard');
      setFile(null);
    } catch (err) {
      setError(err.message || 'Could not open this analysis.');
    } finally {
      setBusy(false);
    }
  }

  async function explainSelectedWithAi() {
    if (!analysis?.analysis_id || !selected?.id) return;
    setExplainBusy(true);
    try {
      const result = await api.explainAnomaly(analysis.analysis_id, selected.id);
      setAnalysis((current) => ({
        ...current,
        anomalies: current.anomalies.map((item) => (item.id === selected.id ? { ...item, ai_explanation: result } : item)),
      }));
    } catch (err) {
      setError(err.message || 'Could not generate AI explanation.');
    } finally {
      setExplainBusy(false);
    }
  }

  async function sendAnomalyChat(event) {
    event.preventDefault();
    const message = chatText.trim();
    if (!message || !analysis?.analysis_id || !selected?.id) return;
    const nextMessages = [...chatMessages, { role: 'user', content: message }];
    setChatMessages(nextMessages);
    setChatText('');
    setChatBusy(true);
    try {
      const result = await api.chatAboutAnomaly(analysis.analysis_id, selected.id, {
        message,
        history: chatMessages,
      });
      setChatMessages([...nextMessages, { role: 'assistant', content: result.text, model: result.status === 'generated' ? 'AI model' : 'local model' }]);
    } catch (err) {
      setError(err.message || 'Could not discuss this anomaly.');
    } finally {
      setChatBusy(false);
    }
  }

  function downloadJson() {
    if (!analysis) return;
    const blob = new Blob([JSON.stringify(analysis, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${analysis.filename || 'anomaly-analysis'}-report.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function downloadReport() {
    if (!analysis) return;
    const topRows = (analysis.anomalies || []).slice(0, 20).map((item) => `
      <tr><td>${escapeHtml(item.severity)}</td><td>${escapeHtml(item.score)}</td><td>${escapeHtml(item.row || '-')}</td><td>${escapeHtml(item.layer)}</td><td>${escapeHtml(item.model)}</td><td>${escapeHtml(item.message)}</td></tr>
    `).join('');
    const html = `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(analysis.filename)} report</title><style>body{font-family:Inter,Arial,sans-serif;background:#f6f8fb;color:#132238;padding:34px}.wrap{max-width:1100px;margin:auto;background:white;border:1px solid #dde6f0;border-radius:8px;padding:28px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.metric{border:1px solid #e2e8f0;border-radius:8px;padding:14px}.metric span{display:block;color:#64748b;font-size:11px;text-transform:uppercase;font-weight:800}.metric strong{font-size:28px}table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid #e2e8f0;padding:9px;text-align:left;vertical-align:top}th{background:#f8fafc}</style></head><body><main class="wrap"><h1>${escapeHtml(analysis.filename)}</h1><p>${escapeHtml(analysis.decision.label)}: ${escapeHtml(analysis.decision.rationale)}</p><section class="grid"><div class="metric"><span>Rows</span><strong>${analysis.row_count}</strong></div><div class="metric"><span>Detector findings</span><strong>${analysis.summary.total_anomalies}</strong></div><div class="metric"><span>Max score</span><strong>${analysis.summary.max_risk_score}</strong></div><div class="metric"><span>${analysis.preprocessing ? "Valid cells (%)" : "Legacy data score"}</span><strong>${escapeHtml(fmt(analysis.summary.data_quality_score))}</strong></div></section><p>${escapeHtml(analysis.preprocessing?.quality_definition || "")}</p><p>${escapeHtml(analysis.processing?.notice || "")}</p><h2>Top anomalies</h2><table><thead><tr><th>Severity</th><th>Score</th><th>Row</th><th>Layer</th><th>Model</th><th>Reason</th></tr></thead><tbody>${topRows}</tbody></table></main></body></html>`;
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${analysis.filename || 'anomaly-analysis'}-executive-report.html`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="xai-shell">
      <a className="xai-skip-link" href="#main-content">Skip to workspace</a>
      <aside className="xai-sidebar">
        <div className="xai-brand">
          <strong className="xai-product-name">Anomaly<br />Detector<span className="xai-brand-dot">.</span></strong>
          <span>ANALYST WORKSPACE</span>
        </div>
        {VIEWS.map((item) => (
          <button className={`xai-nav-item ${view === item.id ? 'active' : ''}`} key={item.id} aria-current={view === item.id ? 'page' : undefined} onClick={() => setView(item.id)}>
            {item.label}
          </button>
        ))}
        <div className="xai-sidebar-note">Generic L1-L4 anomaly detection. Review data quality and unusual patterns.</div>
        <div className="xai-history-mini">
          <strong>Recent analyses</strong>
          {history.slice(0, 4).map((item) => (
            <button key={item.analysis_id} onClick={() => openAnalysis(item.analysis_id)}>
              <span>{item.filename}</span>
              <small>{item.total_anomalies} anomalies | score {fmt(item.max_risk_score)}</small>
            </button>
          ))}
        </div>
      </aside>

      <main className="xai-main" id="main-content">
        <header className="xai-header">
          <div>
            <div className="xai-eyebrow">Workspace / {VIEWS.find(item => item.id === view)?.label}</div>
            <h1>{view === "dashboard" ? "Analysis overview" : VIEWS.find(item => item.id === view)?.label}</h1>
            <p className="xai-header-subtitle">Explore your data. Understand the signals. Review with confidence.</p>
          </div>
          {analysis && <div className="xai-header-actions">
            <label className="xai-upload-button">
              {busy ? 'Analyzing...' : 'Analyze new file'}
              <input aria-label="Choose dataset to analyze" type="file" accept=".csv,.json,.jsonl,.ndjson,application/json,text/csv" onChange={chooseFile} disabled={busy} />
            </label>
          </div>}
        </header>

        {error && <div className="xai-callout red">{error}</div>}
        {progress && <section className="xai-score-card" aria-live="polite">
          <h2>{progress.filename}: {progress.state}</h2>
          <p>{(progress.received / 1024 ** 3).toFixed(2)} / {(progress.size / 1024 ** 3).toFixed(2)} GiB uploaded
            {' · '}{progress.rows_done.toLocaleString()} rows processed in {progress.batches_done.toLocaleString()} batches.</p>
          <progress aria-label="Upload progress" max={progress.size} value={progress.received} style={{ width: '100%' }} />
          {progress.state === 'queued' && <p>Waiting for the background worker. You can close this tab and reconnect later.</p>}
          {progress.state === 'uploading' && !busy && <p>Select the same original file to resume from the last saved chunk.</p>}
          {progress.error && <p>{progress.error}</p>}
          {busy && <button className="xai-ghost-btn" onClick={() => uploadController.current?.abort()}>Pause / disconnect</button>}
          {!busy && ['queued', 'processing', 'completed'].includes(progress.state) && <button className="xai-ghost-btn" onClick={reconnectUpload}>Reconnect to analysis</button>}
          {progress.state !== 'completed' && <button className="xai-ghost-btn" onClick={cancelUpload}>Cancel and remove upload</button>}
        </section>}

        {!analysis && !error && (
          <section className="xai-welcome">
            <div className="xai-welcome-story">
              <span className="xai-welcome-kicker"><i /> A clearer view of your data</span>
              <h2>Find the unusual.<br /><em>Understand why.</em></h2>
              <p>From raw records to meaningful evidence. Explore patterns, uncover outliers, and bring every finding into focus.</p>
              <div className="xai-signal-art" aria-hidden="true">
                <div className="xai-art-caption"><span>PATTERNS INTO PERSPECTIVE</span><span>Illustration</span></div>
                <svg viewBox="0 0 480 160" fill="none">
                  {[35, 75, 115, 155].map(y => <path key={y} d={`M0 ${y} H480`} stroke="#ffffff12" />)}
                  <path d="M0 112 L24 106 L48 118 L72 99 L96 105 L120 92 L144 108 L168 102 L192 115 L216 96 L240 104 L264 35 L288 103 L312 96 L336 108 L360 89 L384 97 L408 83 L432 102 L456 90 L480 98" stroke="#80ddbd" strokeWidth="2.5" strokeLinejoin="round" />
                  <circle cx="264" cy="35" r="17" fill="#eabf6d22" /><circle cx="264" cy="35" r="6" fill="#edc681" />
                  <path d="M264 57 V150" stroke="#edc68166" strokeDasharray="4 5" />
                  <text x="289" y="32" fill="#edc681" fontSize="11">A signal worth exploring</text>
                </svg>
                <div className="xai-art-legend"><span><i /> Typical pattern</span><span><i /> Unusual observation</span></div>
              </div>
            </div>
            <div className="xai-welcome-upload">
              <span className="xai-eyebrow">Start an analysis</span>
              <h3>Your next insight starts here.</h3>
              <p>Choose a dataset. We will prepare the data and surface findings for your review.</p>
              <UploadDropzone busy={busy} onFile={loadFile} capacity={capacity} />
              <div className="xai-file-types"><span>CSV</span><span>JSON</span><span>JSONL</span><small>One dataset at a time</small></div>
            </div>
            <div className="xai-welcome-steps">
              {[['01', 'Prepare', 'Check completeness, normalize values, preserve originals.'], ['02', 'Discover', 'Explore unusual values and relationships through graphs.'], ['03', 'Review', 'Inspect the evidence and decide what needs attention.']].map(([number, title, description]) => <div key={number}><b>{number}</b><div><h3>{title}</h3><p>{description}</p></div></div>)}
            </div>
          </section>
        )}

        {analysis && (
          <>
            <DecisionBanner decision={analysis.decision} />
            {analysis.processing && <div className="xai-callout">{analysis.processing.notice} Column profiles and overview histograms describe the first batch. Statistical exploration uses rows sampled across the full file.</div>}
            <section className="xai-command">
              <div>
                <span>Current file</span>
                <strong>{analysis.filename}</strong>
                <small>{analysis.file_type.toUpperCase()} | {analysis.row_count} rows | {analysis.column_count} columns</small>
              </div>
              <div className="xai-command-actions">
                <button className="xai-ghost-btn" onClick={downloadReport}>Download report</button>
                <button className="xai-ghost-btn" onClick={downloadJson}>Download JSON</button>
                {analysis.processing && <a className="xai-ghost-btn" href={`/v1/anomaly/uploads/${analysis.analysis_id}/findings`}>Download all findings (JSONL)</a>}
                <button className="xai-ghost-btn" onClick={() => runAnalysis()} disabled={busy}>Run model again</button>
              </div>
            </section>

            {view === 'dashboard' && (
              <>
                <section className="xai-metrics">
                  <div className="xai-risk-card"><span>Max risk score</span><strong>{fmt(analysis.summary.max_risk_score)}</strong><small>Capped 0-100 index | {analysis.summary.critical} critical | {analysis.summary.high} high</small></div>
                  <div><span>Detector findings</span><strong>{fmt(analysis.summary.total_anomalies, 0)}</strong><small>Multiple findings can refer to one record</small></div>
                  <div><span>{analysis.preprocessing ? 'Valid cells (%)' : 'Legacy data score'}</span><strong>{fmt(analysis.summary.data_quality_score)}</strong></div>
                  <div><span>Top rows shown</span><strong>{analysis.row_findings.length}</strong></div>
                </section>
                <div className="xai-section-heading"><div><span className="xai-eyebrow">Investigation</span><h2>Signals worth a closer look</h2></div><button className="xai-upload-button" onClick={() => setView('explanations')}>Review findings ?</button></div>
                <AnalystSummary items={analysis.analyst_summary} />
                <details className="xai-disclosure"><summary>Data preparation & quality<span>Inspect transformations and column roles</span></summary><PreprocessingSummary report={analysis.preprocessing} /></details>
                <details className="xai-disclosure"><summary>Detection methods & AI summary<span>Explore how these findings were generated</span></summary><ModelInventory models={analysis.model_inventory || []} compact /><AIReport report={analysis.ai_report} /></details>
                <section className="xai-layer-grid">
                  {analysis.layers.map((item) => (
                    <button className={`xai-layer-card ${layer === item.id ? 'selected' : ''}`} key={item.id} onClick={() => setLayer(layer === item.id ? 'all' : item.id)}>
                      <div><b>{item.id}</b><strong>{item.name}</strong></div>
                      <span>{item.model}</span>
                      <small>{item.description}</small>
                      <em>{item.count}</em>
                    </button>
                  ))}
                </section>
                <section className="xai-analytics-grid">
                  <RiskDistribution bands={analysis.risk_distribution} />
                  <SeverityChart items={analysis.severity_distribution} />
                  <NumericDistributions distributions={analysis.distributions} />
                  <DriverBreakdown items={analysis.driver_breakdown || []} />
                </section>
                <NumericOutliers plots={analysis.numeric_plots || []} />
                <StatisticalGraphs data={analysis.statistical_graphs} />
                <ScoreScatter points={analysis.score_points || []} selectedRow={selectedRow} onSelect={(row) => {
                  const match = (analysis.anomalies || []).find((item) => item.row === row);
                  if (match) { setSelectedId(match.id); setView('explanations'); }
                }} />
                <RiskHeatmap points={analysis.score_points || []} selectedRow={selectedRow} onSelect={(row) => {
                  const match = (analysis.anomalies || []).find((item) => item.row === row);
                  if (match) { setSelectedId(match.id); setView('explanations'); }
                }} />
              </>
            )}

            {view === 'model' && (
              <>
                <section className="xai-model-card expanded">
                  <div>
                    <span>Model card</span>
                    <strong>{analysis.model_card.name}</strong>
                    <small>{analysis.model_card.model_count} total detectors | {analysis.model_card.active_model_count} active on this file | {analysis.model_card.training}</small>
                  </div>
                  <div className="xai-model-features">{analysis.model_card.features.map((feature) => <Badge key={feature}>{feature}</Badge>)}</div>
                </section>
                <ModelInventory models={analysis.model_inventory || []} />
                <section className="xai-model-notes">
                  <div><strong>Explainability</strong><span>{analysis.model_card.explainability}</span></div>
                  <div><strong>Decision policy</strong><span>{analysis.model_card.decision_policy}</span></div>
                  <div><strong>Limitations</strong><span>{analysis.model_card.limitations}</span></div>
                </section>
                <section className="xai-threshold-panel">
                  <h2>Detector thresholds</h2>
                  {(analysis.model_card.thresholds || []).map((item, index) => (
                    <div className="xai-threshold-row" key={item}><b>L{index + 1}</b><span>{item}</span></div>
                  ))}
                </section>
              </>
            )}

            {view === 'explanations' && (
              <section className="xai-workspace">
                <div className="xai-table-panel">
                  <div className="xai-results-toolbar">
                    <h2>Anomaly queue</h2>
                    <div className="xai-filters compact">
                      {LAYERS.map((item) => <button key={item} className={`xai-filter-pill ${layer === item ? 'active' : ''}`} onClick={() => setLayer(item)}>{item}</button>)}
                      {SEVERITIES.map((item) => <button key={item} className={`xai-filter-pill ${severity === item ? 'active' : ''}`} onClick={() => setSeverity(item)}>{item}</button>)}
                      <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search anomalies" />
                    </div>
                  </div>
                  <table className="xai-data xai-anomaly-table">
                    <thead><tr><th>Primary</th><th>Severity</th><th>Score</th><th>Row</th><th>Evidence</th><th>Primary reason</th></tr></thead>
                    <tbody>
                      {anomalyGroups.length === 0 ? <tr><td colSpan={6} className="xai-empty-state">No anomalies match this filter.</td></tr> : anomalyGroups.map((group) => (
                        <tr key={group.key} className={group.items.some((item) => item.id === selected?.id) ? 'selected-row' : ''} onClick={() => setSelectedId(group.primary.id)}>
                          <td><Badge tone="blue">{group.primary.layer}</Badge></td>
                          <td><Badge tone={group.severity}>{group.severity}</Badge></td>
                          <td className="xai-tabular strong-score">{fmt(group.score)}</td>
                          <td className="xai-tabular">{group.row || '-'}</td>
                          <td><div className="xai-evidence-stack">{group.items.map((item) => <span key={item.id}>{item.layer}: {item.type.replace(/_/g, ' ')}</span>)}</div></td>
                          <td><strong className="xai-queue-reason">{group.primary.model}</strong><span>{group.primary.message}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <aside className="xai-explain-panel">
                  <h2>Explainability</h2>
                  {selected ? (
                    <>
                      <div className="xai-explain-head"><Badge tone="blue">{selected.layer}</Badge><Badge tone={selected.severity}>{selected.severity}</Badge><strong>{fmt(selected.score)}</strong></div>
                      <p>{explanation.plain_language}</p>
                      <div className="xai-explain-meta">
                        <span>Method</span><strong>{selected.method}</strong>
                        <span>Threshold</span><strong>{selected.threshold}</strong>
                        <span>Heuristic confidence</span><strong>{fmt(selected.confidence, 2)}</strong>
                        <span>Model</span><strong>{selected.model}</strong>
                        <span>Value</span><strong>{shortValue(selected.value)}</strong>
                      </div>
                      <h3>Feature contributions</h3>
                      <div className="xai-contrib-list">
                        {(explanation.feature_contributions || []).map((item, index) => (
                          <div className="xai-contrib-item" key={`${item.feature}-${index}`}>
                            <div><strong>{item.feature}</strong><span>{item.reason}</span></div>
                            <b>{fmt(item.impact)}</b>
                            <i style={{ width: `${Math.min(100, Math.max(4, Number(item.impact) || 0))}%` }} />
                          </div>
                        ))}
                      </div>
                      <RowSnapshot anomaly={selected} analysis={analysis} />
                      <h3>AI anomaly analyst</h3>
                      {selected.ai_explanation ? (
                        <div className={`xai-selected-ai-note ${selected.ai_explanation.status === 'generated' ? 'active' : 'fallback'}`}>
                          <Badge tone={selected.ai_explanation.status === 'generated' ? 'blue' : 'medium'}>{selected.ai_explanation.status === 'generated' ? 'AI model' : 'local model'}</Badge>
                          <p>{selected.ai_explanation.text}</p>
                        </div>
                      ) : (
                        <button className="xai-ai-explain-btn" onClick={explainSelectedWithAi} disabled={explainBusy}>{explainBusy ? 'Generating...' : 'Explain selected anomaly with AI'}</button>
                      )}
                      <h3>Discuss this anomaly</h3>
                      <div className="xai-chat-box">
                        <div className="xai-chat-messages">
                          {chatMessages.length === 0 ? (
                            <p className="xai-chat-empty">Ask why it was flagged, what the score means, or what to verify next.</p>
                          ) : chatMessages.map((message, index) => (
                            <div className={`xai-chat-message ${message.role}`} key={`${message.role}-${index}`}>
                              <span>{message.role === 'user' ? 'You' : message.model || 'AI analyst'}</span>
                              <p>{message.content}</p>
                            </div>
                          ))}
                          {chatBusy && <div className="xai-chat-message assistant"><span>AI analyst</span><p>Thinking through the model evidence...</p></div>}
                        </div>
                        <form className="xai-chat-form" onSubmit={sendAnomalyChat}>
                          <input
                            value={chatText}
                            onChange={(event) => setChatText(event.target.value)}
                            placeholder="Ask about this anomaly..."
                            disabled={chatBusy}
                          />
                          <button type="submit" disabled={chatBusy || !chatText.trim()}>Send</button>
                        </form>
                      </div>
                      <h3>Recommended action</h3>
                      <p>{explanation.recommended_action}</p>
                    </>
                  ) : <p>No anomaly selected.</p>}
                </aside>
              </section>
            )}

            {view === 'profile' && (
              <>
                <section className="xai-bottom-grid">
                  <div className="xai-top-row-panel">
                    <h2>Top risky rows</h2>
                    {(analysis.row_findings.length ? analysis.row_findings : []).slice(0, 12).map((row) => (
                      <div className="xai-risky-row" key={row.row}><strong>Row {row.row}</strong><span>{row.reasons.join(', ')}</span><b>{fmt(row.score)}</b></div>
                    ))}
                    {analysis.row_findings.length === 0 && <div className="xai-empty-mini">No row-level risks crossed the model threshold.</div>}
                  </div>
                  <div className="xai-profile-panel">
                    <h2>Column profile</h2>
                    <div className="xai-profile-list compact-profile">
                      {analysis.columns.map((column) => (
                        <div className="xai-profile-item" key={column.name}>
                          <div><strong>{column.name}</strong><span>{column.type}</span></div>
                          <small>{column.missing} missing | {column.unique} unique | {(column.missing_rate * 100).toFixed(1)}% blank</small>
                        </div>
                      ))}
                    </div>
                  </div>
                </section>
                <DataPreview analysis={analysis} />
              </>
            )}

            {view === 'history' && (
              <section className="xai-history-panel">
                <h2>Analysis history</h2>
                {history.length === 0 ? <div className="xai-empty-mini">No saved analyses yet.</div> : history.map((item) => (
                  <button className="xai-history-row" key={item.analysis_id} onClick={() => openAnalysis(item.analysis_id)}>
                    <div><strong>{item.filename}</strong><span>{item.file_type?.toUpperCase()} | {item.row_count} rows | {item.column_count} columns | {item.created_at || 'saved'}</span></div>
                    <div><b>{item.total_anomalies}</b><small>anomalies</small></div>
                    <Badge tone={item.decision?.tone || 'blue'}>{item.decision?.label || 'saved'}</Badge>
                  </button>
                ))}
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}

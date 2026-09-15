import React, { useState } from 'react';

const BLUE = '#2563eb';
const RED = '#dc2626';
const number = (value) => Number.isFinite(value)
  ? new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 2 }).format(value)
  : 'N/A';
const precise = (value) => Number.isFinite(value) ? value.toLocaleString('en', { maximumSignificantDigits: 8 }) : 'N/A';

function scale(low, high, start, end) {
  const padding = low === high ? Math.max(1, Math.abs(low) * .05) : (high - low) * .05;
  const minimum = low - padding;
  const maximum = high + padding;
  return { at: (value) => start + (value - minimum) / (maximum - minimum) * (end - start),
    ticks: Array.from({ length: 5 }, (_, index) => minimum + (maximum - minimum) * index / 4) };
}

function BoxPlot({ column }) {
  const x = scale(column.min, column.max, 70, 870);
  return <>
    <svg viewBox="0 0 920 240" className="xai-stat-svg" role="img" aria-label={`${column.column} box plot: median ${precise(column.median)}, ${column.outlier_count} IQR outliers`}>
      {x.ticks.map((tick, index) => <g key={index}><line x1={x.at(tick)} x2={x.at(tick)} y1="30" y2="170" className="xai-gridline"/><text x={x.at(tick)} y="195" textAnchor="middle">{number(tick)}</text></g>)}
      <line x1={x.at(column.whisker_low)} x2={x.at(column.whisker_high)} y1="100" y2="100" stroke={BLUE} strokeWidth="2" />
      {[column.whisker_low, column.whisker_high].map((value, index) => <line key={index} x1={x.at(value)} x2={x.at(value)} y1="78" y2="122" stroke={BLUE} strokeWidth="2" />)}
      <rect x={x.at(column.q1)} y="65" width={Math.max(1, x.at(column.q3) - x.at(column.q1))} height="70" fill="#dbeafe" stroke={BLUE} strokeWidth="2"><title>Middle 50%: {precise(column.q1)} to {precise(column.q3)}</title></rect>
      <line x1={x.at(column.median)} x2={x.at(column.median)} y1="65" y2="135" stroke="#0f172a" strokeWidth="3"><title>Median: {precise(column.median)}</title></line>
      {column.outlier_values.map((value, index) => <circle key={index} cx={x.at(value)} cy={100 + (index % 5 - 2) * 5} r="4" fill={RED} opacity=".75"><title>IQR outlier: {precise(value)}</title></circle>)}
      <text x="470" y="226" textAnchor="middle">{column.column}</text>
    </svg>
    <div className="xai-stat-metrics">
      {[["Q1", column.q1], ["Median", column.median], ["Q3", column.q3], ["Lower fence", column.lower], ["Upper fence", column.upper]].map(([label, value]) => <span key={label}>{label}<strong title={precise(value)}>{number(value)}</strong></span>)}
    </div>
    <p className="xai-stat-note">The box contains the middle 50% of values. Whiskers stop at the furthest observed values within 1.5 × IQR fences. Red dots lie outside those fences; up to 200 are shown.</p>
  </>;
}

function Histogram({ column }) {
  const maximum = Math.max(1, ...column.histogram.map((bin) => bin.normal + bin.outliers));
  const y = (count) => 250 - count / maximum * 210;
  const width = 800 / column.histogram.length;
  return <>
    <svg viewBox="0 0 920 310" className="xai-stat-svg" role="img" aria-label={`${column.column} frequency histogram with IQR outliers`}>
      {[0, .25, .5, .75, 1].map((fraction) => <g key={fraction}><line x1="70" x2="870" y1={y(maximum * fraction)} y2={y(maximum * fraction)} className="xai-gridline"/><text x="60" y={y(maximum * fraction) + 4} textAnchor="end">{number(maximum * fraction)}</text></g>)}
      {column.histogram.map((bin, index) => <g key={index}>
        <title>{precise(bin.from)} to {precise(bin.to)}: {bin.normal} within fences, {bin.outliers} IQR outliers</title>
        <rect x={70 + index * width + 1} y={y(bin.normal)} width={Math.max(1, width - 2)} height={250 - y(bin.normal)} fill={BLUE} />
        <rect x={70 + index * width + 1} y={y(bin.normal + bin.outliers)} width={Math.max(1, width - 2)} height={y(bin.normal) - y(bin.normal + bin.outliers)} fill={RED} />
      </g>)}
      <text x="70" y="272" textAnchor="start">{number(column.min)}</text>
      <text x="870" y="272" textAnchor="end">{number(column.max)}</text>
      <text x="470" y="302" textAnchor="middle">{column.column}</text>
      <text transform="translate(18 150) rotate(-90)" textAnchor="middle">Frequency</text>
    </svg>
    <p className="xai-stat-note">Bars count values in equal-width ranges. Blue values are within the IQR fences; red values are outside. Long tails or isolated bars help identify unusual values.</p>
  </>;
}

function Relationship({ data, xName, yName }) {
  const points = data.points.filter((point) => Number.isFinite(point.values[xName]) && Number.isFinite(point.values[yName]));
  const correlation = data.correlations.find((item) => (item.x === xName && item.y === yName) || (item.y === xName && item.x === yName));
  if (!points.length) return <p>No paired numeric values are available for these columns.</p>;
  const xs = points.map((point) => point.values[xName]);
  const ys = points.map((point) => point.values[yName]);
  const x = scale(Math.min(...xs), Math.max(...xs), 80, 865);
  const y = scale(Math.min(...ys), Math.max(...ys), 250, 30);
  return <>
    <div className="xai-stat-metrics"><span>Pearson correlation<strong>{correlation?.r == null ? 'N/A' : correlation.r.toFixed(3)}</strong></span><span>Pairs used for correlation<strong>{(correlation?.count || 0).toLocaleString()}</strong></span><span>Points shown<strong>{points.length.toLocaleString()}</strong></span></div>
    <svg viewBox="0 0 920 315" className="xai-stat-svg" role="img" aria-label={`${yName} versus ${xName}; red marks rows flagged by existing detectors`}>
      {x.ticks.map((value, index) => <g key={index}><line x1={x.at(value)} x2={x.at(value)} y1="30" y2="250" className="xai-gridline"/><text x={x.at(value)} y="274" textAnchor="middle">{number(value)}</text></g>)}
      {y.ticks.map((value, index) => <g key={index}><line x1="80" x2="865" y1={y.at(value)} y2={y.at(value)} className="xai-gridline"/><text x="70" y={y.at(value) + 4} textAnchor="end">{number(value)}</text></g>)}
      {points.map((point) => <circle key={point.row} cx={x.at(point.values[xName])} cy={y.at(point.values[yName])} r={point.flagged ? 4.5 : 3} fill={point.flagged ? RED : BLUE} opacity={point.flagged ? .85 : .5}>
        <title>Row {point.row}: {xName} = {precise(point.values[xName])}; {yName} = {precise(point.values[yName])}. {point.flagged ? 'Flagged by at least one detector; the flag may concern another column.' : 'No row-level finding.'}</title>
      </circle>)}
      <text x="470" y="307" textAnchor="middle">{xName}</text>
      <text transform="translate(17 145) rotate(-90)" textAnchor="middle">{yName}</text>
    </svg>
    <p className="xai-stat-note">Look for points separated from the main relationship. Red means an existing detector flagged the row, possibly for another column. Correlation is descriptive, not an anomaly verdict; it is undefined for constant columns or fewer than three pairs.</p>
  </>;
}

export default function StatisticalGraphs({ data }) {
  const [view, setView] = useState('box');
  const [selectedColumn, setSelectedColumn] = useState('');
  const [secondColumn, setSecondColumn] = useState('');
  if (!data) return null;
  const column = data.columns.find((item) => item.column === selectedColumn) || data.columns[0];
  const choices = data.columns.filter((item) => item.column !== column?.column);
  const yName = choices.find((item) => item.column === secondColumn)?.column || choices[0]?.column;
  const sampled = data.scope === 'reservoir';
  return <section className="xai-score-card xai-statistics">
    <div className="xai-map-head"><div><h2>Statistical exploration</h2><span>{sampled
      ? `Statistics use a uniform sample of ${data.statistics_rows.toLocaleString()} rows drawn across all ${data.total_rows.toLocaleString()} rows. Counts describe the sample.`
      : `Statistics use all ${data.total_rows.toLocaleString()} rows; each column excludes missing or non-numeric values.`}</span></div></div>
    {!column ? <p>No numeric columns are available for statistical graphs.</p> : <>
      <div className="xai-stat-controls">
        <div className="xai-stat-buttons" aria-label="Statistical graph">
          {[['box', 'Box plot'], ['histogram', 'Histogram'], ['relationship', 'Relationship scatter']].map(([id, label]) => <button type="button" key={id} aria-pressed={view === id} className={`xai-filter-pill ${view === id ? 'active' : ''}`} onClick={() => setView(id)}>{label}</button>)}
        </div>
        <label>{view === 'relationship' ? 'X column' : 'Numeric column'}<select value={column.column} onChange={(event) => setSelectedColumn(event.target.value)}>{data.columns.map((item) => <option key={item.column}>{item.column}</option>)}</select></label>
        {view === 'relationship' && yName && <label>Y column<select value={yName} onChange={(event) => setSecondColumn(event.target.value)}>{choices.map((item) => <option key={item.column}>{item.column}</option>)}</select></label>}
      </div>
      {view !== 'relationship' && <p>{column.count.toLocaleString()} numeric values · {column.outlier_count.toLocaleString()} outside 1.5 × IQR fences{sampled ? ' in the sample' : ''}. These IQR flags can differ from the anomaly ensemble.</p>}
      {view === 'box' && <BoxPlot column={column} />}
      {view === 'histogram' && <Histogram column={column} />}
      {view === 'relationship' && (yName ? <Relationship data={data} xName={column.column} yName={yName} /> : <p>Relationship scatter needs at least two numeric columns.</p>)}
      {sampled && <p className="xai-stat-note">Sampling can miss rare patterns. The scatter may include additional flagged evidence; those extra points do not influence quartiles, histogram counts or correlation. Existing large-file detection remains batch-relative.</p>}
    </>}
  </section>;
}

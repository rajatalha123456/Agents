export default function DataTable({ columns, rows, rowKey = "id", emptyMessage = "Nothing here yet.", renderActions }) {
  const colSpan = columns.length + (renderActions ? 1 : 0);

  return (
    <div className="card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.key} className={col.align === "right" ? "text-right!" : undefined}>
                  {col.label}
                </th>
              ))}
              {renderActions && <th></th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row[rowKey]}>
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={col.align === "right" ? "text-right" : undefined}
                    style={col.style ? col.style(row) : undefined}
                  >
                    {col.render ? col.render(row) : row[col.key]}
                  </td>
                ))}
                {renderActions && <td className="text-right whitespace-nowrap">{renderActions(row)}</td>}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={colSpan} className="text-center py-10" style={{ color: "var(--ink-400)" }}>
                  {emptyMessage}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

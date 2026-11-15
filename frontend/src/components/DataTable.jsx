// DataTable.jsx
// A simple table for query results and previews.
// Long results show the first rows with a "Show all" button.

import { useState } from "react";
import { formatCell } from "../format.js";

export default function DataTable({ columns, rows, initialRows = 8 }) {
  const [showAll, setShowAll] = useState(false);
  if (!rows || rows.length === 0) {
    return <p className="muted">No rows.</p>;
  }
  const visible = showAll ? rows : rows.slice(0, initialRows);

  return (
    <div>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className={typeof cell === "number" ? "num" : ""}>
                    {formatCell(cell, columns[cellIndex])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > initialRows && (
        <button className="link-button" onClick={() => setShowAll(!showAll)}>
          {showAll ? "Show fewer rows" : `Show all ${rows.length} rows`}
        </button>
      )}
    </div>
  );
}

// format.js
// Small helpers to show numbers, dates and column names nicely.

const indianNumber = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
const smallNumber = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 4 });

// 7556786.25 -> "75,56,786.25" (Indian digit grouping)
export function formatNumber(value) {
  if (typeof value !== "number") return value;
  return Math.abs(value) < 1 ? smallNumber.format(value) : indianNumber.format(value);
}

// 75567862 -> "7.56 Cr", 2500000 -> "25 L". Used on KPI cards where space is short.
export function formatCompact(value) {
  if (typeof value !== "number") return value;
  const size = Math.abs(value);
  if (size >= 1e7) return `${(value / 1e7).toFixed(2)} Cr`;
  if (size >= 1e5) return `${(value / 1e5).toFixed(2)} L`;
  return formatNumber(value);
}

// Format one table cell. A "year" column must stay 2025, not 2,025.
export function formatCell(value, columnName = "") {
  if (value === null || value === undefined) return "";
  if (typeof value === "number" && columnName.toLowerCase() !== "year") return formatNumber(value);
  return String(value);
}

// "product_category" -> "Product Category"
export function niceName(name) {
  return String(name)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

// "2026-11-12T09:15:00+05:30" -> "12 Nov 2026, 9:15 am"
export function formatDateTime(isoText) {
  if (!isoText) return "";
  return new Date(isoText).toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric", hour: "numeric", minute: "2-digit",
  });
}

// "2025-10-01" -> "Oct 2025"
export function formatMonth(isoDate) {
  const [year, month] = String(isoDate).split("-");
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[Number(month) - 1]} ${year}`;
}

const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 });
const percentage = new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 });
export function shown(value) { return value == null || value === "" ? "—" : typeof value === "number" ? number.format(value) : String(value); }
export function percent(value) { return value == null ? "—" : percentage.format(value); }


export function hundredFormat(value) {
  return ({ raw: "Raw", structured: "Structured", structured_monthly_100: "Structured Monthly" })[value] || shown(value);
}

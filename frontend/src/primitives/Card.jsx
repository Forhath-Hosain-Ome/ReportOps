export function Card({ children, accent }) {
  return (
    <div className={`card ${accent ? "card--accent" : ""}`} style={{ "--accent-color": accent }}>
      {children}
    </div>
  );
}
export function Label({ children, required }) {
  return (
    <div className={ `mono label` }>
      {children}{required && <span className={ `label__required` }>*</span>}
    </div>
  );
}

export function SectionTitle({ children }) {
  return (
    <div className={ `section-title` }>
      {children}
    </div>
  );
}
import { ApiMenuButton, CollapsedButton } from "../primitives/Buttons";

export function SectionGroup({
  section,
  collapsed,
  setCollapsed,
  activeId,
  onSelect,
  METHOD_COLORS,
}) {
  const isCollapsed = !!collapsed?.[section.label];

  return (
    <div className="mb-2">
      <CollapsedButton
        label={section.label}
        isCollapsed={isCollapsed}
        onToggle={() =>
          setCollapsed((c) => ({
            ...c,
            [section.label]: !c[section.label],
          }))
        }
      />

      {!isCollapsed &&
        section.endpoints.map((ep) => (
          <ApiMenuButton
            key={ep.id}
            ep={ep}
            active={activeId === ep.id}
            onSelect={onSelect}
            mc={METHOD_COLORS[ep.method] || METHOD_COLORS.GET}
          />
        ))}
    </div>
  );
}
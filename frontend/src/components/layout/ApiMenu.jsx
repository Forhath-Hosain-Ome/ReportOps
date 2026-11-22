import { useState } from "react";
import { SectionGroup } from "../SectionGroup"

const METHOD_COLORS = {
  GET:  { bg: "rgba(34,211,160,0.1)",  text: "var(--color-success)" },
  POST: { bg: "rgba(99,102,241,0.12)", text: "var(--color-accent2)" },
};

export default function ApiMenu({ onSelect, activeId, sections }) {
  const [collapsed, setCollapsed] = useState({});
  if (!sections?.length) return null;

  return (
    <nav className="api_menu">
      <div className="label">
        <span className="text-[10px] font-medium tracking-wildest text-muted" >
          API
        </span>
        <div className="text-[9px] accent-accent mt-0.75" >
          /Path/
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2" >
        {sections.map((section) => (
          <SectionGroup
            key={section.label}
            section={section}
            collapsed={collapsed}
            setCollapsed={setCollapsed}
            activeId={activeId}
            onSelect={onSelect}
            METHOD_COLORS={METHOD_COLORS}
          />
        ))}
      </div>
    </nav>
  );
}
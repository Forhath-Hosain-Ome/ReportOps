import { useState } from "react";
import { useLocation, useOutlet } from "react-router-dom";
import TopNav from "./TopNav";
import LogsPanel from "./LogsPanel";
import ApiMenu from "./ApiMenu";
import OutputPanel from "./OutputPanel";
import { MENU_BY_SERVICE, SERVICE_BY_PATH } from "../../shared/apiGroup";

export default function DashboardLayout({ onSelect, extraSections = [] }) {
  const location = useLocation();
  const outlet = useOutlet();
  const [activeId, setActiveId] = useState(null);

  const segment = location.pathname.split("/")[1] || "";
  const serviceKey = SERVICE_BY_PATH[segment];
  const sections = [...(MENU_BY_SERVICE[serviceKey] ?? []), ...extraSections];

  const handleSelect = async (ep) => {
    setActiveId(ep.id);
    await onSelect(ep);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: outlet ? undefined : "100vh", minHeight: "100vh", minWidth: 0 }}>
      <TopNav />
      {outlet ? <main style={{ flex: 1, minWidth: 0, width: "100%" }}>{outlet}</main> : <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <LogsPanel />
        <ApiMenu onSelect={handleSelect} activeId={activeId} sections={sections} />
        <OutputPanel />
      </div>}
    </div>
  );
}

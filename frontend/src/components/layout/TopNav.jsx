import { useAuthStore } from "../../store/authStore";
import { useNavigate, useLocation } from "react-router-dom";

const SERVICES = [
  { id: "inspection-summary", label: "INSPECTION SUMMARY", path: "/inspection-summary" },
  { id: "puma", label: "PUMA SUMMARY", path: "/puma" },
  { id: "defect_image", label: "Defect Image", path: "/image" },
  { id: "audit", label: "AUDIT SUMMARY", path: "/audit" },
  { id: "top_five", label: "TOP FIVE", path: "/top-five" },
  { id: "mail-fetch", label: "MAIL DOWNLOAD", path: "/mail-fetch" },
];

function TopNav() {
  const { logout } = useAuthStore();
  const navigate  = useNavigate();
  const location  = useLocation();

  return (
    <header className="bg-linear-to-br from-slate-900 via-indigo-900 to-slate-950" >
      <nav className="sticky top-4 z-50">
        <div className="mx-auto border border-white/20 bg-white/10 backdrop-blur-xl backdrop-saturate-150 shadow-lg ">
          <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4">
            <div className="cursor-pointer text-xl font-bold text-white" onClick={() => navigate("/")}>
              Dashboard
            </div>
            {/* Navigation */}
            <div className="flex flex-wrap items-center gap-2">
              {SERVICES.map((service) => {
                const active = location.pathname === service.path;

                return (
                  <button className={` rounded-xl px-4 py-2 text-sm font-medium transition-all duration-300
                      ${
                        active
                          ? "bg-white/20 text-white shadow-md"
                          : "text-white/80 hover:bg-white/10 hover:text-white"
                      }
                    `}
                    key={service.id}
                    onClick={() => navigate(service.path)}
                  >
                    {service.label}
                  </button>
                );
              })}
            </div>
            {/* Logout */}
            <button onClick={logout} className=" rounded-xl bg-red-500/20 px-4 py-2 text-red-200 transition-all hover:bg-red-500/30">
              Logout
            </button>
          </div>
        </div>
      </nav>
    </header>
  );
}

export default TopNav;
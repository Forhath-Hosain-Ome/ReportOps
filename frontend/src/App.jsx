import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "./store/authStore";
import {LoginPage, PumaPage, AuditSummaryPage, DefectImagePage, Top5Page, MailFetchPage, InspectionSummaryPage }  from "./pages/index";

import DashboardLayout from "./components/layout/DashboardLayout";

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

function RequireAuth({ children }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return isAuthenticated() ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={ <LoginPage /> }/>

          <Route
            element={
              <RequireAuth>
                <DashboardLayout />
              </RequireAuth>
            }
          >
            <Route path="/inspection-summary" element={<InspectionSummaryPage />} />
          </Route>

          <Route path="/puma"
            element={
              <RequireAuth>
                <PumaPage />
              </RequireAuth>
            }
          />
          <Route path="/image"
            element={
              <RequireAuth>
                <DefectImagePage />
              </RequireAuth>
            }
          />
          <Route path="/audit/*" 
            element={
              <RequireAuth>
                <AuditSummaryPage />
              </RequireAuth>
            } 
          />

          <Route path="/top-five"
            element={
              <RequireAuth>
                <Top5Page />
              </RequireAuth>
            }
          />

          <Route path="/mail-fetch"
            element={
              <RequireAuth>
                <MailFetchPage />
              </RequireAuth>
            }
          />
          <Route path="*" 
            element={
              <Navigate to="/login" replace />
            } 
          />

        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

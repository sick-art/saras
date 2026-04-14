import { createBrowserRouter, RouterProvider, Navigate } from "react-router-dom"
import { ThemeProvider } from "@/components/theme-provider"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AppShell } from "@/components/layout/AppShell"
import { ProjectsPage } from "@/pages/ProjectsPage"
import { DashboardPage } from "@/pages/dashboard/DashboardPage"
import { AgentsPage } from "@/pages/agents/AgentsPage"
import { AgentDetail } from "@/pages/agents/AgentDetail"
import { BuilderLayout } from "@/pages/agents/AgentBuilder/BuilderLayout"
import { SimulatorLayout } from "@/pages/simulator/SimulatorLayout"
import { TracesPage } from "@/pages/traces/TracesPage"
import { TraceDetail } from "@/pages/traces/TraceDetail"
import { SessionDetail } from "@/pages/traces/SessionDetail"
import { EvalsPage } from "@/pages/evals/EvalsPage"
import { EvalSuiteDetail } from "@/pages/evals/EvalSuiteDetail"
import { EvalRunDetail } from "@/pages/evals/EvalRunDetail"
import { DatasetsPage } from "@/pages/datasets/DatasetsPage"
import { DatasetDetail } from "@/pages/datasets/DatasetDetail"
import { SettingsPage } from "@/pages/settings/SettingsPage"

/**
 * createBrowserRouter (data mode) instead of <BrowserRouter> (declarative mode).
 *
 * Reason: in declarative mode, route scoring for sibling disambiguation
 * ("agents/new" static vs "agents/:agentId" dynamic) is unreliable when the
 * competing routes live at different JSX nesting depths. In data mode the router
 * is built as a flat object tree upfront, all siblings are ranked together, and
 * static segments reliably beat dynamic ones at every level.
 */
const router = createBrowserRouter([
  // Project selector — no shell
  { path: "/", element: <ProjectsPage /> },

  // All /projects/:projectId/* routes in one parent so siblings are ranked together
  {
    path: "/projects/:projectId",
    children: [
      // ── Full-screen routes (no AppShell) ────────────────────────────────────
      // These must be siblings of the AppShell layout so "agents/new" (static)
      // beats "agents/:agentId" (dynamic) in the same ranking pass.
      { path: "agents/new",               element: <BuilderLayout /> },
      { path: "agents/:agentId/builder",  element: <BuilderLayout /> },
      { path: "agents/:agentId/simulate", element: <SimulatorLayout /> },

      // ── AppShell layout (pathless — wraps workspace routes only) ────────────
      {
        element: <AppShell />,
        children: [
          { index: true,              element: <DashboardPage /> },
          { path: "agents",           element: <AgentsPage /> },
          { path: "agents/:agentId",  element: <AgentDetail /> },
          { path: "traces",                            element: <TracesPage /> },
          { path: "traces/sessions/:sessionId",        element: <SessionDetail /> },
          { path: "traces/:runId",                     element: <TraceDetail /> },
          { path: "evals",                          element: <EvalsPage /> },
          { path: "evals/suites/:suiteId",          element: <EvalSuiteDetail /> },
          { path: "evals/runs/:runId",              element: <EvalRunDetail /> },
          { path: "datasets",                       element: <DatasetsPage /> },
          { path: "datasets/:datasetId",            element: <DatasetDetail /> },
          { path: "settings",                       element: <SettingsPage /> },
        ],
      },
    ],
  },

  // Catch-all
  { path: "*", element: <Navigate to="/" replace /> },
])

export default function App() {
  return (
    <ThemeProvider defaultTheme="system">
      <TooltipProvider>
        <RouterProvider router={router} />
      </TooltipProvider>
    </ThemeProvider>
  )
}

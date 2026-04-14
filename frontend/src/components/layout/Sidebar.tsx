import { NavLink, useParams } from "react-router-dom"
import {
  Bot,
  Database,
  FlaskConical,
  LayoutDashboard,
  Settings,
  GitBranch,
  ChevronDown,
} from "lucide-react"
import { cn } from "@/lib/utils"

interface NavItem {
  label: string
  to: string
  icon: React.ReactNode
  exact?: boolean
}

function NavGroup({ items, projectId }: { items: NavItem[]; projectId: string }) {
  return (
    <nav className="flex flex-col gap-0.5">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to.replace(":projectId", projectId)}
          end={item.exact}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
            )
          }
        >
          <span className="size-4 shrink-0">{item.icon}</span>
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}

const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", to: "/projects/:projectId", icon: <LayoutDashboard />, exact: true },
  { label: "Agents", to: "/projects/:projectId/agents", icon: <Bot /> },
  { label: "Traces", to: "/projects/:projectId/traces", icon: <GitBranch /> },
  { label: "Evaluations", to: "/projects/:projectId/evals", icon: <FlaskConical /> },
  { label: "Datasets", to: "/projects/:projectId/datasets", icon: <Database /> },
  { label: "Settings", to: "/projects/:projectId/settings", icon: <Settings /> },
]

export function Sidebar() {
  const { projectId = "" } = useParams()

  return (
    <aside className="flex h-full w-56 shrink-0 flex-col border-r bg-sidebar">
      {/* Logo / brand */}
      <div className="flex h-14 items-center gap-2 border-b px-4">
        <div className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground text-sm font-bold select-none">
          S
        </div>
        <span className="font-semibold tracking-tight">Saras</span>
      </div>

      {/* Project selector (placeholder) */}
      <button className="flex items-center gap-2 border-b px-4 py-3 text-sm text-left hover:bg-sidebar-accent/50 transition-colors">
        <span className="flex-1 truncate font-medium text-sidebar-foreground">
          {projectId ? `Project` : "Select project"}
        </span>
        <ChevronDown className="size-3.5 text-sidebar-foreground/50 shrink-0" />
      </button>

      {/* Navigation */}
      <div className="flex-1 overflow-y-auto px-2 py-3">
        <NavGroup items={NAV_ITEMS} projectId={projectId} />
      </div>

      {/* Version footer */}
      <div className="border-t px-4 py-3 text-xs text-sidebar-foreground/40">
        Saras v0.1.0
      </div>
    </aside>
  )
}

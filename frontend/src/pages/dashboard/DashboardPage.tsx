import { TopBar } from "@/components/layout/TopBar"
import { Bot, GitBranch, FlaskConical, Database } from "lucide-react"

interface StatCardProps {
  label: string
  value: string
  icon: React.ReactNode
  description: string
}

function StatCard({ label, value, icon, description }: StatCardProps) {
  return (
    <div className="rounded-lg border bg-card p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-muted-foreground">{label}</p>
        <span className="text-muted-foreground/60">{icon}</span>
      </div>
      <p className="mt-2 text-2xl font-bold">{value}</p>
      <p className="mt-1 text-xs text-muted-foreground">{description}</p>
    </div>
  )
}

export function DashboardPage() {
  return (
    <>
      <TopBar title="Dashboard" />
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-5xl space-y-6">
          <div>
            <h2 className="text-xl font-semibold">Welcome to Saras</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Build, simulate, evaluate, and improve your agents from one place.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="Agents"
              value="—"
              icon={<Bot className="size-4" />}
              description="Active agents in this project"
            />
            <StatCard
              label="Runs (7d)"
              value="—"
              icon={<GitBranch className="size-4" />}
              description="Simulation and production runs"
            />
            <StatCard
              label="Eval suites"
              value="—"
              icon={<FlaskConical className="size-4" />}
              description="Configured evaluation suites"
            />
            <StatCard
              label="Dataset items"
              value="—"
              icon={<Database className="size-4" />}
              description="Golden examples across datasets"
            />
          </div>

          <div className="rounded-lg border bg-card p-5">
            <h3 className="text-sm font-semibold">Getting started</h3>
            <ol className="mt-3 space-y-2 text-sm text-muted-foreground list-decimal list-inside">
              <li>Create your first agent in the Agents section</li>
              <li>Use the Chat builder to describe your agent in plain English</li>
              <li>Switch to the Simulator to test it with sample conversations</li>
              <li>Set up an Eval suite to measure quality over time</li>
            </ol>
          </div>
        </div>
      </main>
    </>
  )
}

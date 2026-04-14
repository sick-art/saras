import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { Plus, FolderOpen } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { ProjectRecord } from "@/types/agent"
import { api } from "@/lib/api"

export function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState("")

  useEffect(() => {
    api.get<ProjectRecord[]>("/projects")
      .then(setProjects)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!newName.trim()) return
    const project = await api.post<ProjectRecord>("/projects", { name: newName.trim() })
    setProjects((p) => [project, ...p])
    setNewName("")
    setCreating(false)
  }

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-start pt-20 px-4">
      <div className="w-full max-w-lg">
        {/* Brand */}
        <div className="flex items-center gap-2 mb-8">
          <div className="size-8 rounded-lg bg-primary flex items-center justify-center text-primary-foreground font-bold text-sm select-none">
            S
          </div>
          <span className="text-xl font-semibold">Saras</span>
        </div>

        <h1 className="text-2xl font-bold mb-1">Your projects</h1>
        <p className="text-sm text-muted-foreground mb-6">
          Select a project to continue, or create a new one.
        </p>

        {loading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : (
          <div className="space-y-2">
            {projects.map((p) => (
              <Link
                key={p.id}
                to={`/projects/${p.id}`}
                className="flex items-center gap-3 rounded-lg border bg-card px-4 py-3 hover:bg-accent transition-colors"
              >
                <FolderOpen className="size-4 text-muted-foreground shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{p.name}</p>
                  {p.description && (
                    <p className="text-xs text-muted-foreground truncate">{p.description}</p>
                  )}
                </div>
              </Link>
            ))}

            {creating ? (
              <form onSubmit={handleCreate} className="flex gap-2 mt-3">
                <input
                  autoFocus
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Project name"
                  className="flex-1 rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                />
                <Button type="submit" size="sm">Create</Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setCreating(false)}
                >
                  Cancel
                </Button>
              </form>
            ) : (
              <Button
                variant="outline"
                className="w-full mt-2"
                onClick={() => setCreating(true)}
              >
                <Plus className="size-4 mr-2" />
                New project
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

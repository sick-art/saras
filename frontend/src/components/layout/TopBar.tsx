import type { ReactNode } from "react"
import { Moon, Sun, Monitor } from "lucide-react"
import { useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"

interface TopBarProps {
  title?: string | ReactNode
  breadcrumb?: ReactNode   // shown to the left of the title (back link etc.)
  actions?: ReactNode      // shown to the right, before the theme toggle
}

export function TopBar({ title, breadcrumb, actions }: TopBarProps) {
  const { theme, setTheme } = useTheme()

  function cycleTheme() {
    if (theme === "light") setTheme("dark")
    else if (theme === "dark") setTheme("system")
    else setTheme("light")
  }

  const ThemeIcon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b bg-background px-6">
      <div className="flex items-center gap-3 min-w-0">
        {breadcrumb}
        {title != null && (
          typeof title === "string"
            ? <h1 className="text-sm font-semibold text-foreground">{title}</h1>
            : <div className="flex items-center min-w-0">{title}</div>
        )}
      </div>
      <div className="ml-auto flex items-center gap-2">
        {actions}
        <Button variant="ghost" size="icon-sm" onClick={cycleTheme} title="Toggle theme">
          <ThemeIcon className="size-4" />
        </Button>
      </div>
    </header>
  )
}

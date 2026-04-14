import { TopBar } from "@/components/layout/TopBar"

interface ProviderRowProps {
  name: string
  description: string
  configured: boolean
}

function ProviderRow({ name, description, configured }: ProviderRowProps) {
  return (
    <div className="flex items-center justify-between py-4 border-b last:border-0">
      <div>
        <p className="text-sm font-medium">{name}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
      </div>
      <span
        className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          configured
            ? "bg-green-500/10 text-green-600 dark:text-green-400"
            : "bg-muted text-muted-foreground"
        }`}
      >
        {configured ? "Configured" : "Not set"}
      </span>
    </div>
  )
}

export function SettingsPage() {
  return (
    <>
      <TopBar title="Settings" />
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-2xl space-y-8">
          <div>
            <h2 className="text-xl font-semibold">Settings</h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              Manage LLM provider keys, deployment configuration, and preferences.
            </p>
          </div>

          <section>
            <h3 className="text-sm font-semibold mb-1">LLM Providers</h3>
            <p className="text-xs text-muted-foreground mb-3">
              API keys are configured via environment variables in your deployment.
            </p>
            <div className="rounded-lg border bg-card px-4">
              <ProviderRow
                name="Anthropic (Claude)"
                description="claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5"
                configured={false}
              />
              <ProviderRow
                name="OpenAI"
                description="gpt-4o, o1, o3-mini"
                configured={false}
              />
              <ProviderRow
                name="Google (Gemini)"
                description="gemini-2.0-flash, gemini-1.5-pro"
                configured={false}
              />
            </div>
          </section>

          <section>
            <h3 className="text-sm font-semibold mb-3">Deployment</h3>
            <div className="rounded-lg border bg-card px-4 py-4 text-sm text-muted-foreground">
              Configure all settings via the <code className="font-mono text-xs bg-muted px-1 py-0.5 rounded">.env</code> file
              in your deployment. See <code className="font-mono text-xs bg-muted px-1 py-0.5 rounded">.env.example</code> for
              all available options.
            </div>
          </section>
        </div>
      </main>
    </>
  )
}

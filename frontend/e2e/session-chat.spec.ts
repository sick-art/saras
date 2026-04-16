/**
 * E2E test: Verify that simulator conversations appear correctly in the
 * Traces → Session → Chat tab.
 *
 * Navigates to a session detail page, fetches the raw API data in-browser,
 * runs extractTurns logic, and asserts all turns are rendered.
 *
 * Prerequisites:
 *  - Backend on http://localhost:8000
 *  - Frontend on http://localhost:3000
 */

import { expect, test } from "@playwright/test"

const API = "http://localhost:8000/api"

interface TurnDiagnostic {
  runIndex: number
  userMessage: string | null
  assistantMessage: string | null
  turnType: string | null
  skipped: boolean
  skipReason: string
  spanTypes: string[]
}

test("session chat tab renders all conversation turns", async ({ page, request }) => {
  // Collect ALL browser console logs
  const logs: string[] = []
  page.on("console", msg => logs.push(msg.text()))

  // ── Step 1: Find an existing project with sessions ────────────────────────
  const projectsResp = await request.get(`${API}/projects`)
  const projects = await projectsResp.json()
  if (!projects.length) test.skip()

  const projectId = projects[0].id
  const sessResp = await request.get(`${API}/projects/${projectId}/sessions?limit=5`)
  const sessions = (await sessResp.json()).sessions ?? []
  if (!sessions.length) test.skip()

  const sessionId = sessions[0].session_id
  console.log(`Session: ${sessionId}, runs: ${sessions[0].run_count}`)

  // ── Step 2: Fetch API data directly in the browser context ────────────────
  await page.goto(`/projects/${projectId}/traces/sessions/${sessionId}`)
  await page.waitForSelector("main", { timeout: 10_000 })

  // Fetch the session detail via fetch() inside the browser to get the EXACT
  // same data the frontend receives (same BASE_URL, same JSON parsing)
  const apiData = await page.evaluate(async (sid: string) => {
    const BASE = (window as unknown as Record<string, string>).VITE_API_URL ?? "http://localhost:8000"
    const res = await fetch(`${BASE}/api/projects/${(document.location.pathname.match(/\/projects\/([^/]+)/) ?? [])[1]}/sessions/${sid}`)
    return res.json()
  }, sessionId)

  const runs = apiData.runs
  console.log(`API returned ${runs.length} runs`)

  // ── Step 3: Run extractTurns logic in-browser ─────────────────────────────
  const turns: TurnDiagnostic[] = await page.evaluate((runsData: Array<{ spans: Array<{ type: string; payload: Record<string, unknown> | null }> }>) => {
    return runsData.map((run, i) => {
      const spans = run.spans ?? []
      const rd = spans.find(s => s.type === "router_decision")
      const tc = spans.find(s => s.type === "turn_complete")

      const userMsg = rd?.payload?.user_message ?? null
      const content = tc?.payload?.content ?? null
      const turnType = tc?.payload?.turn_type ?? null
      const skipped = !userMsg && !content

      return {
        runIndex: i + 1,
        userMessage: userMsg as string | null,
        assistantMessage: content ? String(content).slice(0, 80) : null,
        turnType: turnType as string | null,
        skipped,
        skipReason: skipped
          ? `rd=${rd ? `exists(user_msg=${JSON.stringify(rd.payload?.user_message)})` : "MISSING"} tc=${tc ? `exists(content=${JSON.stringify(tc.payload?.content)?.slice(0, 60)})` : "MISSING"}`
          : "",
        spanTypes: spans.map(s => s.type),
      }
    })
  }, runs)

  console.log("\n=== extractTurns diagnostic ===")
  for (const t of turns) {
    if (t.skipped) {
      console.log(`  ✗ Run ${t.runIndex}: SKIPPED — ${t.skipReason}`)
      console.log(`    spanTypes: ${t.spanTypes.join(", ")}`)
    } else {
      console.log(`  ✓ Run ${t.runIndex}: user="${t.userMessage}" asst="${t.assistantMessage}" type=${t.turnType}`)
    }
  }

  const skipped = turns.filter(t => t.skipped)
  const extracted = turns.filter(t => !t.skipped)
  console.log(`\nExtracted: ${extracted.length}/${runs.length} turns, ${skipped.length} skipped`)

  // ── Step 4: Assertions ────────────────────────────────────────────────────

  // Dump browser console logs for diagnosis
  console.log(`\n=== Browser console logs (${logs.length} total) ===`)
  for (const l of logs) {
    if (l.includes("[extractTurns]") || l.includes("[SessionDetail]") || l.includes("SKIPPED")) {
      console.log(l)
    }
  }

  // No turns should be skipped
  expect(skipped, `${skipped.length} turns were skipped:\n${skipped.map(s => `  Run ${s.runIndex}: ${s.skipReason}`).join("\n")}`).toHaveLength(0)

  // Give the page time to render
  await page.waitForTimeout(3000)

  // Also check what the React component sees via window.__sessionData
  const componentData = await page.evaluate(() => {
    const sd = (window as unknown as Record<string, unknown>).__sessionData as {
      runs: Array<{
        id: string
        status: string
        spans: Array<{ type: string; payload: Record<string, unknown> | null }>
      }>
    } | null
    if (!sd || !sd.runs) return { error: "No __sessionData found", keys: Object.keys(window as unknown as Record<string, unknown>).filter(k => k.startsWith("__")) }
    return {
      runCount: sd.runs.length,
      runs: sd.runs.map((r, i) => {
        const rd = r.spans.find(s => s.type === "router_decision")
        const tc = r.spans.find(s => s.type === "turn_complete")
        return {
          i: i + 1,
          status: r.status,
          spanCount: r.spans.length,
          spanTypes: r.spans.map(s => s.type),
          userMessage: (rd?.payload?.user_message as string) ?? null,
          content: tc?.payload?.content ? String(tc.payload.content).slice(0, 60) : null,
          turnType: (tc?.payload?.turn_type as string) ?? null,
        }
      }),
    }
  })
  console.log("\n=== Component __sessionData ===")
  console.log(JSON.stringify(componentData, null, 2))

  // Also dump the rendered chat bubbles
  const renderedUserBubbles = await page.locator("main .rounded-tr-sm").allTextContents()
  const renderedAsstBubbles = await page.locator("main .rounded-tl-sm").allTextContents()
  console.log(`\nRendered user bubbles (${renderedUserBubbles.length}):`, renderedUserBubbles.map(b => b.slice(0, 40)))
  console.log(`Rendered asst bubbles (${renderedAsstBubbles.length}):`, renderedAsstBubbles.map(b => b.slice(0, 40)))

  const mainText = await page.locator("main").innerText()

  // Verify each user message appears in the rendered page
  for (const t of extracted) {
    if (t.userMessage) {
      const snippet = t.userMessage.length > 20 ? t.userMessage.slice(0, 20) : t.userMessage
      expect(mainText, `User msg "${snippet}" not in page`).toContain(snippet)
    }
  }

  console.log("\n✓ All turns extracted and visible on page")
})

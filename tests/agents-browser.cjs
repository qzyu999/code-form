const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright-core");

(async () => {
  const base = process.env.CODEFORM_URL || "http://127.0.0.1:7332";
  const artifacts = path.resolve(__dirname, "..", ".codeform", "browser-artifacts");
  await fs.mkdir(artifacts, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const bootstrap = await (await page.request.get(base + "/api/bootstrap")).json();
    const snapshot = bootstrap.snapshots.find(s => s.repository.name === "verified-transfer");
    const headers = { "X-Codeform-Token": bootstrap.token };
    const proposalResponse = await page.request.post(`${base}/api/v1/snapshots/${snapshot.id}/proposals`, {
      headers, data: {
        kind: "explanation", title: `Explain the conservation theorem ${Date.now()}`, agent: "browser integration",
        rationale: "The checked arithmetic establishes cancellation of the transferred amount.",
        content: "For a successful transfer, x = source - amount and y = destination + amount; their sum is unchanged. The source translator remains trusted.",
        evidence: [{ path: "transfer.py", line_start: 4, line_end: 8 }],
      },
    });
    assert.equal(proposalResponse.status(), 201);
    const proposal = await proposalResponse.json();
    await page.goto(`${base}/#${snapshot.id}/agents`);
    await page.getByRole("heading", { name: "Agent workspace", exact: true }).waitFor();
    await page.getByRole("heading", { name: proposal.title, exact: true }).waitFor();
    const form = page.locator(`form[data-proposal="${proposal.id}"]`);
    const note = `The explanation correctly names the model and source boundary (${proposal.id}).`;
    await form.locator("textarea").fill(note);
    await form.getByRole("button", { name: "Save proposal review" }).click();
    await page.getByText(note, { exact: true }).waitFor();
    await page.getByRole("button", { name: "Refresh agent work" }).click();
    await page.locator(".agent-attempt").first().waitFor();
    await page.locator(".agent-attempt summary").first().click();
    await page.locator(".agent-attempt .lean-preview").first().waitFor();
    await page.screenshot({ path: path.join(artifacts, "agent-workspace.png"), fullPage: true });
    await page.reload();
    await page.getByText(note, { exact: true }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.deepEqual(errors, []);
    console.log("Agent UI passed: API proposal, review, persisted history, Lean diagnostics, refresh, and mobile layout.");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });

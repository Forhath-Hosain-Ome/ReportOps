// Run against a local Vite server with Playwright available through NODE_PATH:
// IMAGE_RECOVERY_TEST_URL=http://127.0.0.1:5181 node --test tests/image-publication-recovery.test.js
import { after, before, test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { env } from "node:process";

const { chromium } = createRequire(import.meta.url)("playwright");
const baseURL = env.IMAGE_RECOVERY_TEST_URL || "http://127.0.0.1:5181";
assert.ok(["127.0.0.1", "localhost"].includes(new URL(baseURL).hostname), "Use a local test server only");
let browser;
before(async () => { browser = await chromium.launch({ channel: env.PLAYWRIGHT_BROWSER_CHANNEL || "msedge", headless: true }); });
after(async () => { await browser?.close(); });

function pendingBatch(state, expired) {
  return { id: 41, status: "PENDING", dispatch_state: state,
    lease_expires_at: new Date(Date.now() + (expired ? -60000 : 3600000)).toISOString(),
    total_folders: 1, processed_folders: 0, failed_folders_count: 0, partial_reports: 0,
    submitted_images: 1, successful_images: 0, failed_images: 0, progress_percent: 0,
    success_rate: 0, reports: [], failed_folder_records: [] };
}

async function withPage(batch, check) {
  const page = await browser.newPage();
  let requests = 0;
  try {
    await page.addInitScript(() => {
      // Unsigned UI fixture only; every Image API request is intercepted below.
      const payload = btoa(JSON.stringify({ user_id: 1, exp: 4102444800 }));
      localStorage.setItem("qc-auth", JSON.stringify({ state: { access: `test.${payload}.test`, refresh: null }, version: 0 }));
      window.WebSocket = class { constructor() { this.readyState = 3; } close() {} };
      const set = window.setInterval.bind(window);
      const clear = window.clearInterval.bind(window);
      window.__publicationPollTimers = new Set();
      window.setInterval = (callback, delay, ...args) => {
        const id = set(callback, delay, ...args);
        if (delay === 2000) window.__publicationPollTimers.add(id);
        return id;
      };
      window.clearInterval = (id) => { window.__publicationPollTimers.delete(id); clear(id); };
    });
    await page.route("**/image/**", async (route) => {
      if (new URL(route.request().url()).pathname === "/image/settings/") {
        await route.fulfill({ json: { can_manage: false } });
      } else if (new URL(route.request().url()).pathname === "/image/folder/batches/41/") {
        requests += 1;
        await route.fulfill({ json: batch });
      } else {
        await route.abort(); // No real backend or external service is contacted.
      }
    });
    await page.goto(`${baseURL}/image`);
    await page.getByText("List Batches", { exact: true }).waitFor();
    const mount = async (type) => page.evaluate(async ({ type, batch }) => {
      const { useOutputStore } = await import("/src/store/outputStore.js");
      useOutputStore.getState().setOutput(type, type === "batch-progress" ? { batch_id: batch.id } : batch,
        "Publication regression", { source: "image" });
    }, { type, batch });
    await check(page, mount, () => requests);
  } finally { await page.close(); }
}

for (const state of ["REQUESTED", "PUBLISHING"]) {
  test(`expired ${state}: BatchDetail exposes recovery without failed reports`, async () => {
    await withPage(pendingBatch(state, true), async (page, mount) => {
      await mount("batch");
      await page.getByRole("button", { name: "Recover dispatch", exact: true }).waitFor({ timeout: 3000 });
      assert.equal(await page.getByRole("button", { name: "Recover dispatch", exact: true }).count(), 1);
    });
  });

  test(`expired ${state}: upload polling exits, clears its interval and surfaces recovery`, async () => {
    await withPage(pendingBatch(state, true), async (page, mount, requests) => {
      await mount("batch-progress");
      await page.getByRole("button", { name: "Recover dispatch", exact: true }).waitFor({ timeout: 7000 });
      await page.waitForFunction(() => window.__publicationPollTimers.size === 0);
      assert.equal(requests(), 1);
      assert.equal(await page.evaluate(async () => {
        const { useOutputStore } = await import("/src/store/outputStore.js");
        return useOutputStore.getState().output.type;
      }), "batch");
    });
  });

  test(`live ${state}: no premature recovery or polling exit`, async () => {
    await withPage(pendingBatch(state, false), async (page, mount, requests) => {
      await mount("batch");
      await page.getByRole("heading", { name: "Batch #41", exact: true }).waitFor();
      assert.equal(await page.getByRole("button", { name: "Recover dispatch", exact: true }).count(), 0);
      await mount("batch-progress");
      await page.waitForResponse((response) => response.url().endsWith("/image/folder/batches/41/"));
      assert.equal(requests(), 1);
      assert.equal(await page.evaluate(() => window.__publicationPollTimers.size), 1);
      assert.equal(await page.evaluate(async () => {
        const { useOutputStore } = await import("/src/store/outputStore.js");
        return useOutputStore.getState().output.type;
      }), "batch-progress");
    });
  });
}

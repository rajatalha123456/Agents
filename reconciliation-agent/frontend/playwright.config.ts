import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  timeout: 180000,
  expect: {timeout:15000},
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:5180', trace: 'retain-on-failure', screenshot: 'only-on-failure', channel: 'chrome' },
  webServer: [
    {command: `"${path.resolve('../.venv/Scripts/python.exe')}" -m uvicorn workbench.app:app --app-dir ../backend --host 127.0.0.1 --port 8767`, url:'http://127.0.0.1:8767/api/health', reuseExistingServer:false, env:{RECON_WORKBENCH_DB:path.resolve(`../.data/ux-e2e-${Date.now()}.sqlite3`), GEMINI_API_KEY:'', RECON_LLM__API_KEY:'', RECON_ALLOWED_ORIGINS:'http://127.0.0.1:5180'}},
    {command:'npm.cmd run dev -- --port 5180', url:'http://127.0.0.1:5180', reuseExistingServer:false, env:{RECON_API_URL:'http://127.0.0.1:8767'}},
  ],
  projects: [{name:'desktop', use:{...devices['Desktop Chrome'], viewport:{width:1440,height:1050}}}],
});

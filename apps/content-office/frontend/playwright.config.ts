import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  outputDir: "./test-results/playwright",
  fullyParallel: false,
  workers: 1,
  reporter: [
    ["list"],
    ["json", { outputFile: "test-results/browser-results.json" }],
  ],
  use: {
    baseURL: process.env.OFFICE_BROWSER_BASE_URL ?? "http://127.0.0.1:3110",
    viewport: { width: 1440, height: 1050 },
    launchOptions: {
      executablePath: process.env.OFFICE_BROWSER_EXECUTABLE || undefined,
      env: {
        ...Object.fromEntries(
          Object.entries(process.env).filter(
            (entry): entry is [string, string] => entry[1] !== undefined,
          ),
        ),
        LD_LIBRARY_PATH: `${process.cwd()}/.browser-libs/root/usr/lib/x86_64-linux-gnu:${process.env.LD_LIBRARY_PATH ?? ""}`,
      },
    },
  },
});

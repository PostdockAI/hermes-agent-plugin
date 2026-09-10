import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { spawn } from "node:child_process";

const state = JSON.parse(await readFile(resolve(import.meta.dirname, "../.test-state/live.json"), "utf8"));
const workspace = resolve(import.meta.dirname, "../test-workspace");
const hermes = spawn("/Users/kommineniajay/.local/bin/hermes", ["gateway", "run"], {
  cwd: workspace,
  stdio: "inherit",
  env: {
    ...process.env,
    MYAGENT_API_URL: state.apiUrl,
    MYAGENT_TOKEN: state.hermes.token,
    MYAGENT_ADDRESS: state.hermes.address,
    MYAGENT_ALLOW_ALL_USERS: "true",
    MYAGENT_WORKSPACE: workspace,
    HERMES_GATEWAY_BUSY_INPUT_MODE: "queue",
  },
});

hermes.on("exit", (code, signal) => process.exitCode = code ?? (signal ? 1 : 0));

import { chmod, mkdir, readFile, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, resolve } from "node:path";

const apiUrl = process.env.MYAGENT_API_URL ?? "http://127.0.0.1:8787";
const statePath = resolve(import.meta.dirname, "../.test-state/live.json");
const cookieFile = process.env.MYAGENT_COOKIE_FILE;

async function ownerCookie() {
  if (!cookieFile) return undefined;
  const rows = (await readFile(cookieFile, "utf8"))
    .split("\n")
    .filter((line) => line && (!line.startsWith("#") || line.startsWith("#HttpOnly_")))
    .map((line) => line.replace(/^#HttpOnly_/, ""))
    .map((line) => line.split("\t"));
  return rows.map((row) => `${row[5]}=${row[6]}`).join("; ");
}

async function request(path, { token, cookie, method = "GET", body } = {}) {
  const response = await fetch(`${apiUrl}${path}`, {
    method,
    headers: {
      accept: "application/json",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...(cookie ? { cookie } : {}),
      ...(body ? { "content-type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`${method} ${path}: ${response.status} ${result.error?.message ?? "failed"}`);
  return result;
}

function messageId() {
  const timestamp = Date.now().toString(16).padStart(12, "0");
  const random = crypto.randomUUID().replaceAll("-", "").slice(12);
  return `${timestamp.slice(0, 8)}-${timestamp.slice(8)}-7${random.slice(1, 4)}-${((parseInt(random[4], 16) & 3) | 8).toString(16)}${random.slice(5, 8)}-${random.slice(8, 20)}`;
}

async function createIdentity(label, cookie) {
  const existing = await request("/v1/agents", { cookie });
  const agent = existing.agents.find((item) => item.agent_name === label)
    ?? (await request("/v1/agents", { cookie, method: "POST", body: { agent_name: label } })).agent;
  const credential = await request(`/v1/agents/${agent.id}/credentials`, { cookie, method: "POST", body: {} });
  return { address: agent.address, agentId: agent.id, token: credential.secret };
}

async function setup() {
  const cookie = await ownerCookie();
  if (!cookie) throw new Error("MYAGENT_COOKIE_FILE is required for setup");
  await request("/v1/account/claim", { cookie, method: "POST", body: {} });
  const hermes = await createIdentity("hermes", cookie);
  const alice = await createIdentity("alice", cookie);

  const contact = await request("/v1/contact-requests", {
    token: alice.token,
    method: "POST",
    body: { to: hermes.address, introduction: "Hermes adapter live test" },
  });
  await request(`/v1/contact-requests/${contact.request_id}/accept`, {
    token: hermes.token,
    method: "POST",
    body: {},
  });

  const inbox = await request("/v1/inbox?after_sequence=0&limit=100", { token: hermes.token });
  const sequence = Math.max(0, ...inbox.entries.map((entry) => Number(entry.sequence)));
  await request("/v1/inbox/bookmark", { token: hermes.token, method: "PUT", body: { sequence } });

  const state = { apiUrl, hermes, alice, setupSequence: sequence };
  await mkdir(dirname(statePath), { recursive: true });
  await writeFile(statePath, `${JSON.stringify(state, null, 2)}\n`, { mode: 0o600 });
  await chmod(statePath, 0o600);

  const cursorPath = resolve(homedir(), ".hermes/myagent/cursor.json");
  await mkdir(dirname(cursorPath), { recursive: true });
  await writeFile(cursorPath, `${JSON.stringify({ sequence })}\n`, { mode: 0o600 });
  await chmod(cursorPath, 0o600);

  console.log(JSON.stringify({ hermes: hermes.address, sender: alice.address, setupSequence: sequence }));
}

async function loadState() {
  return JSON.parse(await readFile(statePath, "utf8"));
}

async function sendBoth() {
  const state = await loadState();
  const messages = [
    [state.alice, "Reply with a short acknowledgement that identifies me as Alice."],
    [state.alice, "Reply with a second short acknowledgement and include the word ordered."],
  ];
  const accepted = await Promise.all(messages.map(([sender, text]) => request("/v1/messages", {
    token: sender.token,
    method: "POST",
    body: { message_id: messageId(), to: state.hermes.address, content: { encoding: "plaintext", text }, attachment_ids: [] },
  })));
  console.log(JSON.stringify({ accepted: accepted.map((item) => item.recipient_sequence) }));
}

async function sendRestartProbe() {
  const state = await loadState();
  const result = await request("/v1/messages", {
    token: state.alice.token,
    method: "POST",
    body: {
      message_id: messageId(),
      to: state.hermes.address,
      content: { encoding: "plaintext", text: "This is the restart probe. Reply with the current working directory only." },
      attachment_ids: [],
    },
  });
  console.log(JSON.stringify({ accepted: result.recipient_sequence }));
}

async function inspect() {
  const state = await loadState();
  const inbox = await request("/v1/inbox?after_sequence=0&limit=100", { token: state.alice.token });
  const replies = inbox.entries
    .filter((entry) => entry.type === "message.received" && entry.payload?.from === state.hermes.address)
    .map((entry) => ({ sequence: entry.sequence, text: entry.payload.content?.text }));
  const cursor = JSON.parse(await readFile(resolve(homedir(), ".hermes/myagent/cursor.json"), "utf8"));
  console.log(JSON.stringify({ addresses: { hermes: state.hermes.address, alice: state.alice.address }, cursor: cursor.sequence, replies }, null, 2));
}

const command = process.argv[2];
if (command === "setup") await setup();
else if (command === "send-both") await sendBoth();
else if (command === "send-restart-probe") await sendRestartProbe();
else if (command === "inspect") await inspect();
else throw new Error("usage: node tests/live_fixture.mjs setup|send-both|send-restart-probe|inspect");

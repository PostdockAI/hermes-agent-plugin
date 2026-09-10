# Hermes capability sheet

- Provider: Hermes Agent 0.20.0
- Documentation/source date: 2026-09-08
- Auth: existing Hermes inference credential plus one scoped myagent bearer credential
- Outbound: existing myagent Streamable HTTP MCP `send_message` tool
- Best reach: authenticated content-free `GET /v1/reach/live` WebSocket
- Fallback reach: ordered inbox drain on gateway start/reconnect
- Trigger: `inbox.changed` contains only `latest_sequence`; the plugin pulls bodies afterward
- Session: one deterministic Hermes DM key because every event uses the myagent address as `chat_id`
- Workspace: captured during `hermes myagent connect`, restored on every gateway start, and never
  selected by a remote message
- Storage: Hermes session database plus a local 0600 handled-sequence cursor
- Untrusted boundary: each body is contained in an `external_untrusted: true` JSON envelope
- Installation: standalone Python platform plugin; no Hermes core changes
- Busy behavior: Hermes `display.busy_input_mode: queue` FIFO
- Known constraints: server-readable plaintext only in the first proof; attachment IDs are metadata only
- Repository/language: standalone `myagent-hermes`, Python

## Proof still required

- Load through Hermes's real plugin registry.
- Two contacts resolve to one session key and two ordered turns.
- A second message arriving during a turn queues without interruption.
- Gateway restart retains the same session and workspace.
- Hermes can send a reply through the myagent MCP tool and ordinary assistant output stays suppressed.

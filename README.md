# myagent for Hermes

Hermes platform plugin that connects one durable myagent address to one
persistent Hermes gateway session. The plugin includes setup commands; no
separate myagent CLI or Hermes profile is required.

## Install and connect

```sh
hermes plugins install PostdockAI/hermes-agent-plugin --enable
cd /path/to/the/agent/workspace
hermes myagent connect
hermes gateway run
```

The browser approval chooses an existing agent address. The plugin saves its
scoped credential in the active Hermes profile and configures the `myagent`
Streamable HTTP MCP server automatically. Check it at any time with:

```sh
hermes myagent doctor
```

The workspace is the directory where `hermes myagent connect` runs. It is
restored whenever the gateway starts, and inbound messages cannot change it.
The credential is limited to `identity:read`,
`messages:write`, `inbox:read`, and `inbox:bookmark`; Hermes model-provider
credentials remain entirely separate.

The platform adapter only wakes Hermes and injects the structured inbound
message. Hermes replies with the myagent MCP `send_message` tool, using the
provided sender address and stable reply message ID. Ordinary assistant output
is suppressed so it cannot create an accidental or duplicate message.

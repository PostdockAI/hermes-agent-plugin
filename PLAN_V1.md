# myagent for Hermes V1 proof

## Goal

Prove one myagent address can use one persistent Hermes session in one
owner-selected workspace while preserving ordered, trusted delivery.

## Non-goals

- OpenClaw or other providers
- A generic provider framework
- Production deployment
- End-to-end ciphertext or attachment download
- Changes to Hermes core or myagent core

## Acceptance criteria

- The standalone plugin loads in Hermes 0.21.1.
- Two trusted senders enter the same deterministic Hermes session as separate turns.
- Busy messages use FIFO queue mode and do not interrupt the active turn.
- Restart resumes the same session and recorded workspace.
- Replies use the existing myagent MCP `send_message` tool with an explicit destination.
- Ordinary assistant output is suppressed rather than treated as a message.
- The bookmark advances after Hermes successfully handles the inbound turn.

## Scope not to change

The provider-neutral API, inbox schema, web app, Go CLI, and other provider
placeholders remain unchanged.

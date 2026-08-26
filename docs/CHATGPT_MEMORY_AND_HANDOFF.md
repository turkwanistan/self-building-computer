# ChatGPT Memory and Handoff Policy

Purpose: preserve reliable continuity across fresh ChatGPT sessions without treating ChatGPT memory as an operational database.

## Source-of-truth order

For this project, resolve conflicts in this order:

1. **Root-owned installed state** under `/var/lib/mcp-evolution/` once the safe-MCP lifecycle bootstrap creates it.
2. **`state/current.json`** for the current machine-readable project state.
3. **`NEXT_SESSION.md`** for the smallest exact resumption instruction.
4. **`STATUS.md`** for the human-readable verified snapshot and current gate.
5. **`history/events.jsonl`** for append-only evolution history when prior decisions need explanation.
6. **ChatGPT project/chat memory** only as advisory context.

If ChatGPT memory, an old chat, or a prompt conflicts with current repository or root-owned state, the current state files win.

## What ChatGPT memory is good for

Use memory for durable, non-secret context that changes rarely, such as:

- the high-level objective: build an evolvable MCP plus an isolated unrestricted lab;
- stable working preferences such as concise handoffs and repository-first verification;
- enduring safety boundaries: the unrestricted MCP belongs inside the isolated guest, and widening safe/host authority requires explicit user approval;
- the fact that fresh sessions should begin from `START_HERE.md` rather than reconstructing state from chat history.

Memory may improve convenience, but no implementation step may depend on it being complete or current.

## What must not depend on ChatGPT memory

Keep these in repository/root-owned state instead:

- current lifecycle phase or next gate;
- active/candidate/previous release identifiers;
- tool counts, schema hashes, commit IDs, test results, ports, IPs, tunnel/profile/service state;
- whether a connector refresh/new-chat boundary has been crossed;
- pending implementation work or partially completed commands;
- credentials, API keys, private keys, tokens, or other secrets.

Do not intentionally ask ChatGPT to remember secrets. If sensitive information is accidentally shared, treat source cleanup and credential rotation as the remedy rather than relying on memory deletion alone.

## Recommended ChatGPT project setup

Use a dedicated ChatGPT Project for Self-Building Computer work when practical.

Recommended setting: **Project-only memory**. This keeps project chats able to reference one another while preventing unrelated conversations from becoming implicit project state. Put durable operating rules in Project instructions and/or this repository because project-only memory does not reference personal saved memories.

If project memory is used, keep both `Reference saved memories` and `Reference chat history` enabled where the account requires them for project memory. Product settings can change, so repository state must remain sufficient even if memory behavior changes.

Use Temporary Chat for experiments that should neither use nor contribute to memory.

## Fresh-session protocol

A fresh session should:

1. read `START_HERE.md`;
2. read `NEXT_SESSION.md`;
3. read `state/current.json`;
4. read `STATUS.md`;
5. inspect root-owned installed state when the lifecycle bootstrap exists;
6. verify any live condition needed for the next action instead of trusting old chat/memory;
7. read `history/events.jsonl` or older planning material only when needed to explain a decision or recover missing context.

Do not reread the full history by default. Keep the hot context small.

## End-of-session protocol

Before intentionally crossing a connector refresh/new-chat boundary or ending a material implementation session:

1. update `state/current.json` with the exact current lifecycle state;
2. update `STATUS.md` with what was actually verified;
3. rewrite `NEXT_SESSION.md` so a new session can resume without the previous chat;
4. append one concise event to `history/events.jsonl` for a meaningful lifecycle transition;
5. ensure no credential or secret was written into ChatGPT-writable source;
6. run the relevant project-native checks.

A handoff is complete only when a fresh session could continue correctly using repository/root-owned state alone.

## Freshness rule

ChatGPT memory is optimized for useful continuity, not exact operational freshness. Time-sensitive facts and mutable machine state must be revalidated at the point of use. The repo records the last verified state; live checks establish whether it is still true.

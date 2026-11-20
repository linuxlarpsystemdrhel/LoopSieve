# Integration architecture

LoopSieve runs verification locally without any LLM provider. An opt-in agent runtime connects to one supported provider adapter at a time and restricts model actions before applying patches. External agent CLIs remain separate programs and are not copied into the distribution.

`AgentRuntime -> bounded provider decision -> permission validation -> local file tool -> verification -> SQLite journal + hash-chain evidence`.

MCP is inspected in read-only mode. There is no native MCP server execution runtime in this release, so MCP integration is PARTIAL.

The repo must not claim full compatibility with Codex, OpenCode or other tools unless a live integration test exists.

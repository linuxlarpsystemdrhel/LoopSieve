# GitHub copy

## Repository name

`loopsieve`

## About description

Local verification for coding agents. Runs relevant checks after edits and sends back only new diagnostic evidence.

## Short launch text

LoopSieve is a small local verification layer for coding agents.

After an agent edits code, LoopSieve runs the checks that match the changed files. If a check fails, it returns a compact diagnostic. If the same normalized failure appears again on the next edit, LoopSieve does not send the full log back a second time.

The first integration uses Claude Code's official PostToolBatch hook. It does not proxy Claude, handle subscription credentials, or call another model. The verification engine runs locally and can also be used directly from the CLI.

The 0.2 engineering preview supports Python, Node, Go, and Rust project detection, configurable checks, output limits, timeouts, duplicate failure fingerprints, a local report, and a reproducible benchmark.

The revised stable-repeat synthetic fixture reduces repeated diagnostic text from 19,144 characters to 2,911 across eight iterations. A separate adversarial fixture preserves all four distinct failures. That is a diagnostic-volume result, not a claim that Claude plan usage drops by the same percentage.

I built this because coding agents are good enough that a surprising amount of wasted time now comes from the loop around the model: rerunning checks, rereading nearly identical errors, and spending another turn on information that did not change.

The next milestone is a public benchmark on real repositories. If you use Claude Code, Codex, OpenCode, or another coding agent and have a real failure loop that wastes turns, open an issue with a reproducible case.

## One-line positioning

Fresh verification evidence for coding agents, without another model call.

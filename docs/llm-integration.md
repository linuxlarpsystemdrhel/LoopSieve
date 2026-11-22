# Experimental local diagnostic explanations

`loopsieve check --explain` sends a bounded excerpt from a failed check to a trusted llama.cpp server on loopback. The response is advisory text. Verification determines the exit status. The core works without model files or a model server.

## Run with your own model

Install `llama-server` and supply a compatible GGUF obtained separately. The launcher accepts `--sha256` to verify the file against its publisher's digest before loading it. Keep weights and local configuration in the ignored directories `.local-models/` and `.private/`.

From the checkout, after installing LoopSieve:

```bash
mkdir -p .private
printf '%s\n' '{"model":"local-model"}' > .private/llm.local.json
loopsieve models serve --weights .local-models/your-model.gguf --device cpu
```

Run the example from a second terminal:

```bash
loopsieve check --root examples/local-diagnostics \
  --explain --llm-config .private/llm.local.json example.py
```

The example intentionally fails with exit code 1. The regular command runs the same check without the explanation:

```bash
loopsieve check --root examples/local-diagnostics example.py
```

The launcher binds to `127.0.0.1:8080`. `--device cpu` sets zero GPU layers. `--device auto` delegates offload selection to llama.cpp, and `--device gpu` requests all layers from a GPU-enabled build. The default context is 8,192 tokens. Override it with `--context-tokens` to suit your model and available memory. Press Ctrl+C to stop the server. [llama.cpp server options](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

## Inference settings

The client requires an explicit JSON file with the alias of the model served. The other settings shown below are defaults. Use the same alias in the server's `--model` launcher option and the client configuration.

```json
{
  "model": "local-model",
  "endpoint": "http://127.0.0.1:8080",
  "max_tokens": 128,
  "temperature": 0,
  "seed": 42,
  "timeout_seconds": 60
}
```

Use a numeric loopback HTTP origin, such as `http://127.0.0.1:8080` or `http://[::1]:8080` for a server listening there. The client bypasses proxies and rejects redirects. It limits diagnostic input to 6,400 UTF-8 bytes and replies to 1 MiB. Diagnostic output can include paths or sensitive information emitted by the check itself. Keep the server private. Prefix reuse via `--prompt-cache` is experimental and opt-in.

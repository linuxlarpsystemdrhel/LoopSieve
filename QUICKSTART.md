# Quickstart

```bash
python -m pip install .
python -m loopsieve doctor
python -m loopsieve
```

Inside the workbench:

```text
/status
/hardware
/models
/model select llama3.2:3b --quantization q4_k_m
/team add llama3.2:3b
/team status
/agent run Review the repository and report risks
/hf search SmolLM2
/providers ollama
/quantization llama3.2:3b
/permissions
```

Run a verified local check without an LLM:

```bash
loopsieve init
loopsieve check src/example.py
loopsieve report
```

Run the offline demo:

```bash
loopsieve demo
```

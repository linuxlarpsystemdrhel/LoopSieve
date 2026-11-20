# Installation

## Windows 11 (PowerShell)

```powershell
git clone <repository>
cd loopsieve
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .
python -m loopsieve doctor
python -m loopsieve
```

Optional Textual UI:

```powershell
python -m pip install ".[tui]"
python -m loopsieve tui --provider ollama --model llama3.2:3b
```

Optional local model server: install Ollama separately and use its official
instructions. LoopSieve does not bundle model weights.

## Claude Code hook

```powershell
loopsieve claude install --root .
loopsieve claude status
```

## Tests

```powershell
python -m pytest -q
python -m unittest discover -s tests -v
```

If running from a source checkout without installing, set `PYTHONPATH=src`.

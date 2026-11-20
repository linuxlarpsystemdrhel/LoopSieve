"""Terminal workbench: Textual when installed, zero-dependency fallback otherwise.

The TUI is a view and command surface over the same local state as the CLI. It
does not start a model, a hook or a background daemon on mount.
"""
from __future__ import annotations

from pathlib import Path

from .agent_runtime import Journal
from .agents import TaskStore, list_agents
from .capability import CapabilityRegistry
from .catalog import list_entries
from .config import load_config
from .engine import state_report
from .hardware import detect_hardware
from .mascot import pixel_mascot
from .model_manager import ModelManager
from .model_team import ModelTeam, TeamStore
from .plugins import list_plugins
from .provider_catalog import ProviderCatalog
from .provider_health import ProviderHealthMonitor
from .quantization import method_catalog
from .reliability import rank_agents
from .toolkit import tool_catalog

SECTIONS = ['Dashboard', 'Agents', 'Tasks', 'Tools', 'Skills', 'Verification', 'Models',
            'Providers', 'Provider Health', 'Hugging Face', 'Quantization', 'Model Team', 'Team Dialogue',
            'Capabilities', 'Security', 'Activity', 'Performance', 'Checkpoints',
            'Reliability', 'Settings']


def _safe(call, fallback):
    try:
        return call()
    except Exception as exc:
        return fallback(exc)


def data_rows(section: str, root: Path, filter_text: str = '') -> tuple[list[str], list[list[str]]]:
    """Return display columns and rows. Every section is safe to call without a provider."""
    f = filter_text.lower().strip()
    try:
        if section == 'Agents':
            values = [[x['id'], x['name'], x['specialization'], 'Idle'] for x in list_agents()]
            headers = ['ID', 'Agent', 'Area', 'State']
        elif section == 'Tasks':
            values = [[x['task_id'], x['agent_id'], x['status'], x['task'][:80]] for x in TaskStore(root).all()]
            headers = ['Task ID', 'Agent', 'Status', 'Task']
        elif section == 'Tools':
            values = [[x['id'], x['permission'], x['description']] for x in tool_catalog()]
            headers = ['Tool', 'Scope', 'Operation']
        elif section == 'Plugins':
            values = [[x['id'], x['status'], x['name']] for x in list_plugins()]
            headers = ['Adapter', 'Availability', 'Purpose']
        elif section == 'Skills':
            values = [[x['id'], x['name'], str(len(x['workflow'])) + ' steps'] for x in list_entries('skills')]
            headers = ['Skill', 'Workflow', 'Length']
        elif section == 'Verification':
            report = state_report(root, load_config(root))
            values = [[x.get('name', ''), x.get('status', 'unknown'), str(x.get('duration_seconds', 0)) + 's']
                      for x in report.get('last_results', [])]
            headers = ['Check', 'Status', 'Runtime']
        elif section == 'Performance':
            import os
            import platform
            values = [['Python', platform.python_version()], ['OS', platform.platform()], ['Process', str(os.getpid())]]
            try:
                import psutil  # type: ignore
                values.append(['RSS', f'{psutil.Process().memory_info().rss / 1048576:.1f} MiB'])
            except ImportError:
                values.append(['RSS', 'psutil not installed'])
            hw = detect_hardware()
            values.append(['RAM total', f'{hw.ram_total_mb} MiB' if hw.ram_total_mb else 'unknown'])
            values.append(['VRAM total', f'{hw.total_vram_mb} MiB' if hw.total_vram_mb else 'none detected'])
            values.append(['GPU', hw.gpus[0].name if hw.gpus else 'none detected'])
            headers = ['Metric', 'Value']
        elif section == 'Models':
            manager = ModelManager()
            status = manager.status()
            values = [[x['model'], x['status'], str(x.get('estimate', {}).get('total_mb', '?')), x['license']]
                      for x in status['models']]
            headers = ['Model', 'Fit', 'Est. MiB', 'License']
        elif section == 'Provider Health':
            health = ProviderHealthMonitor().status()
            values = [[k, v.get('state', 'UNVERIFIED'), v.get('kind', ''), v.get('reason', '')[:80]]
                      for k, v in health.get('providers', {}).items()]
            if not values:
                values = [['none observed', 'UNVERIFIED', 'NO_PROBE', 'Run /provider status']]
            headers = ['Provider', 'State', 'Kind', 'Reason']
        elif section == 'Checkpoints':
            journal = Journal(root)
            rows = []
            for session in journal.list()[:30]:
                for cp in journal.checkpoints(session['id'])[:20]:
                    rows.append([session['id'][:8], str(cp['id']), cp['path'], cp['sha256'][:12]])
            values = rows or [['none', '-', 'No file checkpoints yet', '-']]
            headers = ['Session', 'ID', 'Path', 'SHA256']
        elif section == 'Reliability':
            rows = rank_agents(Journal(root))
            values = [[r['agent_id'], str(r['score']), str(r['completed']), str(r['verified']), r['label']]
                      for r in rows[:40]] or [['none', '-', '0', '0', 'No sessions']]
            headers = ['Agent', 'Score', 'Completed', 'Verified', 'Label']
        elif section == 'Capabilities':
            registry = CapabilityRegistry()
            values = [[x.kind, x.id, x.status, x.description[:90]] for x in registry.list()[:120]]
            headers = ['Kind', 'Capability', 'Status', 'Description']
        elif section == 'Providers':
            catalog = ProviderCatalog()
            rows = []
            for profile in catalog.search(limit=80):
                rows.append([profile.id, profile.protocol, profile.status,
                             'yes' if profile.streaming else 'no', ','.join(profile.modalities)])
            values = rows
            headers = ['Provider', 'Protocol', 'Status', 'Streaming', 'Modalities']
        elif section == 'Hugging Face':
            values = [['Search', 'Use /hf search <query>'], ['Categories', 'Text Generation, Code, Vision-Language, Text-to-Image, Audio, 3D'],
                      ['Pagination', 'server-side cursor from the official API'], ['Policy', 'metadata only; no remote code']]
            headers = ['Feature', 'Value']
        elif section == 'Quantization':
            values = [[x['id'], x['family'], x['backend'], str(x['bits']), x['status']]
                      for x in method_catalog()['methods']]
            headers = ['Method', 'Family', 'Backend', 'BPW', 'Status']
        elif section == 'Model Team':
            journal = Journal(root)
            team = ModelTeam(root, store=TeamStore(journal.path.parent / 'team.db'), journal=journal)
            status = team.status()
            values = [[k, str(v)] for k, v in status.items() if not isinstance(v, dict)]
            headers = ['Team Metric', 'Value']
        elif section == 'Team Dialogue':
            journal = Journal(root)
            store = TeamStore(journal.path.parent / 'team.db')
            values = [[x.get('kind'), x.get('from_agent'), x.get('model_id'), x.get('content', '')[:100]]
                      for x in store.messages(limit=80)]
            if not values:
                values = [['none', '-', '-', 'No real team messages yet; use /team run']]
            headers = ['Kind', 'From', 'Model', 'Message']
        elif section == 'Security':
            from .permissions import PermissionEngine
            snap = PermissionEngine().snapshot()
            values = [['Default', snap['policy'].get('default', 'deny')],
                      ['Levels', ', '.join(snap['levels'])],
                      ['Unsafe actions', 'deny-by-default'],
                      ['Secrets', 'DPAPI/keyring; no catalog plaintext'],
                      ['Downloads', 'license + approval + SHA-256']]
            headers = ['Policy', 'Value']
        elif section == 'Activity':
            journal = Journal(root)
            rows = []
            for session in journal.list()[:30]:
                for ev in journal.events(session['id'])[-5:]:
                    rows.append([session['id'][:8], ev['kind'], str(ev['details'])[:100]])
            values = rows or [['none', 'no activity', '']]
            headers = ['Session', 'Event', 'Details']
        elif section == 'Settings':
            c = load_config(root)
            values = [['Workspace', str(root)], ['Checks', str(len(c.checks))],
                      ['Deduplicate failures', str(c.deduplicate_failures)],
                      ['Cache', 'Off unless complete_inputs explicitly declared'],
                      ['UI', 'Terminal-only; no automatic external execution'],
                      ['Mascot', 'Pip pixel-art in /mascot']]
            headers = ['Setting', 'Value']
        else:
            report = state_report(root, load_config(root))
            stats = report.get('stats', {})
            sessions = Journal(root).list()
            values = [['Workspace', str(root)], ['Verification runs', str(stats.get('runs', 0))],
                      ['Successful runs', str(stats.get('passed_runs', 0))],
                      ['Failing runs', str(stats.get('failed_runs', 0))],
                      ['Suppressed duplicates', str(stats.get('repeated_failures_suppressed', 0))],
                      ['Catalog agents', '100'], ['Local tools', str(len(tool_catalog()))],
                      ['External adapters', '50; availability varies'], ['Skills', '50'],
                      ['Agent sessions', str(len(sessions))],
                      ['Mascot', pixel_mascot()[0].strip()]]
            headers = ['Overview', 'Value']
    except Exception as exc:
        return ['Status', 'Detail'], [['ERROR', f'{type(exc).__name__}: {exc}']]
    if f:
        values = [row for row in values if f in ' '.join(str(x) for x in row).lower()]
    return headers, values


def _workbench(root: Path, **kwargs):
    from .commands import TerminalWorkbench
    return TerminalWorkbench(root, **kwargs)


def launch(root: Path, provider: str = 'ollama', model: str = 'llama3.2:3b',
           allow_writes: bool = False, allow_checks: bool = False,
           agent_id: str | None = None):
    try:
        from textual.app import App, ComposeResult
        from textual.widgets import Header, Footer, DataTable, Input, Static, TabbedContent, TabPane
        from textual.binding import Binding
    except ImportError:
        return basic_launch(root, provider=provider, model=model,
                            allow_writes=allow_writes, allow_checks=allow_checks, agent_id=agent_id)

    workbench = _workbench(root, provider_name=provider, model=model,
                           allow_writes=allow_writes, allow_checks=allow_checks, agent_id=agent_id)

    class LoopSieveApp(App):
        TITLE = 'LoopSieve'
        SUB_TITLE = 'Terminal workbench for verified coding agents'
        CSS = '''
        Screen { background: #11171d; color: #e6edf3; }
        Header { background: #1d2a33; color: #d8f3e7; }
        Input { margin: 1 2; border: round #5c8f84; background: #17212a; }
        Input#command { border: round #d2a85c; }
        DataTable { margin: 0 2 1 2; height: 1fr; background: #141d26; }
        Static#hint { color: #9db4af; margin: 0 2 1 2; }
        Tabs { background: #1f303b; }
        Tab { color: #d1dedb; }
        Tab.-active { color: #b9f4d9; }
        Footer { background: #223039; }
        '''
        BINDINGS = [Binding('q', 'quit', 'Quit'), Binding('r', 'refresh', 'Refresh'),
                    Binding('/', 'search', 'Search'), Binding('ctrl+p', 'command', 'Command')]

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Static('Local-first. Type a command and press Enter. /help for commands. r refresh, q quit.',
                         id='hint')
            yield Input(placeholder='Filter the current view...', id='filter')
            yield Input(placeholder='Command: /models  /agent run ...  /verify ...', id='command')
            with TabbedContent(initial='dashboard', id='tabs'):
                for name in SECTIONS:
                    pane_id = name.lower().replace(' ', '-')
                    with TabPane(name, id=pane_id):
                        yield DataTable(id='table-' + pane_id)
            yield Footer()

        def on_mount(self):
            for name in SECTIONS:
                self.fill(name)
            self.query_one('#filter', Input).display = False

        def fill(self, name):
            pane_id = name.lower().replace(' ', '-')
            table = self.query_one('#table-' + pane_id, DataTable)
            text = self.query_one('#filter', Input).value if self.is_mounted else ''
            headers, rows = data_rows(name, root, text)
            table.clear(columns=True)
            for heading in headers:
                table.add_column(heading)
            for row in rows:
                table.add_row(*[str(x) for x in row])
            table.cursor_type = 'row'
            table.zebra_stripes = True

        def on_input_changed(self, event: Input.Changed):
            if event.input.id == 'filter':
                for name in SECTIONS:
                    self.fill(name)

        def on_input_submitted(self, event: Input.Submitted):
            if event.input.id != 'command':
                return
            result = workbench.run(event.value)
            self.query_one('#hint', Static).update(result.get('text', '')[:1200])
            event.input.value = ''
            for name in SECTIONS:
                self.fill(name)

        def action_refresh(self):
            for name in SECTIONS:
                self.fill(name)
            self.notify('Local view refreshed')

        def action_search(self):
            inp = self.query_one('#filter', Input)
            inp.display = True
            inp.focus()

        def action_command(self):
            inp = self.query_one('#command', Input)
            inp.focus()

    app = LoopSieveApp()
    app.run()
    return 0


def basic_launch(root: Path, provider: str = 'ollama', model: str = 'llama3.2:3b',
                 allow_writes: bool = False, allow_checks: bool = False,
                 agent_id: str | None = None) -> int:
    """Zero-additional-dependency command loop for all platforms."""
    import sys
    workbench = _workbench(root, provider_name=provider, model=model,
                           allow_writes=allow_writes, allow_checks=allow_checks, agent_id=agent_id)
    chosen = 'Dashboard'
    query = ''
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        console = Console()
    except ImportError:
        console = None
    print('\n  ◈  L O O P S I E V E  ·  terminal workbench')
    print('  ' + pixel_mascot()[0].strip() + '  Pip is awake. /help for commands.\n')
    while True:
        headers, rows = data_rows(chosen, root, query)
        if console:
            console.clear()
            console.print(Panel('[bold #b1dfc9]LoopSieve[/]   Local-first terminal workbench',
                                subtitle='No background model calls', border_style='#547d75'))
            console.print('[#92aaa5]' + '   '.join(f'{i+1} {name}' for i, name in enumerate(SECTIONS)) + '[/]')
            table = Table(show_header=True, header_style='bold #b1dfc9', border_style='#34434a', expand=True)
            for h in headers:
                table.add_column(h, overflow='fold')
            for row in rows[:30]:
                table.add_row(*[str(x)[:130] for x in row])
            console.print(table)
        else:
            print('LoopSieve / ' + chosen + ' | ' + ', '.join(f'{i+1}={n}' for i, n in enumerate(SECTIONS)))
            print(' | '.join(headers))
            for row in rows[:30]:
                print(' | '.join(str(x) for x in row))
        if not sys.stdin.isatty():
            return 0
        try:
            choice = input('Section [1-13], / command, r refresh, q quit > ').strip()
        except (KeyboardInterrupt, EOFError):
            return 0
        if choice.lower() in ('q', 'quit', 'exit'):
            return 0
        if choice == 'r':
            continue
        if choice == '/':
            query = input('Filter > ').strip()
            continue
        if choice.startswith('/'):
            result = workbench.run(choice)
            print(result.get('text', ''))
            continue
        if choice in {str(i) for i in range(1, len(SECTIONS) + 1)}:
            chosen = SECTIONS[int(choice) - 1]
            query = ''
            continue
        print('Unknown command. Type /help.')

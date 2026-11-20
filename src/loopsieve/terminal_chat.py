"""Zero-dependency keyboard-first terminal interaction with autonomous sessions."""
from __future__ import annotations

import json
from pathlib import Path

from .agent_runtime import AgentRuntime,Journal
from .providers import OllamaProvider,CLIProvider

HELP='''Commands:
  /new <task>    Start an agent task
  /step          Execute exactly one model decision
  /run           Continue until completed or budget expires
  /history       Show session event history
  /sessions      List saved sessions
  /resume <id>   Resume a previous session
  /agents        View agent IDs and names
  /quit          Exit. Sessions remain on disk.

All writes and project check commands are disabled unless enabled when launching
this terminal. The model never executes raw shell commands through LoopSieve.
'''


def launch(root:Path,provider='ollama',model='llama3.2:3b',allow_writes=False,allow_checks=False,agent_id=None):
    from .agents import list_agents
    active=CLIProvider(provider) if provider in ('claude','codex') else OllamaProvider(model)
    runtime=AgentRuntime(root,active,Journal(root))
    session=None
    print('\n  ◈  L O O P S I E V E    ·    terminal workspace')
    print('  Local-first agent runner  /  /help for commands  /  /quit to exit')
    print('  Permissions: file writes = %s, project checks = %s\n'%('ON' if allow_writes else 'OFF','ON' if allow_checks else 'OFF'))
    while True:
        try:line=input('loopsieve › ').strip()
        except (EOFError,KeyboardInterrupt):
            print('\nExiting. Your sessions are persisted.');break
        if not line:continue
        if line in ('/quit','/exit'):break
        if line=='/help':print(HELP);continue
        if line=='/sessions':
            for s in runtime.journal.list()[:30]:print(f' {s["id"][:8]}  {s["status"]:10} {s["task"][:55]}')
            continue
        if line=='/agents':
            for agent in list_agents():print(f' {agent["id"]:35} {agent["name"]}')
            continue
        if line.startswith('/resume '):
            val=line.split(' ',1)[1].strip()
            try:
                choices=[x['id'] for x in runtime.journal.list() if x['id'].startswith(val)]
                if len(choices)!=1:raise ValueError('session id ambiguous or unknown')
                session=choices[0]
                state=runtime.journal.get(session)
                print('Selected',session,state['status'])
                if state['status']=='PAUSED':
                    state['status']='READY';runtime.journal.save(state)
            except Exception as exc:print('Error:',exc)
            continue
        if line.startswith('/new ') or not line.startswith('/'):
            task=line.split(' ',1)[1] if line.startswith('/new ') else line
            try:
                state=runtime.create(task,agent_id,allow_writes=allow_writes,allow_checks=allow_checks)
                session=state['id']
                print('  New session:',session,' · ',state['agent_id'])
                print('  Type /step to inspect the next action, /run to continue.')
            except Exception as exc:print('Error:',exc)
            continue
        if not session:
            print('Start a task with /new <description> first.');continue
        if line in ('/step','/run'):
            try:
                state=runtime.step(session) if line=='/step' else runtime.run(session)
                print(f'  [{state["status"]}] {state["step"]}/{state["max_steps"]} model steps')
                last=json.loads(state['messages'][-1]['content'])
                print(json.dumps(last,ensure_ascii=False,indent=2)[:1900])
            except Exception as exc:print('Error:',exc)
            continue
        if line=='/history':
            for ev in runtime.journal.events(session):
                print(f'  {ev["kind"]:17} {json.dumps(ev["details"],ensure_ascii=False)[:230]}')
            continue
        print('Unknown command. Type /help.')
    return 0

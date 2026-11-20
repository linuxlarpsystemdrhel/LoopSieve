"""Loopback-only opt-in agent Studio and original animated 3D mascot.

This is a local user-facing control plane. CSRF token + origin verification; no
remote binding, shell API, credential persistence, or silent background runs.
"""
from __future__ import annotations

import json
import secrets
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,unquote

from .agents import list_agents
from .agent_runtime import AgentRuntime,Journal
from .catalog import list_entries
from .config import load_config
from .engine import state_report
from .plugins import list_plugins
from .providers import OllamaProvider, CLIProvider
from .toolkit import tool_catalog

ASSETS=Path(__file__).resolve().parent/'assets'
MAX_REQUEST=16000


def make_handler(root:Path, token:str|None=None,providers:dict|None=None):
    root=root.resolve()
    secret=token or secrets.token_urlsafe(36)
    assignments={} if providers is None else providers
    journal=Journal(root)

    class StudioHandler(BaseHTTPRequestHandler):
        def _reply(self,data,status=200,content_type='application/json; charset=utf-8'):
            body=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('X-Frame-Options','DENY')
            self.send_header('Content-Security-Policy',"default-src 'none'; connect-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'")
            self.send_header('Content-Length',str(len(body)))
            self.end_headers();self.wfile.write(body)
        def _get_data(self,route):
            if route=='overview':
                return {'counts':{'agents':len(list_agents()),'tools':len(tool_catalog()),'skills':len(list_entries('skills')),
                                  'plugins':len(list_plugins())},'project':str(root)}
            if route=='agents':
                return [{'id':a['id'],'name':a['name'],'specialization':a['specialization']} for a in list_agents()]
            if route=='sessions':return journal.list()
            if route=='tools':return tool_catalog()
            if route=='plugins':return list_plugins()
            if route=='skills':return [{'id':s['id'],'name':s['name'],'steps':len(s.get('workflow',[]))} for s in list_entries('skills')]
            if route=='verification':return state_report(root,load_config(root)).get('last_results',[])
            if route=='evidence':return {'audit': journal.proof.audit(), 'recent': journal.proof.recent(20)}
            if route=='impact':
                from .project_intelligence import python_impact
                return python_impact(root,[])
            if route=='performance':return {'agents_loaded':0,'local_llm_model':'none by default','resource_metrics':'not collected'}
            if route.startswith('events/'):
                return journal.events(route[7:])
            if route.startswith('session/'):
                return journal.get(route[8:])
            raise KeyError(route)
        def do_GET(self):
            route=urlsplit(self.path).path
            try:
                if route=='/':
                    content=(ASSETS/'studio.html').read_text(encoding='utf-8').replace('__CSRF__',secret)
                    return self._reply(content.encode(),content_type='text/html; charset=utf-8')
                if route=='/assets/pip.gltf':
                    return self._reply((ASSETS/'pip.gltf').read_bytes(),content_type='model/gltf+json')
                if route.startswith('/api/'):
                    return self._reply(self._get_data(unquote(route[5:])))
            except (KeyError,ValueError) as e:
                return self._reply({'error':str(e)},404)
            self._reply({'error':'not found'},404)
        def do_POST(self):
            host=self.headers.get('Host','')
            # DNS rebinding and CSRF: reject non-loopback hosts and foreign origins.
            port=self.server.server_port
            if host not in (f'127.0.0.1:{port}',f'localhost:{port}'):
                return self._reply({'error':'invalid localhost Host'},403)
            origin=self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{port}',f'http://localhost:{port}'):
                return self._reply({'error':'cross-origin requests denied'},403)
            if not secrets.compare_digest(self.headers.get('X-LoopSieve-Token',''),secret):
                return self._reply({'error':'missing or invalid local CSRF token'},403)
            try:length=int(self.headers.get('Content-Length','-1'))
            except ValueError:length=-1
            if not 0<=length<=MAX_REQUEST or self.headers.get('Content-Type','').split(';')[0]!='application/json':
                return self._reply({'error':'invalid content length or type'},400)
            try:
                payload=json.loads(self.rfile.read(length))
                if not isinstance(payload,dict):raise ValueError('payload must be JSON object')
                route=urlsplit(self.path).path
                if route=='/api/create':
                    name=payload.get('provider','ollama')
                    if name=='ollama':
                        model=payload.get('model','llama3.2:3b')
                        if not isinstance(model,str) or not 1<=len(model)<=90:raise ValueError('invalid model')
                        provider=OllamaProvider(model)
                    elif name in ('claude','codex'):provider=CLIProvider(name)
                    else:raise ValueError('unknown provider')
                    steps=payload.get('steps',8)
                    if not isinstance(steps,int):raise ValueError('steps must be integer')
                    session=AgentRuntime(root,provider,journal).create(
                        payload.get('task',''),payload.get('agent_id'),steps,
                        allow_writes=payload.get('allow_writes') is True,
                        allow_checks=payload.get('allow_checks') is True)
                    assignments[session['id']]=provider
                    return self._reply({'id':session['id'],'agent_id':session['agent_id'],'status':session['status']},201)
                if route.startswith('/api/'):
                    _,_,action,sid=route.split('/',3)
                    if action not in ('step','pause','cancel'):
                        return self._reply({'error':'unsupported action'},404)
                    if action=='step':
                        if sid not in assignments:raise ValueError('provider not attached to this Studio instance; resume using CLI')
                        rt=AgentRuntime(root,assignments[sid],journal)
                        result=rt.step(sid)
                    else:
                        rt=AgentRuntime(root,None,journal)
                        result=rt.pause(sid) if action=='pause' else rt.cancel(sid)
                    return self._reply({'id':sid,'status':result['status'],'step':result['step'],
                                        'last_message':result['messages'][-1]['content']})
                raise KeyError(route)
            except (KeyError,ValueError,TypeError,RuntimeError) as exc:
                return self._reply({'error':f'{type(exc).__name__}: {exc}'},400)
        def log_message(self,fmt,*args):pass

    StudioHandler.csrf_token=secret
    return StudioHandler


def serve(root:Path,port:int=8766):
    if not (1<=port<=65535):raise ValueError('invalid port')
    server=ThreadingHTTPServer(('127.0.0.1',port),make_handler(root))
    print(f'LoopSieve Studio: http://127.0.0.1:{server.server_port} (Ctrl+C to stop)')
    try:server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:pass
    finally:server.server_close()
    return 0

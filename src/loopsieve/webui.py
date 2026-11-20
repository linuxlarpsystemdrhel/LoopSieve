"""Read-only localhost status dashboard, no remote connection or shell API."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .agents import TaskStore,list_agents
from .catalog import list_entries
from .config import load_config
from .engine import state_report
from .plugins import list_plugins
from .toolkit import tool_catalog

HTML=r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>LoopSieve · Local Console</title><style>
:root{color-scheme:dark;--bg:#111720;--panel:#19222e;--line:#293747;--text:#e3eae8;--muted:#95acb1;--accent:#b1dfc9}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif}
header{padding:30px max(24px,calc((100vw - 1280px)/2));border-bottom:1px solid var(--line);display:flex;align-items:center;gap:16px}
.logo{width:38px;height:38px;border-radius:13px;background:var(--accent);color:#12202a;display:grid;place-items:center;font-size:23px;font-weight:800}
h1{font-size:20px;margin:0;letter-spacing:-.5px}small{color:var(--muted)}.pill{margin-left:auto;border:1px solid #3c655f;border-radius:20px;padding:8px 12px;color:var(--accent);font-size:12px}
main{max-width:1280px;margin:auto;padding:32px 24px;display:grid;grid-template-columns:220px 1fr;gap:28px}
nav{display:flex;flex-direction:column;gap:6px}nav button{padding:12px 14px;text-align:left;background:transparent;border:0;border-radius:9px;color:var(--muted);cursor:pointer;font-size:14px}
nav button.active,nav button:hover{background:#24313a;color:var(--text)}.content{min-width:0}h2{font-size:28px;letter-spacing:-1px;font-weight:600;margin:0 0 8px}p{color:var(--muted);font-size:14px;line-height:1.6}
.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:28px 0}.card{padding:22px;border:1px solid var(--line);border-radius:12px;background:var(--panel)}.number{font-size:29px;font-weight:600;margin:8px 0}.label{color:var(--muted);font-size:12px}
input{padding:13px 16px;border-radius:9px;background:#1b2734;border:1px solid #3b4a56;color:var(--text);width:100%;outline:none;font-size:14px}input:focus{border-color:var(--accent)}
.table{margin-top:15px;overflow:auto;border:1px solid var(--line);border-radius:12px;background:var(--panel)}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:14px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:500}tr:last-child td{border-bottom:0}td{word-break:break-word}.tag{color:#b6e4cf}
@media(max-width:750px){main{grid-template-columns:1fr}nav{flex-direction:row;overflow-x:auto}nav button{white-space:nowrap}.cards{grid-template-columns:1fr}}
</style></head><body><header><div class="logo">L</div><div><h1>LoopSieve</h1><small>Local verification and agent workspace</small></div><span class="pill">● Local only</span></header>
<main><nav id="nav"></nav><div class="content"><h2 id="title">Dashboard</h2><p id="subtitle">Live local metadata. No background model calls.</p><div id="view"></div></div></main>
<script>
const sections=['Dashboard','Agents','Tasks','Tools','Plugins','Skills','Verification','Performance','Settings'];
let current='Dashboard', cache={};const $=id=>document.getElementById(id);
function el(name,txt){const e=document.createElement(name);e.textContent=String(txt??'');return e;}
async function get(section){const res=await fetch('/api/'+section.toLowerCase(),{cache:'no-store'});if(!res.ok)throw Error('HTTP '+res.status);return await res.json();}
function renderTable(records){const input=el('input');input.placeholder='Search entries';const container=el('div');container.className='table';
function redraw(){container.replaceChildren();const list=records.filter(r=>JSON.stringify(r).toLowerCase().includes(input.value.toLowerCase()));const fields=[...new Set(list.flatMap(x=>Object.keys(x)))].slice(0,5);const table=el('table');const tr=el('tr');fields.forEach(k=>tr.appendChild(el('th',k)));table.appendChild(tr);
list.slice(0,200).forEach(x=>{const row=el('tr');fields.forEach(k=>{const value=x[k];row.appendChild(el('td',typeof value==='object'?JSON.stringify(value):value));});table.appendChild(row);});container.appendChild(table);}
input.addEventListener('input',redraw);redraw();$('view').append(input,container);}
async function show(section){current=section;$('title').textContent=section;$('view').replaceChildren();document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('active',x.textContent===section));
try{const data=await get(section);if(section==='Dashboard'){const cards=el('div');cards.className='cards';[['Verification runs',data.stats?.runs||0],['Agents',data.counts?.agents||0],['Local tools',data.counts?.tools||0],['Plugin adapters',data.counts?.plugins||0],['Skills',data.counts?.skills||0],['Failures',data.stats?.failed_runs||0]].forEach(([name,value])=>{const card=el('div');card.className='card';const label=el('div',name);label.className='label';const number=el('div',value);number.className='number';card.append(label,number);cards.appendChild(card)});$('view').appendChild(cards);$('view').appendChild(el('p','LoopSieve verifies code locally and preserves only confirmed diagnostic evidence.'));}
else renderTable(Array.isArray(data)?data:[data]);}catch(e){$('view').appendChild(el('p','Cannot load local data: '+e.message));}}
sections.forEach(s=>{const b=el('button',s);b.addEventListener('click',()=>show(s));$('nav').appendChild(b)});show(current);
</script></body></html>'''


def make_handler(root:Path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route=urlparse(self.path).path
            if route=='/':
                blob=HTML.encode('utf-8'); content_type='text/html; charset=utf-8'
            elif route.startswith('/api/'):
                category=route[5:]
                try:
                    report=state_report(root,load_config(root))
                    routes={
                        'dashboard':lambda:{'stats':report.get('stats',{}),'counts':{'agents':100,'tools':len(tool_catalog()),'plugins':50,'skills':50}},
                        'agents':lambda:[{'id':a['id'],'name':a['name'],'area':a['specialization']} for a in list_agents()],
                        'tasks':lambda:TaskStore(root).all(),
                        'tools':tool_catalog,
                        'plugins':lambda:[{'id':p['id'],'status':p['status'],'name':p['name']} for p in list_plugins()],
                        'skills':lambda:[{'id':s['id'],'name':s['name'],'steps':len(s['workflow'])} for s in list_entries('skills')],
                        'verification':lambda:report.get('last_results',[]),
                        'performance':lambda:{'model_processes':0,'vram_allocated_by_idle_agents_mb':0,'observed_measurements':'not collected in dashboard'},
                        'settings':lambda:{'workspace':str(root),'read_only':True,'bind':'127.0.0.1'},
                    }
                    if category not in routes:raise KeyError(category)
                    blob=json.dumps(routes[category](),ensure_ascii=False).encode();content_type='application/json; charset=utf-8'
                except (KeyError,ValueError):
                    self.send_error(404,'Unknown endpoint');return
            else:
                self.send_error(404,'Not found');return
            self.send_response(200)
            self.send_header('Content-Type',content_type)
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'")
            self.send_header('Content-Length',str(len(blob)))
            self.end_headers();self.wfile.write(blob)
        def log_message(self,fmt,*args):pass
    return Handler


def serve(root:Path,port:int=8765):
    if not (1<=port<=65535):raise ValueError('invalid port')
    server=ThreadingHTTPServer(('127.0.0.1',port),make_handler(root.resolve()))
    print(f'LoopSieve local dashboard: http://127.0.0.1:{server.server_port} (Ctrl+C to stop)')
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
    return 0

"""Read-only, credentials-redacting discovery of project MCP server configuration.

No untrusted MCP server is started, installed, or contacted automatically.
"""
from __future__ import annotations
import json
import shutil
from pathlib import Path
from .toolkit import safe_path


def inspect_mcp(root:Path)->dict:
    configs=[root/'.mcp.json',root/'.claude'/'mcp.json']
    outputs=[]
    for path in configs:
        if not path.is_file():continue
        if path.stat().st_size>250000:
            outputs.append({'config':path.name,'status':'ERROR','reason':'file too large'});continue
        try:
            source=json.loads(path.read_text(encoding='utf-8'))
            servers=source.get('mcpServers',{})
            if not isinstance(servers,dict):raise ValueError('mcpServers must be an object')
            for name,spec in servers.items():
                if not isinstance(spec,dict):raise ValueError('server entry must be object')
                command=spec.get('command')
                # Do not expose command args, URLs (which may contain tokens),
                # env values, HTTP headers, auth or secret metadata.
                enabled=bool(command and shutil.which(command)) if isinstance(command,str) else False
                outputs.append({'name':str(name)[:100],'config':path.relative_to(root).as_posix(),
                                'transport':spec.get('type','stdio' if command else 'remote'),
                                'dependency_present':enabled if command else None,
                                'status':'AVAILABLE' if enabled else 'REQUIRES_DEPENDENCY' if command else 'NOT_PROBED',
                                'execution':'never_started'})
        except (OSError,ValueError,TypeError) as exc:
            outputs.append({'config':path.name,'status':'ERROR','reason':type(exc).__name__})
    return {'project':str(root),'servers':outputs,'note':'MCP discovery is read only. Tool calls and install/enable are not implemented.'}

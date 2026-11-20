"""One-time migration: opt-in model actor policy for the 100 original agent definitions."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'src'/'loopsieve'/'data'/'agents'
read_only_terms=('architect','auditor','reviewer','researcher','analyst','quality director','compliance','security','observer','investigator','scientist')
for file in root.glob('*.json'):
    obj=json.loads(file.read_text())
    role=obj['name'].lower()
    read_only=any(x in role for x in read_only_terms)
    actions=['inspect','tree','verify','finish','blocked'] if read_only else ['inspect','tree','patch','verify','finish','blocked']
    obj['schema_version']=2
    obj['runtime']={
        'kind':'demand_activated_stateful_actor',
        'allowed_actions':actions,
        'lifecycle':['DORMANT','INITIALIZING','READY','PLANNING','WORKING','VERIFYING','PAUSED','BLOCKED','FAILED','COMPLETED','TERMINATED'],
        'provider':'user_selected_only',
        'state_storage':'per_session_sqlite',
        'max_history_messages':15,
        'quality_rule':'evidence_first_completion',
        'can_escalate_permissions':False
    }
    obj['policy']['external_llm_calls']='opt_in_provider_only'
    obj['policy']['auto_execute']=False
    obj['resource_limits']['max_llm_calls']=16
    obj['memory_policy']='Session-scoped, persistently journaled metadata. No model weights or secrets stored.'
    obj['example_workflows'].append('Given a scoped task, inspect sources; propose a bounded edit only if permitted; run local checks only if enabled; deliver verified evidence.') if 'example_workflows' in obj else None
    file.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
print('updated',len(list(root.glob('*.json'))),'agents')

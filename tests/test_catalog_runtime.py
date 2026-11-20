import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from loopsieve.agents import TaskStore,list_agents,select_agents
from loopsieve.catalog import list_entries,load,validate_catalog
from loopsieve.plugins import list_plugins,probe_plugin
from loopsieve.skills import list_skills,run_skill
from loopsieve.toolkit import REGISTRY,run_tool,safe_path,tool_catalog


class CatalogRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.fixtures={
         'README.md':'# Example\n\n[Docs](https://example.com)\n\n## Usage\n',
         'CHANGELOG.md':'# Changelog\n\n## v1\n',
         'main.py':'# TODO: review\nimport json\n\ndef hello():\n    """Say hello."""\n    if True:\n        return 1\n\nclass World:\n    pass\n',
         'config.json':'{"answer":42,"secret":false}',
         'package.json':'{"name":"example","scripts":{"test":"echo ok"},"dependencies":{"foo":"1.0"}}',
         'pyproject.toml':'[project]\nname="example"\nversion="0.1"\n',
         'Cargo.toml':'[package]\nname="example"\nversion="0.1.0"\n',
         'go.mod':'module example.com/demo\nrequire example.com/test v1.2.3\n',
         'requirements.txt':'pytest==1.0\n',
         'sample.yml':'hello: world\n',
         'sample.xml':'<sample><a/></sample>',
         'sample.ini':'[app]\nname=demo\n',
         'sample.csv':'name,age\nA,1\n',
         'dependency.flag':'ok',
         'package-lock.json':'{"lockfileVersion":3}',
         'SECuRITY.md':'# Security',
         'LICENSE':'MIT',
         'CONTRIBUTING.md':'# Contributors',
        }
        for name,txt in self.fixtures.items():
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(txt)
        (self.root/'.github/workflows').mkdir(parents=True)
        (self.root/'.github/workflows/ci.yml').write_text('jobs: {}')
        with ZipFile(self.root/'sample.zip','w') as z:z.writestr('a.txt','hello')
        if shutil.which('git'):
            subprocess.run(['git','init','-q',str(self.root)],capture_output=True,check=True)
            subprocess.run(['git','-C',str(self.root),'add','.'],capture_output=True,check=True)
            subprocess.run(['git','-C',str(self.root),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-q','-m','initial'],capture_output=True,check=True)

    def test_catalog_shapes_count_and_ids(self):
        self.assertEqual(validate_catalog(),{'agents':100,'plugins':50,'skills':50,'technologies':50})
        self.assertEqual(len(REGISTRY),63)
        self.assertEqual(len(set(a['name'] for a in list_agents())),100)
        for a in list_agents():
            self.assertTrue(a['instructions'])
            self.assertEqual(a['resource_limits']['vram_mb'],0)
            self.assertGreaterEqual(a['resource_limits']['max_llm_calls'],1)
            self.assertEqual(a['policy']['external_llm_calls'],'opt_in_provider_only')
            self.assertFalse(a['runtime']['can_escalate_permissions'])
            self.assertFalse(a['policy']['auto_execute'])

    def test_routing_and_task_permission(self):
        selected=select_agents('python pytest unit test')
        self.assertTrue(any(word in selected[0]['name'] for word in ('Test','Python')))
        store=TaskStore(self.root,state_dir=self.root/'state')
        a=store.create('python repair', 'workspace_tree', {}, '002-python-engineer')
        self.assertEqual(a['status'],'QUEUED')
        b=store.create('python repair', 'workspace_tree', {}, '002-python-engineer')
        self.assertEqual(a['task_id'],b['task_id'])
        c=store.run(a['task_id'])
        self.assertEqual(c['status'],'COMPLETED')
        self.assertTrue(c['result']['data'])
        with self.assertRaises(PermissionError):
            store.create('hacking', 'git_ignored', {}, '002-python-engineer')

    def test_task_queue_writes_survive_concurrent_creates(self):
        from concurrent.futures import ThreadPoolExecutor
        store=TaskStore(self.root,state_dir=self.root/'state')
        def create(i):return store.create(f'python task {i}', 'workspace_tree', {}, '002-python-engineer')
        with ThreadPoolExecutor(max_workers=10) as pool:
            created=list(pool.map(create,range(25)))
        self.assertEqual(len({x['task_id'] for x in created}),25)
        self.assertEqual(len(store.all()),25)

    def test_no_automatic_agent_execution(self):
        store=TaskStore(self.root,state_dir=self.root/'state')
        a=store.create('unreal engine design')
        self.assertEqual(store.run(a['task_id'])['status'],'BLOCKED')

    def test_task_cancel(self):
        store=TaskStore(self.root,state_dir=self.root/'state')
        a=store.create('go compile issue')
        self.assertEqual(store.cancel(a['task_id'])['status'],'CANCELLED')
        with self.assertRaises(ValueError):store.run(a['task_id'])

    def test_every_tool_implements_an_actual_operation(self):
        common={'path':'README.md','other':'CHANGELOG.md','query':'Example','pattern':'#', 'limit':100}
        path_by_prefix={
            'python_':'main.py','json_':'config.json','yaml_':'sample.yml','toml_':'pyproject.toml','xml_':'sample.xml',
            'ini_':'sample.ini','csv_':'sample.csv','archive_':'sample.zip',
            'package_':'package.json','pyproject_':'pyproject.toml',
            'go_modules':'go.mod','cargo_':'Cargo.toml','requirements_':'requirements.txt',
            'file_diff':'README.md',
        }
        for name in sorted(REGISTRY):
            args=dict(common)
            for prefix,path in path_by_prefix.items():
                if name.startswith(prefix):args['path']=path
            if name=='file_search_name':args['query']='README'
            if name=='search_text':args['query']='hello'
            if name=='python_todo':args['path']='main.py'
            with self.subTest(tool=name):
                result=run_tool(name,self.root,args)
                self.assertIsNotNone(result)
                self.assertNotEqual(result,'NOT_IMPLEMENTED')

    def test_filesystem_boundary_and_secrets(self):
        with self.assertRaises(PermissionError):safe_path(self.root,'../secret.txt')
        with self.assertRaises(PermissionError):run_tool('file_read',self.root,{'path':'.env'})
        self.assertIn('Example',run_tool('file_read',self.root,{'path':'README.md'}))
        self.assertEqual(run_tool('file_sha256',self.root,{'path':'README.md'}),run_tool('file_sha256',self.root,{'path':'README.md'}))

    def test_technology_registry_points_to_callable_source(self):
        import importlib
        for item in list_entries('technologies'):
            with self.subTest(technology=item['id']):
                module, symbol = item['implementation'].split('.',1)
                imported=importlib.import_module('loopsieve.'+module)
                self.assertTrue(callable(getattr(imported,symbol)))

    def test_plugin_adapters_have_real_probes_and_missing_status(self):
        items=list_plugins()
        self.assertEqual(len(items),50)
        for entry in items:
            self.assertIn(entry['status'],{'AVAILABLE_NOT_PROBED','REQUIRES_DEPENDENCY'})
            self.assertTrue(load('plugins',entry['id'])['probe_args'])
        # Probe a known installed interpreter, not 50 missing CLIs.
        result=probe_plugin('plugin-python3' if shutil.which('python3') else 'plugin-python')
        self.assertEqual(result['status'],'AVAILABLE')

    def test_skill_steps_are_distinct_tool_sequences(self):
        entries=list_skills(); self.assertEqual(len(entries),50)
        sequences=[tuple(s['tools']) for s in entries]
        self.assertEqual(len(set(sequences)),50)
        result=run_skill('skill-005-assess-release-readiness',self.root)
        self.assertEqual(result['status'],'COMPLETED')
        self.assertEqual(len(result['steps']),3)


if __name__=='__main__':unittest.main()

"""Early build-risk prediction from changed source and local dependency data."""
from __future__ import annotations

from pathlib import Path

from .project_intelligence import python_impact


def predict_failure(root: Path, changed_files: list[str]) -> dict:
    root = Path(root).resolve()
    reasons = []
    score = 0
    python_files = [x for x in changed_files if str(x).endswith('.py')]
    if python_files:
        try:
            impact = python_impact(root, python_files)
            affected = impact.get('potentially_affected', [])
            if affected:
                score += min(40, 8 * len(affected))
                reasons.append(f'{len(affected)} Python file(s) may import a changed module')
        except Exception as exc:
            reasons.append(f'impact analysis unavailable: {type(exc).__name__}')
    tests = [p for p in root.rglob('test_*.py') if p.is_file()] if root.exists() else []
    if python_files and not tests:
        score += 25
        reasons.append('changed Python source but no test_*.py file was found')
    for name in changed_files:
        if str(name).endswith(('.toml', '.json', '.yml', '.yaml')):
            score += 8
            reasons.append(f'configuration change may affect build/CI: {name}')
        if str(name).endswith(('.lock', 'lock.json')):
            score += 12
            reasons.append(f'dependency lock changed: {name}')
    risk = 'HIGH' if score >= 55 else 'MEDIUM' if score >= 25 else 'LOW'
    return {'risk': risk, 'score': score, 'reasons': reasons,
            'changed_files': list(changed_files),
            'confidence': 'HEURISTIC_NOT_MEASURED',
            'recommendation': 'Run the configured local verification before merging.' if score else 'No elevated risk detected by this heuristic.'}

"""Evidence-backed agent reliability ranking, computed from the local journal."""
from __future__ import annotations

from collections import Counter

from .agent_runtime import Journal


def rank_agents(journal: Journal, min_sessions: int = 1) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for summary in journal.list():
        try:
            session = journal.get(summary['id'])
        except KeyError:
            continue
        grouped.setdefault(session['agent_id'], []).append(session)
    rows = []
    for agent_id, sessions in grouped.items():
        counts = Counter(s['status'] for s in sessions)
        total = len(sessions)
        if total < min_sessions:
            continue
        completed = counts.get('COMPLETED', 0)
        failed = counts.get('FAILED', 0)
        blocked = counts.get('BLOCKED', 0)
        verified = sum(1 for s in sessions if any(e.get('status') == 'PASS' for e in s.get('evidence', [])))
        completion_rate = completed / total
        verified_rate = verified / total
        blocked_rate = blocked / total
        score = round(completion_rate * 0.6 + verified_rate * 0.3 - blocked_rate * 0.1, 4)
        rows.append({'agent_id': agent_id, 'total': total, 'completed': completed,
                     'failed': failed, 'blocked': blocked, 'verified': verified,
                     'completion_rate': round(completion_rate, 4),
                     'verified_rate': round(verified_rate, 4),
                     'blocked_rate': round(blocked_rate, 4),
                     'score': score,
                     'label': 'VERIFIED' if verified_rate >= 0.8 and completed else 'PARTIAL' if completed else 'UNPROVEN'})
    rows.sort(key=lambda x: (-x['score'], -x['total'], x['agent_id']))
    return rows


def reliability_summary(journal: Journal) -> dict:
    rows = rank_agents(journal)
    return {'agents_seen': len(rows), 'ranked': rows,
            'policy': 'Rankings use local journal outcomes; they are not a guarantee of future quality.'}

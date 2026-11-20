"""Adaptive swarm budget based on measured/declared memory and call limits."""
from __future__ import annotations

from dataclasses import dataclass

from .hardware import HardwareProfile, detect_hardware


@dataclass
class AdaptiveSwarmBudget:
    hardware: HardwareProfile
    max_agents: int = 8
    max_memory_mb: int | None = None
    max_llm_calls: int = 200

    def __post_init__(self):
        self.max_agents = max(1, min(int(self.max_agents), 32))
        if self.max_memory_mb is None:
            self.max_memory_mb = max(512, int((self.hardware.ram_free_mb or self.hardware.ram_total_mb or 4096) * 0.65))

    def recommend(self, active: int = 0, model_mb: int = 0, calls_used: int = 0) -> dict:
        active = max(0, int(active))
        memory_available = max(0, int(self.max_memory_mb or 0) - model_mb)
        per_agent = max(128, int((model_mb or 512) * 0.35))
        memory_slots = memory_available // per_agent if per_agent else self.max_agents
        call_slots = max(0, self.max_llm_calls - calls_used)
        workers = min(self.max_agents, max(1, memory_slots), max(1, call_slots))
        if active >= workers:
            workers = active
        reason = f'memory_slots={memory_slots}, call_slots={call_slots}, active={active}'
        return {'max_workers': workers, 'active': active, 'model_mb': model_mb,
                'memory_available_mb': memory_available, 'per_agent_reserve_mb': per_agent,
                'calls_remaining': call_slots, 'reason': reason,
                'policy': 'Conservative local estimate; reserve memory before launching more agents.'}

    def can_start(self, active: int, model_mb: int = 0, calls_used: int = 0) -> bool:
        return self.recommend(active, model_mb, calls_used)['max_workers'] > active

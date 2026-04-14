"""Shared interrupt signaling for all tools.

Provides a global threading.Event that any tool can check to determine
if the user has requested an interrupt. The agent's interrupt() method
sets this event, and tools poll it during long-running operations.

Supports both global (legacy) and per-agent interrupt events for
concurrent multi-agent scenarios.

Usage in tools:
    from tools.interrupt import is_interrupted
    if is_interrupted():
        return {"output": "[interrupted]", "returncode": 130}

Per-agent usage:
    from tools.interrupt import is_interrupted, register_agent_interrupt
    event = register_agent_interrupt("agent-123")
    # ... later in tools:
    if is_interrupted(agent_id="agent-123"):
        return {"output": "[interrupted]", "returncode": 130}
"""

import threading
from typing import Optional

_interrupt_event = threading.Event()
_agent_events: dict = {}
_agent_events_lock = threading.Lock()


def set_interrupt(active: bool, agent_id: Optional[str] = None) -> None:
    """Called by the agent to signal or clear the interrupt.

    Args:
        active: True to set the interrupt, False to clear it.
        agent_id: Optional agent identifier for per-agent interrupts.
                  If None, operates on the global event.
    """
    if agent_id is not None:
        with _agent_events_lock:
            event = _agent_events.get(agent_id)
            if event is not None:
                if active:
                    event.set()
                else:
                    event.clear()
    else:
        if active:
            _interrupt_event.set()
        else:
            _interrupt_event.clear()


def is_interrupted(agent_id: Optional[str] = None) -> bool:
    """Check if an interrupt has been requested. Safe to call from any thread.

    Args:
        agent_id: Optional agent identifier for per-agent interrupt check.
                  If None, checks the global event.

    Returns:
        True if an interrupt is active for the given agent (or globally).
    """
    if agent_id is not None:
        with _agent_events_lock:
            event = _agent_events.get(agent_id)
            if event is not None:
                return event.is_set()
    return _interrupt_event.is_set()


def register_agent_interrupt(agent_id: str) -> threading.Event:
    """Register a per-agent interrupt event.

    Args:
        agent_id: Unique identifier for the agent.

    Returns:
        The threading.Event created for this agent.
    """
    event = threading.Event()
    with _agent_events_lock:
        _agent_events[agent_id] = event
    return event


def unregister_agent_interrupt(agent_id: str) -> None:
    """Unregister a per-agent interrupt event.

    Args:
        agent_id: Unique identifier for the agent to remove.
    """
    with _agent_events_lock:
        _agent_events.pop(agent_id, None)

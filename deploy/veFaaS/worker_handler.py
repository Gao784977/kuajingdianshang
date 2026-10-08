# veFaaS Worker Handler
#
# Consumes async task messages from a message queue (e.g. RocketMQ/Kafka)
# and runs V31Workflow phases. This is the production equivalent of the
# local threading.Thread-based WorkflowRunner.
#
# IMPORTANT: Real queue integration (Volcengine RocketMQ/Kafka) is NOT
# included here. This handler defines the message contract and the
# processing loop. The actual queue consumer must be configured when
# deploying to veFaaS.
#
# Production task message structure:
# {
#     "job_id": "...",
#     "phase": "phase_1" | "phase_2",
#     "input_ref": "...",           # storage key or DB reference
#     "checkpoint_ref": "...",      # for phase 2
#     "retry_count": 0,
#     "idempotency_key": "..."
# }

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_SRC = os.path.join(_PROJECT_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """veFaaS Worker handler (message queue trigger).

    Reads a task message, runs the corresponding workflow phase, and
    updates persistent job state.

    Responsibilities (interface only - real cloud integration required):
    - Persist task status to production DB
    - Retry with backoff on transient failures
    - Idempotency via idempotency_key
    - Cooperative cancellation (check cancellation flag)
    - Dead-letter queue for permanently failed tasks
    - Function-timeout handling
    """
    try:
        message = _parse_message(event)
    except (ValueError, KeyError) as exc:
        return {"status": "error", "error": f"invalid message: {exc}"}

    job_id = message["job_id"]
    phase = message["phase"]

    # TODO: Replace with production DB + TOS + queue integration.
    # This is a skeleton that demonstrates the processing contract.
    # In production:
    #   1. Load project inputs from production DB / TOS
    #   2. Run V31Workflow phase
    #   3. Save checkpoint (phase 1) or outputs (phase 2)
    #   4. Update job status in production DB
    #   5. Handle retries / dead-letter / timeout

    return {
        "status": "processed",
        "job_id": job_id,
        "phase": phase,
        "message": "Worker handler skeleton. Real queue/DB/TOS integration required.",
    }


def _parse_message(event: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the task message from the veFaaS event.

    Supports both direct JSON events and wrapped message events.
    """
    if "body" in event:
        body = event["body"]
        if isinstance(body, str):
            body = json.loads(body)
        return body
    if "job_id" in event:
        return event
    raise ValueError("no task message found in event")

"""Agent loop over the escalation harness.

The scripted model is what CI and the hosted trace use. The Foundry-compatible
client is a maintainer command and is not constructed here.
"""

from agent.tools import PUBLISHED_STEP_CAP

__all__ = ["PUBLISHED_STEP_CAP"]

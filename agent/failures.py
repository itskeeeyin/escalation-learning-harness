"""Named failures for the agent loop.

Every stop the loop can reach has a class name and a sentence a person can read.
Messages name the gate. They do not include environment values or credentials.
"""


class AgentFailure(Exception):
    """Base class. ``failure_class`` is the class name, stable for traces and evals."""

    def __init__(self, message):
        self.failure_class = type(self).__name__
        super().__init__(message)


class FoundryKeyMissing(AgentFailure):
    pass


class FoundryAuthFailed(AgentFailure):
    pass


class FoundryRateLimited(AgentFailure):
    pass


class FoundryServerBusy(AgentFailure):
    pass


class FoundryRequestRejected(AgentFailure):
    pass


class EmptyCompletion(AgentFailure):
    pass


class ModelRetry(AgentFailure):
    """Recorded on the trace when a retry is scheduled. The run continues."""


class ModelNoToolCall(AgentFailure):
    pass


class UnknownTool(AgentFailure):
    pass


class StepBudgetExceeded(AgentFailure):
    pass


class CostBudgetExceeded(AgentFailure):
    pass


class ResumeStateCorrupt(AgentFailure):
    pass


class SecretInTrace(AgentFailure):
    pass


class WriteBeforeApproval(AgentFailure):
    pass


class EffectivenessUnconfirmed(AgentFailure):
    pass


class CloseBeforeVerification(EffectivenessUnconfirmed):
    pass


class SkipIntake(AgentFailure):
    pass


class WrongCaseType(AgentFailure):
    pass


class WrongEscalationType(AgentFailure):
    pass


class PolicyGate(AgentFailure):
    """A workflow rule rejected the tool. The model can read it and choose another tool."""


# Stops the run. PolicyGate and UnknownTool are written on the trace and the loop continues.
HARD_STOPS = (
    FoundryKeyMissing,
    FoundryAuthFailed,
    FoundryRateLimited,
    FoundryServerBusy,
    FoundryRequestRejected,
    EmptyCompletion,
    ModelNoToolCall,
    StepBudgetExceeded,
    CostBudgetExceeded,
    ResumeStateCorrupt,
    SecretInTrace,
    WriteBeforeApproval,
    EffectivenessUnconfirmed,
    CloseBeforeVerification,
    SkipIntake,
    WrongCaseType,
    WrongEscalationType,
)

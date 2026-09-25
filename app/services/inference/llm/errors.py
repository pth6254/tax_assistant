class LLMGenerationIncomplete(RuntimeError):
    """The provider stopped before producing a complete answer."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"LLM generation incomplete: {reason}")

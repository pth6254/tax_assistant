class LLMGenerationIncomplete(RuntimeError):
    """The provider stopped before producing a complete answer."""

    def __init__(self, reason: str, partial_content: str = ""):
        self.reason = reason
        self.partial_content = partial_content
        super().__init__(f"LLM generation incomplete: {reason}")


class LLMRequestError(RuntimeError):
    """Safe public error. Never include provider bodies, headers or request text."""

    def __init__(self, code: str, message: str, status_code: int = 502):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)

    def event(self) -> dict:
        return {"type": "error", "code": self.code, "message": self.message}

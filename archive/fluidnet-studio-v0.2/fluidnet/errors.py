from dataclasses import asdict, dataclass


@dataclass
class Diagnostic:
    code: str
    message: str
    element_id: str | None = None
    severity: str = "error"
    field: str | None = None

    def to_dict(self):
        return asdict(self)


class ModelError(Exception):
    def __init__(self, code, message, element_id=None, field=None):
        super().__init__(message)
        self.diagnostic = Diagnostic(code, message, element_id, "error", field)


class ConvergenceError(ModelError):
    pass

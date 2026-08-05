"""Shared domain validation errors."""


class ValidationError(Exception):
    """A business-rule validation failure."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field

    def __str__(self) -> str:
        return self.message

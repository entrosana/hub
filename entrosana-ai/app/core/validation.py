"""Shared domain validation for service-layer inputs."""

from datetime import date


class ValidationError(Exception):
    """A business-rule validation failure."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field

    def __str__(self) -> str:
        return self.message


def require_non_empty(value: str, field: str) -> str:
    """Return a stripped string, rejecting missing or blank values."""
    if value is None or not value.strip():
        raise ValidationError(f"{field} must not be empty", field)
    return value.strip()


def require_positive_amount(amount_cents: int, field: str = "amount_cents") -> int:
    """Require a strictly positive integer amount."""
    if amount_cents <= 0:
        raise ValidationError(f"{field} must be greater than zero", field)
    return amount_cents


def _require_ascii_letters(code: str, length: int, field: str) -> str:
    normalized = code.upper()
    if len(normalized) != length or not normalized.isascii() or not normalized.isalpha():
        raise ValidationError(f"{field} must be {length} ASCII letters", field)
    return normalized


def require_currency(code: str) -> str:
    """Return an uppercase three-letter currency code."""
    return _require_ascii_letters(code, 3, "currency")


def require_country(code: str) -> str:
    """Return an uppercase two-letter country code."""
    return _require_ascii_letters(code, 2, "country")


def require_range(value: int, field: str, *, min: int, max: int) -> int:
    """Require an integer within an inclusive range."""
    if value < min or value > max:
        raise ValidationError(f"{field} must be between {min} and {max}", field)
    return value


def require_order[T: date](
    earlier: T,
    later: T,
    *,
    earlier_field: str,
    later_field: str,
) -> None:
    """Require the later value to be strictly after the earlier value."""
    if later <= earlier:
        raise ValidationError(f"{later_field} must be after {earlier_field}", later_field)


def require_not_before[T: date](
    later: T,
    earlier: T,
    *,
    earlier_field: str,
    later_field: str,
) -> None:
    """Require the later value not to precede the earlier value."""
    if later < earlier:
        raise ValidationError(f"{later_field} must not be before {earlier_field}", later_field)

"""
Decimal utilities for safe money and rate operations.

All monetary calculations in the quoting system MUST use fixed-point Decimal
arithmetic.  Float is never acceptable for money.  These helpers enforce that
constraint and provide round-trip JSON serialization that preserves precision.
"""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import json
from typing import Any, Union


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

def to_decimal(
    value: Union[str, int, float, Decimal, None],
    default: Decimal = Decimal("0.00"),
) -> Decimal:
    """Convert any value to Decimal safely.

    Uses ``str()`` as an intermediary for floats so that the Decimal
    constructor receives the human-readable representation rather than the
    IEEE-754 binary value (e.g. ``str(0.1)`` -> ``"0.1"`` instead of
    ``Decimal(0.1)`` -> ``Decimal("0.100000000000000005551…")``).

    Returns *default* when *value* is ``None`` or cannot be parsed.
    """
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


# ---------------------------------------------------------------------------
# Rounding
# ---------------------------------------------------------------------------

def round_money(d: Decimal, places: int = 2) -> Decimal:
    """Round a Decimal to *places* decimal places using ROUND_HALF_UP.

    Default is 2 places -- suitable for USD dollar amounts.
    """
    quantize_str = "0." + "0" * places
    return d.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)


def round_rate(d: Decimal, places: int = 4) -> Decimal:
    """Round rates and percentages to *places* decimal places.

    Default is 4 places -- suitable for tax rates, markup percentages, and
    unit-cost rates that need more precision than dollar amounts.
    """
    quantize_str = "0." + "0" * places
    return d.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# JSON serialization
# ---------------------------------------------------------------------------

class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that serializes Decimal values as strings.

    This preserves full precision across serialization boundaries.  Use with
    ``json.dumps(data, cls=DecimalEncoder)``.
    """

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def decimal_to_json_dict(data: Any) -> Any:
    """Recursively convert Decimals in a dict/list structure to strings.

    Useful before storing data in a JSONB column or sending over the wire
    where Decimal is not a native type.
    """
    if isinstance(data, Decimal):
        return str(data)
    if isinstance(data, dict):
        return {k: decimal_to_json_dict(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [decimal_to_json_dict(v) for v in data]
    return data


def json_dict_to_decimal(data: Any) -> Any:
    """Recursively parse string and numeric values back to Decimals.

    Strings that look like valid decimal numbers are converted; everything
    else is left untouched.  ``int`` and ``float`` values are converted via
    ``str()`` first to avoid float precision artifacts.
    """
    if isinstance(data, str):
        try:
            return Decimal(data)
        except InvalidOperation:
            return data
    if isinstance(data, dict):
        return {k: json_dict_to_decimal(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [json_dict_to_decimal(v) for v in data]
    if isinstance(data, (int, float)):
        return Decimal(str(data))
    return data

"""Microstructure intelligence availability (§22).

The repository contains NO real order-book / depth / order-flow data.
The explicit state is therefore MICROSTRUCTURE_UNAVAILABLE — recorded,
not hidden. Real order-book evidence is NEVER synthesized and presented
as real (§22, §57); microstructure signals activate only when genuine
data with provenance exists.
"""

from pydantic import BaseModel, ConfigDict

#: The repository-level availability declaration (§22).
MICROSTRUCTURE_UNAVAILABLE = "MICROSTRUCTURE_UNAVAILABLE"


class MicrostructureAvailability(BaseModel):
    """Explicit microstructure data availability declaration (§22)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    available: bool
    reason: str

    @property
    def status(self) -> str:
        if self.available:
            return "MICROSTRUCTURE_AVAILABLE"
        return MICROSTRUCTURE_UNAVAILABLE


def microstructure_availability(
    *,
    order_book_data_present: bool,
) -> MicrostructureAvailability:
    """Declare availability from an honest data inventory flag.

    ``order_book_data_present`` MUST reflect the actual inventory — the
    function never upgrades an absent dataset.
    """
    if order_book_data_present:
        return MicrostructureAvailability(
            available=True,
            reason="order-book/depth data present with documented provenance",
        )
    return MicrostructureAvailability(
        available=False,
        reason=(
            "no order-book/depth/order-flow data in the repository — "
            "microstructure signals stay explicitly UNAVAILABLE and are "
            "never synthesized (§22/§57)"
        ),
    )


__all__ = [
    "MICROSTRUCTURE_UNAVAILABLE",
    "MicrostructureAvailability",
    "microstructure_availability",
]

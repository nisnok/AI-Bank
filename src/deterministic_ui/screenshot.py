"""Provider-independent screenshot policy and non-sensitive capture manifest."""
from enum import StrEnum

from pydantic import Field

from .models import Model


class ScreenshotPolicy(StrEnum):
    FULL_MASK = "FULL_MASK"
    SELECTIVE_REDACTION = "SELECTIVE_REDACTION"
    DISABLED = "DISABLED"


class ScreenshotManifest(Model):
    policy: ScreenshotPolicy
    masked_regions: int = Field(default=0, ge=0)
    categories: list[str] = Field(default_factory=list)
    fallback_full_mask: bool = False
    reason: str | None = None

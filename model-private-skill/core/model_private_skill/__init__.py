"""Platform-neutral private-model inference capacity planning core."""

from .request import calculate_request, validate_request

__all__ = ["calculate_request", "validate_request"]
__version__ = "1.4.0"

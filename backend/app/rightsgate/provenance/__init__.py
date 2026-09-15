"""Provenance adapters for VeilGraph RightsGate."""

from .c2pa import C2PAVerificationResult, verify_c2pa
from .image_forensics import ImageForensicsResult, inspect_image_forensics

__all__ = [
    "C2PAVerificationResult",
    "ImageForensicsResult",
    "inspect_image_forensics",
    "verify_c2pa",
]

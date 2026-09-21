"""Provenance adapters for VeilGraph RightsGate."""

from .c2pa import C2PAVerificationResult, verify_c2pa
from .image_forensics import ImageForensicsResult, inspect_image_forensics
from .watermark import (
    VisibleWatermarkProfile,
    VisibleWatermarkRegistry,
    WatermarkVerificationResult,
    build_visible_watermark_profile,
    verify_visible_watermarks,
)

__all__ = [
    "C2PAVerificationResult",
    "ImageForensicsResult",
    "inspect_image_forensics",
    "verify_c2pa",
    "VisibleWatermarkProfile",
    "VisibleWatermarkRegistry",
    "WatermarkVerificationResult",
    "build_visible_watermark_profile",
    "verify_visible_watermarks",
]

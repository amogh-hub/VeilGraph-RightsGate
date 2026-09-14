"""Governed local rights-reference capabilities."""

from .image_registry import (
    ReferenceKind,
    RegistryImage,
    RightsImageMatchResult,
    RightsReferenceRegistry,
    build_registry_image,
    image_dhash,
    match_reference_image,
)
from .licensing import (
    LicenceEvaluationResult,
    LicenceRecord,
    LicenceRegistry,
    LicenceState,
    evaluate_candidate_licences,
)

__all__ = [
    "ReferenceKind",
    "RegistryImage",
    "RightsImageMatchResult",
    "RightsReferenceRegistry",
    "build_registry_image",
    "image_dhash",
    "match_reference_image",
    "LicenceEvaluationResult",
    "LicenceRecord",
    "LicenceRegistry",
    "LicenceState",
    "evaluate_candidate_licences",
]

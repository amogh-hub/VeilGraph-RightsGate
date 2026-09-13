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

__all__ = [
    "ReferenceKind",
    "RegistryImage",
    "RightsImageMatchResult",
    "RightsReferenceRegistry",
    "build_registry_image",
    "image_dhash",
    "match_reference_image",
]

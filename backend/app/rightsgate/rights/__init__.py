"""Governed local rights-reference capabilities."""

from .consent import (
    ConsentAnalysisResult,
    ConsentGrant,
    ConsentRegistry,
    LikenessTemplate,
    VoiceTemplate,
    analyze_likeness_consent,
    analyze_voice_consent,
    build_likeness_template,
    build_voice_template,
    voice_reference_features,
)

from .image_registry import (
    ImageFeatureManifest,
    ReferenceKind,
    RegistryImage,
    RightsImageMatchResult,
    RightsReferenceRegistry,
    build_registry_image,
    image_dhash,
    image_feature_manifest,
    match_reference_image,
)
from .licensing import (
    LicenceEvaluationResult,
    LicenceRecord,
    LicenceRegistry,
    LicenceState,
    evaluate_candidate_licences,
)
from .localization import LocalizedReferenceMatchResult, localize_reference_images

__all__ = [
    "ConsentAnalysisResult",
    "ConsentGrant",
    "ConsentRegistry",
    "LikenessTemplate",
    "VoiceTemplate",
    "analyze_likeness_consent",
    "analyze_voice_consent",
    "build_likeness_template",
    "build_voice_template",
    "voice_reference_features",
    "ImageFeatureManifest",
    "ReferenceKind",
    "RegistryImage",
    "RightsImageMatchResult",
    "RightsReferenceRegistry",
    "build_registry_image",
    "image_dhash",
    "image_feature_manifest",
    "match_reference_image",
    "LicenceEvaluationResult",
    "LicenceRecord",
    "LicenceRegistry",
    "LicenceState",
    "evaluate_candidate_licences",
    "LocalizedReferenceMatchResult",
    "localize_reference_images",
]

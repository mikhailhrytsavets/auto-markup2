class WebhookServiceError(Exception):
    """Base exception for webhook service errors."""


class UnknownWebhookEventError(WebhookServiceError):
    """Raised when webhook event type is not supported."""


class InvalidNodePathError(WebhookServiceError):
    """Raised when the provided webhook path is invalid for processing."""


class ConfigStructureError(WebhookServiceError):
    """Raised when config.yaml has an unexpected structure."""


class MappingDecodeError(WebhookServiceError):
    """Raised when Mapping.csv cannot be decoded."""


class MappingMissingColumnError(WebhookServiceError):
    """Raised when Mapping.csv misses required columns."""


class MetadataDownloadError(WebhookServiceError):
    """Raised when metadata files cannot be downloaded."""


class ProjectNotFountError(WebhookServiceError):
    """Raised when batch-project not in db."""

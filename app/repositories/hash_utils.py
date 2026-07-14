"""Content hash utility for idempotent document ingestion."""

import hashlib


def compute_content_hash(tenant_id: str, title: str, content: str) -> str:
    """Compute a SHA256 content hash for idempotency checks.

    Args:
        tenant_id: Tenant namespace.
        title: Document title.
        content: Document body text.

    Returns:
        SHA256 hex digest string.
    """
    return hashlib.sha256(f"{tenant_id}:{title}:{content}".encode()).hexdigest()

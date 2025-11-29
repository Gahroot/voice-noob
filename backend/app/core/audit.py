"""Audit logging for sensitive operations.

Provides structured audit logging for security-sensitive operations like:
- API key changes
- User authentication events
- Data access/export
- Agent configuration changes
- Workspace operations
"""

from typing import Any

import structlog

logger = structlog.get_logger("audit")

# Minimum length for masking (show last N chars)
_MASK_SUFFIX_LENGTH = 4


class AuditAction:
    """Audit action constants."""

    # Authentication
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILED = "auth.login.failed"
    LOGOUT = "auth.logout"
    REGISTER = "auth.register"
    PASSWORD_CHANGE = "auth.password.change"

    # API Keys
    API_KEY_CREATE = "api_key.create"
    API_KEY_UPDATE = "api_key.update"
    API_KEY_DELETE = "api_key.delete"

    # Agents
    AGENT_CREATE = "agent.create"
    AGENT_UPDATE = "agent.update"
    AGENT_DELETE = "agent.delete"
    AGENT_ACTIVATE = "agent.activate"
    AGENT_DEACTIVATE = "agent.deactivate"

    # Workspaces
    WORKSPACE_CREATE = "workspace.create"
    WORKSPACE_UPDATE = "workspace.update"
    WORKSPACE_DELETE = "workspace.delete"

    # Contacts/CRM
    CONTACT_CREATE = "contact.create"
    CONTACT_UPDATE = "contact.update"
    CONTACT_DELETE = "contact.delete"
    CONTACT_EXPORT = "contact.export"

    # Phone Numbers
    PHONE_ACQUIRE = "phone.acquire"
    PHONE_RELEASE = "phone.release"

    # Calls
    CALL_INITIATE = "call.initiate"
    CALL_COMPLETE = "call.complete"

    # Compliance/Privacy
    DATA_EXPORT = "compliance.data_export"
    DATA_DELETE = "compliance.data_delete"
    CONSENT_UPDATE = "compliance.consent_update"

    # Integrations
    INTEGRATION_CONNECT = "integration.connect"
    INTEGRATION_DISCONNECT = "integration.disconnect"


def audit_log(
    action: str,
    user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    success: bool = True,
    ip_address: str | None = None,
) -> None:
    """Log an audit event.

    Args:
        action: The action being performed (use AuditAction constants)
        user_id: ID of the user performing the action
        resource_type: Type of resource being acted upon (e.g., "agent", "workspace")
        resource_id: ID of the resource being acted upon
        details: Additional details about the action
        success: Whether the action succeeded
        ip_address: Client IP address
    """
    log_data: dict[str, Any] = {
        "audit": True,  # Flag for filtering audit logs
        "action": action,
        "success": success,
    }

    if user_id is not None:
        log_data["user_id"] = user_id
    if resource_type:
        log_data["resource_type"] = resource_type
    if resource_id:
        log_data["resource_id"] = resource_id
    if ip_address:
        log_data["ip_address"] = ip_address

    # Merge additional details, but sanitize sensitive fields
    if details:
        sanitized = _sanitize_details(details)
        log_data["details"] = sanitized

    # Use appropriate log level
    if success:
        logger.info("audit_event", **log_data)
    else:
        logger.warning("audit_event", **log_data)


def _sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
    """Remove or mask sensitive fields from audit details.

    Args:
        details: The details dict to sanitize

    Returns:
        Sanitized details dict
    """
    sensitive_fields = {
        "password",
        "api_key",
        "secret",
        "token",
        "auth_token",
        "access_token",
        "refresh_token",
        "openai_api_key",
        "telnyx_api_key",
        "twilio_auth_token",
        "deepgram_api_key",
        "elevenlabs_api_key",
    }

    sanitized = {}
    for key, value in details.items():
        lower_key = key.lower()
        if any(sensitive in lower_key for sensitive in sensitive_fields):
            # Mask the value, showing only last N chars
            if isinstance(value, str) and len(value) > _MASK_SUFFIX_LENGTH:
                sanitized[key] = f"****{value[-_MASK_SUFFIX_LENGTH:]}"
            else:
                sanitized[key] = "****"
        else:
            sanitized[key] = value

    return sanitized


def audit_api_key_change(
    user_id: int,
    workspace_id: str | None,
    key_type: str,
    action: str,
    ip_address: str | None = None,
) -> None:
    """Convenience function to audit API key changes.

    Args:
        user_id: User making the change
        workspace_id: Workspace ID (if workspace-scoped)
        key_type: Type of API key (openai, telnyx, twilio, etc.)
        action: create, update, or delete
        ip_address: Client IP
    """
    audit_action = {
        "create": AuditAction.API_KEY_CREATE,
        "update": AuditAction.API_KEY_UPDATE,
        "delete": AuditAction.API_KEY_DELETE,
    }.get(action, AuditAction.API_KEY_UPDATE)

    audit_log(
        action=audit_action,
        user_id=user_id,
        resource_type="api_key",
        resource_id=workspace_id,
        details={"key_type": key_type, "workspace_scoped": workspace_id is not None},
        ip_address=ip_address,
    )


def audit_agent_change(
    user_id: int,
    agent_id: str,
    action: str,
    changes: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """Convenience function to audit agent changes.

    Args:
        user_id: User making the change
        agent_id: Agent being modified
        action: create, update, delete, activate, deactivate
        changes: Dict of changed fields (for updates)
        ip_address: Client IP
    """
    action_map = {
        "create": AuditAction.AGENT_CREATE,
        "update": AuditAction.AGENT_UPDATE,
        "delete": AuditAction.AGENT_DELETE,
        "activate": AuditAction.AGENT_ACTIVATE,
        "deactivate": AuditAction.AGENT_DEACTIVATE,
    }

    audit_log(
        action=action_map.get(action, AuditAction.AGENT_UPDATE),
        user_id=user_id,
        resource_type="agent",
        resource_id=agent_id,
        details={"changes": changes} if changes else None,
        ip_address=ip_address,
    )


def audit_data_export(
    user_id: int,
    export_type: str,
    record_count: int,
    ip_address: str | None = None,
) -> None:
    """Convenience function to audit data exports.

    Args:
        user_id: User performing the export
        export_type: Type of data being exported (contacts, calls, etc.)
        record_count: Number of records exported
        ip_address: Client IP
    """
    audit_log(
        action=AuditAction.DATA_EXPORT,
        user_id=user_id,
        resource_type=export_type,
        details={"record_count": record_count},
        ip_address=ip_address,
    )

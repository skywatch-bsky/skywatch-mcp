# pattern: Imperative Shell

import json
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx

from skywatch_mcp.config import OzoneSettings
from skywatch_mcp.server import mcp

# _settings is created at import time to capture environment variables at load time.
# Environment variables are typically static for the lifetime of the process.
# Tests reload this module when env vars change, which is the accepted pattern.
_settings = OzoneSettings()

# Session cache at module level
_cached_session: dict[str, str] | None = None

REVIEW_STATE_MAP = {
    "open": "tools.ozone.moderation.defs#reviewOpen",
    "escalated": "tools.ozone.moderation.defs#reviewEscalated",
    "closed": "tools.ozone.moderation.defs#reviewClosed",
    "none": "tools.ozone.moderation.defs#reviewNone",
}

EVENT_TYPE_MAP = {
    "takedown": "tools.ozone.moderation.defs#modEventTakedown",
    "reverseTakedown": "tools.ozone.moderation.defs#modEventReverseTakedown",
    "comment": "tools.ozone.moderation.defs#modEventComment",
    "report": "tools.ozone.moderation.defs#modEventReport",
    "label": "tools.ozone.moderation.defs#modEventLabel",
    "acknowledge": "tools.ozone.moderation.defs#modEventAcknowledge",
    "escalate": "tools.ozone.moderation.defs#modEventEscalate",
    "mute": "tools.ozone.moderation.defs#modEventMute",
    "unmute": "tools.ozone.moderation.defs#modEventUnmute",
    "muteReporter": "tools.ozone.moderation.defs#modEventMuteReporter",
    "unmuteReporter": "tools.ozone.moderation.defs#modEventUnmuteReporter",
    "email": "tools.ozone.moderation.defs#modEventEmail",
    "resolveAppeal": "tools.ozone.moderation.defs#modEventResolveAppeal",
    "divert": "tools.ozone.moderation.defs#modEventDivert",
    "tag": "tools.ozone.moderation.defs#modEventTag",
    "accountEvent": "tools.ozone.moderation.defs#accountEvent",
    "identityEvent": "tools.ozone.moderation.defs#identityEvent",
    "recordEvent": "tools.ozone.moderation.defs#recordEvent",
}


def _validate_ozone_config() -> str | None:
    if not _settings.is_configured:
        return "Ozone is not configured. Set OZONE_HANDLE, OZONE_PDS, OZONE_ADMIN_PASSWORD, and OZONE_DID environment variables."
    return None


def _build_subject_ref(subject: str, cid: str | None = None) -> dict[str, str]:
    if subject.startswith("did:"):
        return {"$type": "com.atproto.admin.defs#repoRef", "did": subject}
    if subject.startswith("at://"):
        if not cid:
            raise ValueError(
                "AT-URI subjects require a cid parameter. Use com.atproto.repo.getRecord to resolve the CID for the record."
            )
        return {"$type": "com.atproto.repo.strongRef", "uri": subject, "cid": cid}
    raise ValueError(f"Subject must be a DID (did:plc:...) or AT-URI (at://...). Got: {subject}")


def _build_mod_tool(batch_id: str | None = None) -> dict[str, Any]:
    from datetime import datetime, timezone

    # Note: TS version uses a custom UUIDv7 implementation. We use uuid4 here
    # which is acceptable — batch IDs only need uniqueness, not time-ordering.
    # Python 3.14+ will have native uuid7() if time-ordering is later desired.
    return {
        "name": "skywatch-mcp",
        "meta": {
            "time": datetime.now(timezone.utc).isoformat(),
            "batchId": batch_id or str(uuid.uuid4()),
        },
    }


def _build_query_string(
    params: dict[str, str | list[str] | None],
) -> str:
    parts: list[tuple[str, str]] = []
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, list):
            for item in value:
                parts.append((key, item))
        else:
            parts.append((key, value))
    qs = urlencode(parts)
    return f"?{qs}" if qs else ""


async def _create_session() -> str:
    global _cached_session
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"https://{_settings.pds}/xrpc/com.atproto.server.createSession",
            json={
                "identifier": _settings.handle,
                "password": _settings.admin_password,
            },
        )
        if response.status_code != 200:
            raise ValueError(f"Failed to create session ({response.status_code}): {response.text}")
        session: dict[str, Any] = response.json()
        _cached_session = {
            "accessJwt": session["accessJwt"],
            "refreshJwt": session["refreshJwt"],
        }
        return str(session["accessJwt"])


async def _refresh_session() -> str:
    global _cached_session
    if not _cached_session:
        return await _create_session()

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"https://{_settings.pds}/xrpc/com.atproto.server.refreshSession",
            headers={"Authorization": f"Bearer {_cached_session['refreshJwt']}"},
        )
        if response.status_code != 200:
            _cached_session = None
            return await _create_session()

        session: dict[str, Any] = response.json()
        _cached_session = {
            "accessJwt": session["accessJwt"],
            "refreshJwt": session["refreshJwt"],
        }
        return str(session["accessJwt"])


async def _get_access_token() -> str:
    if _cached_session:
        return _cached_session["accessJwt"]
    return await _create_session()


async def _ozone_request(
    method: str,
    path: str,
    body: Any = None,
) -> dict[str, Any]:
    async def make_request(jwt: str) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {jwt}",
            "atproto-proxy": f"{_settings.did}#atproto_labeler",
            "atproto-accept-labelers": "did:plc:ar7c4by46qjdydhdevvrndac;redact",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient(timeout=10.0) as client:
            if method == "GET":
                return await client.get(
                    f"https://{_settings.pds}/xrpc/{path}",
                    headers=headers,
                )
            return await client.post(
                f"https://{_settings.pds}/xrpc/{path}",
                headers=headers,
                json=body,
            )

    access_jwt = await _get_access_token()
    response = await make_request(access_jwt)

    if not response.is_success:
        response_body = response.text
        if "ExpiredToken" in response_body:
            access_jwt = await _refresh_session()
            response = await make_request(access_jwt)
            if not response.is_success:
                raise ValueError(f"Ozone API error ({response.status_code}): {response.text}")
        else:
            raise ValueError(f"Ozone API error ({response.status_code}): {response_body}")

    text = response.text
    if text:
        parsed: Any = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    return {}


async def _emit_ozone_event(
    subject: str,
    event: dict[str, Any],
    cid: str | None = None,
    comment: str | None = None,
    batch_id: str | None = None,
) -> str:
    from datetime import datetime, timezone

    config_error = _validate_ozone_config()
    if config_error:
        raise ValueError(config_error)

    subject_ref = _build_subject_ref(subject, cid)

    body = {
        "event": {**event, **({"comment": comment} if comment else {})},
        "subject": subject_ref,
        "createdBy": _settings.did,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "modTool": _build_mod_tool(batch_id),
    }

    result = await _ozone_request("POST", "tools.ozone.moderation.emitEvent", body)
    return json.dumps(result, indent=2)


@mcp.tool()
async def ozone_label(
    subject: str,
    label: str,
    action: str,
    comment: str | None = None,
    cid: str | None = None,
    batch_id: str | None = None,
    duration_in_hours: int | None = None,
) -> str:
    """Apply or remove a moderation label on a subject via the Ozone moderation service."""
    # This tool has custom logic beyond _emit_ozone_event (buildOzoneRequest pattern from TS)
    config_error = _validate_ozone_config()
    if config_error:
        raise ValueError(config_error)

    from datetime import datetime, timezone

    subject_ref = _build_subject_ref(subject, cid)

    event = {
        "$type": "tools.ozone.moderation.defs#modEventLabel",
        **({"comment": comment} if comment else {}),
        "createLabelVals": [label] if action == "apply" else [],
        "negateLabelVals": [label] if action == "remove" else [],
        **({"durationInHours": duration_in_hours} if duration_in_hours is not None else {}),
    }

    body = {
        "event": event,
        "subject": subject_ref,
        "createdBy": _settings.did,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "modTool": _build_mod_tool(batch_id),
    }

    result = await _ozone_request("POST", "tools.ozone.moderation.emitEvent", body)
    response = {
        "success": True,
        "action": action,
        "subject": subject,
        "label": label,
        "response": result,
    }
    return json.dumps(response, indent=2)


@mcp.tool()
async def ozone_comment(
    subject: str,
    comment: str,
    sticky: bool = False,
    cid: str | None = None,
    batch_id: str | None = None,
) -> str:
    """Add a comment to a subject's moderation record. Comments can be pinned to the top of the moderation history."""
    event = {
        "$type": "tools.ozone.moderation.defs#modEventComment",
        **({"sticky": True} if sticky else {}),
    }
    return await _emit_ozone_event(subject, event, cid=cid, comment=comment, batch_id=batch_id)


@mcp.tool()
async def ozone_acknowledge(
    subject: str,
    comment: str | None = None,
    acknowledge_account_subjects: bool = False,
    cid: str | None = None,
    batch_id: str | None = None,
) -> str:
    """Acknowledge a subject, moving it from open to reviewed status."""
    event = {
        "$type": "tools.ozone.moderation.defs#modEventAcknowledge",
        **({"acknowledgeAccountSubjects": True} if acknowledge_account_subjects else {}),
    }
    return await _emit_ozone_event(subject, event, cid=cid, comment=comment, batch_id=batch_id)


@mcp.tool()
async def ozone_escalate(
    subject: str,
    comment: str | None = None,
    cid: str | None = None,
    batch_id: str | None = None,
) -> str:
    """Escalate a subject for higher-level review by the moderation team."""
    event = {"$type": "tools.ozone.moderation.defs#modEventEscalate"}
    return await _emit_ozone_event(subject, event, cid=cid, comment=comment, batch_id=batch_id)


@mcp.tool()
async def ozone_tag(
    subject: str,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    comment: str | None = None,
    cid: str | None = None,
    batch_id: str | None = None,
) -> str:
    """Add and/or remove tags from a subject for categorization and filtering."""
    add = add or []
    remove = remove or []
    if not add and not remove:
        raise ValueError("At least one of 'add' or 'remove' must be non-empty.")
    event = {"$type": "tools.ozone.moderation.defs#modEventTag", "add": add, "remove": remove}
    return await _emit_ozone_event(subject, event, cid=cid, comment=comment, batch_id=batch_id)


@mcp.tool()
async def ozone_mute(
    subject: str,
    duration_in_hours: float,
    comment: str | None = None,
    cid: str | None = None,
    batch_id: str | None = None,
) -> str:
    """Mute a subject to temporarily suppress notifications and queue visibility for a specified duration."""
    event = {
        "$type": "tools.ozone.moderation.defs#modEventMute",
        "durationInHours": duration_in_hours,
    }
    return await _emit_ozone_event(subject, event, cid=cid, comment=comment, batch_id=batch_id)


@mcp.tool()
async def ozone_unmute(
    subject: str,
    comment: str | None = None,
    cid: str | None = None,
    batch_id: str | None = None,
) -> str:
    """Unmute a previously muted subject."""
    event = {"$type": "tools.ozone.moderation.defs#modEventUnmute"}
    return await _emit_ozone_event(subject, event, cid=cid, comment=comment, batch_id=batch_id)


@mcp.tool()
async def ozone_resolve_appeal(
    subject: str,
    comment: str,
    cid: str | None = None,
    batch_id: str | None = None,
) -> str:
    """Resolve an appeal on a subject by providing a required explanation."""
    event = {"$type": "tools.ozone.moderation.defs#modEventResolveAppeal"}
    return await _emit_ozone_event(subject, event, cid=cid, comment=comment, batch_id=batch_id)


@mcp.tool()
async def ozone_query_statuses(
    subject: str | None = None,
    review_state: str | None = None,
    sort_field: str | None = None,
    sort_direction: str | None = None,
    tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    appealed: bool | None = None,
    takendown: bool | None = None,
    limit: int | None = None,
    cursor: str | None = None,
) -> str:
    """Query subject statuses from the Ozone moderation queue with optional filtering and pagination."""
    config_error = _validate_ozone_config()
    if config_error:
        raise ValueError(config_error)

    mapped_review_state = REVIEW_STATE_MAP.get(review_state) if review_state else None

    query_params: dict[str, str | list[str] | None] = {
        "subject": subject,
        "includeAllUserRecords": "true",
        "reviewState": mapped_review_state,
        "sortField": sort_field,
        "sortDirection": sort_direction,
        "tags": tags,
        "excludeTags": exclude_tags,
        "appealed": str(appealed).lower() if appealed is not None else None,
        "takendown": str(takendown).lower() if takendown is not None else None,
        "limit": str(limit) if limit is not None else None,
        "cursor": cursor,
    }

    query_string = _build_query_string(query_params)
    result = await _ozone_request("GET", f"tools.ozone.moderation.queryStatuses{query_string}")
    return json.dumps(result, indent=2)


@mcp.tool()
async def ozone_query_events(
    subject: str | None = None,
    types: list[str] | None = None,
    created_by: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    sort_direction: str | None = None,
    has_comment: bool | None = None,
    added_labels: list[str] | None = None,
    limit: int | None = None,
    cursor: str | None = None,
) -> str:
    """Query moderation events from Ozone with optional filtering and pagination."""
    config_error = _validate_ozone_config()
    if config_error:
        raise ValueError(config_error)

    mapped_types = None
    if types:
        mapped_types = []
        for t in types:
            mapped = EVENT_TYPE_MAP.get(t)
            if not mapped:
                raise ValueError(f"Unknown event type: {t}")
            mapped_types.append(mapped)

    query_params: dict[str, str | list[str] | None] = {
        "subject": subject,
        "types": mapped_types,
        "createdBy": created_by,
        "createdAfter": created_after,
        "createdBefore": created_before,
        "sortDirection": sort_direction,
        "hasComment": str(has_comment).lower() if has_comment is not None else None,
        "addedLabels": added_labels,
        "limit": str(limit) if limit is not None else None,
        "cursor": cursor,
    }

    query_string = _build_query_string(query_params)
    result = await _ozone_request("GET", f"tools.ozone.moderation.queryEvents{query_string}")
    return json.dumps(result, indent=2)

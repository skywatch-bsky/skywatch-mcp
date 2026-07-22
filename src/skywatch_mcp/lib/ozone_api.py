"""
Ozone moderation client — reusable helper for agent-driven moderation operations.

Solves three problems that the copy-paste scripts had:
1. $type key serialization — uses content=json.dumps() internally
2. Session management — cached with auto-refresh on ExpiredToken
3. Acknowledge-after-label — label() and negate() acknowledge atomically

Usage:
    from skywatch_mcp.lib.ozone_api import OzoneClient

    client = OzoneClient()
    await client.label("did:plc:abc", ["troll"], comment="evidence...")
    await client.negate("did:plc:abc", ["spam"], comment="false positive")
    await client.acknowledge("did:plc:abc")
    events = await client.query_events("did:plc:abc")
    statuses = await client.query_statuses(review_state="open", limit=10)
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from skywatch_mcp.config import OzoneSettings

# Constants
LABELER_DID = "did:plc:ar7c4by46qjdydhdevvrndac;redact"
CREATED_BY = "did:plc:e4elbtctnfqocyfcml6h2lf7"  # skywatch.blue

# Event type URIs
_T_LABEL = "tools.ozone.moderation.defs#modEventLabel"
_T_COMMENT = "tools.ozone.moderation.defs#modEventComment"
_T_ACK = "tools.ozone.moderation.defs#modEventAcknowledge"
_T_ESCALATE = "tools.ozone.moderation.defs#modEventEscalate"
_T_TAG = "tools.ozone.moderation.defs#modEventTag"
_T_MUTE = "tools.ozone.moderation.defs#modEventMute"
_T_UNMUTE = "tools.ozone.moderation.defs#modEventUnmute"


class OzoneClient:
    """Reusable Ozone moderation client with session caching and atomic operations."""

    def __init__(self, settings: OzoneSettings | None = None):
        self._settings = settings or OzoneSettings()
        self._cached_session: dict[str, str] | None = None

    # ---- Session management ----

    async def _create_session(self) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"https://{self._settings.pds}/xrpc/com.atproto.server.createSession",
                json={
                    "identifier": self._settings.handle,
                    "password": self._settings.admin_password,
                },
            )
            if resp.status_code != 200:
                raise ValueError(f"Session failed ({resp.status_code}): {resp.text}")
            session = resp.json()
            self._cached_session = {
                "accessJwt": session["accessJwt"],
                "refreshJwt": session["refreshJwt"],
            }
            return str(session["accessJwt"])

    async def _refresh_session(self) -> str:
        if not self._cached_session:
            return await self._create_session()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"https://{self._settings.pds}/xrpc/com.atproto.server.refreshSession",
                headers={"Authorization": f"Bearer {self._cached_session['refreshJwt']}"},
            )
            if resp.status_code != 200:
                self._cached_session = None
                return await self._create_session()
            session = resp.json()
            self._cached_session = {
                "accessJwt": session["accessJwt"],
                "refreshJwt": session["refreshJwt"],
            }
            return str(session["accessJwt"])

    async def _get_jwt(self) -> str:
        if self._cached_session:
            return self._cached_session["accessJwt"]
        return await self._create_session()

    # ---- Core request helper ----

    async def _request(
        self, method: str, path: str, body: Any = None
    ) -> dict[str, Any]:
        jwt = await self._get_jwt()

        def build_headers(jwt: str) -> dict[str, str]:
            h = {
                "Authorization": f"Bearer {jwt}",
                "atproto-proxy": f"{self._settings.did}#atproto_labeler",
                "atproto-accept-labelers": LABELER_DID,
            }
            if body is not None:
                h["Content-Type"] = "application/json"
            return h

        url = f"https://{self._settings.pds}/xrpc/{path}"

        # Use content= with pre-serialized JSON to avoid $type key issues
        if method == "GET":
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers=build_headers(jwt), params=body)
        else:
            content = json.dumps(body) if body else None
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=build_headers(jwt), content=content)

        if not resp.is_success:
            if "ExpiredToken" in resp.text:
                jwt = await self._refresh_session()
                if method == "GET":
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.get(
                            url, headers=build_headers(jwt), params=body
                        )
                else:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.post(
                            url, headers=build_headers(jwt), content=content
                        )
                if not resp.is_success:
                    raise ValueError(f"Ozone API error ({resp.status_code}): {resp.text}")
            else:
                raise ValueError(f"Ozone API error ({resp.status_code}): {resp.text}")

        text = resp.text
        if text:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        return {}

    # ---- Subject helpers ----

    @staticmethod
    def _subject_ref(subject: str, cid: str | None = None) -> dict[str, str]:
        if subject.startswith("did:"):
            return {"$type": "com.atproto.admin.defs#repoRef", "did": subject}
        if subject.startswith("at://"):
            if not cid:
                raise ValueError(
                    "AT-URI subjects require a cid parameter."
                )
            return {"$type": "com.atproto.repo.strongRef", "uri": subject, "cid": cid}
        raise ValueError(f"Subject must be a DID or AT-URI. Got: {subject}")

    @staticmethod
    def _mod_tool(batch_id: str | None = None) -> dict[str, Any]:
        return {
            "name": "skywatch-mcp",
            "meta": {
                "time": datetime.now(timezone.utc).isoformat(),
                "batchId": batch_id or str(uuid.uuid4()),
            },
        }

    async def _emit(
        self,
        subject: str,
        event: dict[str, Any],
        cid: str | None = None,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "event": event,
            "subject": self._subject_ref(subject, cid),
            "createdBy": self._settings.did,
            "modTool": self._mod_tool(batch_id),
        }
        return await self._request("POST", "tools.ozone.moderation.emitEvent", body)

    # ---- Public API ----

    async def label(
        self,
        subject: str,
        labels: list[str],
        comment: str | None = None,
        cid: str | None = None,
        acknowledge: bool = True,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Apply labels atomically: label + evidence comment + acknowledge in one call.

        Args:
            subject: DID or AT-URI
            labels: List of label strings to apply (e.g. ["troll"], ["spam", "inauthentic-fundraising"])
            comment: Evidence comment (non-sticky by default)
            cid: Required for AT-URI subjects
            acknowledge: If True (default), acknowledges the subject after labeling
            batch_id: Optional batch UUID

        Returns:
            Dict with status of each operation: {"label": ..., "comment": ..., "acknowledge": ...}
        """
        results = {}

        # 1. Apply label
        label_event = {
            "$type": _T_LABEL,
            "createLabelVals": labels,
            "negateLabelVals": [],
        }
        results["label"] = await self._emit(subject, label_event, cid, batch_id)

        # 2. Evidence comment (non-sticky)
        if comment:
            comment_event = {"$type": _T_COMMENT, "comment": comment, "sticky": False}
            results["comment"] = await self._emit(subject, comment_event, cid, batch_id)

        # 3. Acknowledge (close the report)
        if acknowledge:
            ack_event = {
                "$type": _T_ACK,
                "acknowledgeAccountSubjects": subject.startswith("did:"),
            }
            results["acknowledge"] = await self._emit(subject, ack_event, cid, batch_id)

        return results

    async def negate(
        self,
        subject: str,
        labels: list[str],
        comment: str | None = None,
        cid: str | None = None,
        acknowledge: bool = True,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Remove labels atomically: negate + comment + acknowledge in one call.

        Args:
            subject: DID or AT-URI
            labels: List of label strings to remove
            comment: Reason for removal (non-sticky)
            cid: Required for AT-URI subjects
            acknowledge: If True (default), acknowledges after negating
            batch_id: Optional batch UUID
        """
        results = {}

        negate_event = {
            "$type": _T_LABEL,
            "createLabelVals": [],
            "negateLabelVals": labels,
        }
        results["negate"] = await self._emit(subject, negate_event, cid, batch_id)

        if comment:
            comment_event = {"$type": _T_COMMENT, "comment": comment, "sticky": False}
            results["comment"] = await self._emit(subject, comment_event, cid, batch_id)

        if acknowledge:
            ack_event = {
                "$type": _T_ACK,
                "acknowledgeAccountSubjects": subject.startswith("did:"),
            }
            results["acknowledge"] = await self._emit(subject, ack_event, cid, batch_id)

        return results

    async def acknowledge(
        self,
        subject: str,
        comment: str | None = None,
        cid: str | None = None,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        """Acknowledge a subject, closing its open reports."""
        event = {
            "$type": _T_ACK,
            "acknowledgeAccountSubjects": subject.startswith("did:"),
        }
        if comment:
            event["comment"] = comment
        return await self._emit(subject, event, cid, batch_id)

    async def comment(
        self,
        subject: str,
        text: str,
        sticky: bool = False,
        cid: str | None = None,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        """Add a comment to a subject's moderation record."""
        event = {"$type": _T_COMMENT, "comment": text, "sticky": sticky}
        return await self._emit(subject, event, cid, batch_id)

    async def escalate(
        self,
        subject: str,
        comment: str | None = None,
        cid: str | None = None,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        """Escalate a subject for higher-level review."""
        event = {"$type": _T_ESCALATE}
        if comment:
            event["comment"] = comment
        return await self._emit(subject, event, cid, batch_id)

    async def tag(
        self,
        subject: str,
        add: list[str] | None = None,
        remove: list[str] | None = None,
        cid: str | None = None,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        """Add or remove tags from a subject."""
        add = add or []
        remove = remove or []
        if not add and not remove:
            raise ValueError("At least one of 'add' or 'remove' must be non-empty.")
        event = {"$type": _T_TAG, "add": add, "remove": remove}
        return await self._emit(subject, event, cid, batch_id)

    async def query_events(
        self, subject: str, limit: int = 20, sort_direction: str = "desc"
    ) -> list[dict[str, Any]]:
        """Query moderation event history for a subject."""
        params = {
            "subject": subject,
            "sort_direction": sort_direction,
            "limit": limit,
        }
        result = await self._request("GET", "tools.ozone.moderation.queryEvents", params)
        return list(result.get("events", []))

    async def query_statuses(
        self,
        review_state: str | None = None,
        sort_field: str = "lastReportedAt",
        sort_direction: str = "desc",
        limit: int = 50,
        tags: list[str] | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """
        Query the moderation queue.

        Args:
            review_state: 'open', 'escalated', 'closed', 'none', or None for all
            sort_field: Field to sort by
            sort_direction: 'asc' or 'desc'
            limit: Max results
            tags: Filter by tags
            cursor: Pagination cursor

        Returns:
            Dict with 'subjectStatuses' list and 'cursor'
        """
        params: dict[str, Any] = {
            "sort_field": sort_field,
            "sort_direction": sort_direction,
            "limit": limit,
        }
        if review_state:
            state_map = {
                "open": "tools.ozone.moderation.defs#reviewOpen",
                "escalated": "tools.ozone.moderation.defs#reviewEscalated",
                "closed": "tools.ozone.moderation.defs#reviewClosed",
                "none": "tools.ozone.moderation.defs#reviewNone",
            }
            params["review_state"] = state_map.get(review_state, review_state)
        if tags:
            for tag in tags:
                params.setdefault("tags", []).append(tag) if isinstance(
                    params.get("tags"), list
                ) else None
        if cursor:
            params["cursor"] = cursor

        return await self._request("GET", "tools.ozone.moderation.queryStatuses", params)

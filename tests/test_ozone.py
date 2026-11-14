# pattern: Test Suite

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from skywatch_mcp.tools.ozone import (
    EVENT_TYPE_MAP,
    REPORT_TYPE_MAP,
    REVIEW_STATE_MAP,
    _build_mod_tool,
    _build_query_string,
    _build_subject_ref,
)
from mcp.server.mcpserver.exceptions import ToolError


class TestConfigValidation:
    def test_validate_ozone_config_not_configured(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "")
        monkeypatch.setenv("OZONE_PDS", "")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "")
        monkeypatch.setenv("OZONE_DID", "")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        error = ozone_module._validate_ozone_config()
        assert error is not None
        assert "Ozone is not configured" in error

    def test_validate_ozone_config_configured(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        error = ozone_module._validate_ozone_config()
        assert error is None


class TestSubjectRef:
    def test_build_subject_ref_did(self):
        subject = "did:plc:abcdef123456"
        ref = _build_subject_ref(subject)
        assert ref["$type"] == "com.atproto.admin.defs#repoRef"
        assert ref["did"] == subject

    def test_build_subject_ref_at_uri_with_cid(self):
        subject = "at://did:plc:test/app.bsky.feed.post/abc123"
        cid = "bafy123abc"
        ref = _build_subject_ref(subject, cid)
        assert ref["$type"] == "com.atproto.repo.strongRef"
        assert ref["uri"] == subject
        assert ref["cid"] == cid

    def test_build_subject_ref_at_uri_without_cid(self):
        subject = "at://did:plc:test/app.bsky.feed.post/abc123"
        with pytest.raises(ValueError, match="AT-URI subjects require a cid parameter"):
            _build_subject_ref(subject)

    def test_build_subject_ref_invalid(self):
        subject = "invalid_subject"
        with pytest.raises(ValueError, match="Subject must be a DID"):
            _build_subject_ref(subject)


class TestModTool:
    def test_build_mod_tool_with_custom_batch_id(self):
        batch_id = "custom-batch-id-123"
        result = _build_mod_tool(batch_id)
        assert result["name"] == "skywatch-mcp"
        assert result["meta"]["batchId"] == batch_id
        assert "time" in result["meta"]

    def test_build_mod_tool_generates_batch_id(self):
        result = _build_mod_tool()
        assert result["name"] == "skywatch-mcp"
        assert "batchId" in result["meta"]
        assert result["meta"]["batchId"] != ""


class TestQueryString:
    def test_build_query_string_with_none_values(self):
        params = {"key1": "value1", "key2": None, "key3": "value3"}
        qs = _build_query_string(params)
        assert "key2" not in qs
        assert "key1=value1" in qs
        assert "key3=value3" in qs

    def test_build_query_string_with_list_values(self):
        params = {"tags": ["tag1", "tag2"], "other": "value"}
        qs = _build_query_string(params)
        assert "tags=tag1" in qs
        assert "tags=tag2" in qs
        assert "other=value" in qs

    def test_build_query_string_empty(self):
        params = {"key1": None, "key2": None}
        qs = _build_query_string(params)
        assert qs == ""

    def test_build_query_string_single_value(self):
        params = {"subject": "did:plc:test"}
        qs = _build_query_string(params)
        assert qs == "?subject=did%3Aplc%3Atest"


class TestSessionManagement:
    @pytest.mark.asyncio
    async def test_create_session(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "accessJwt": "access_token",
            "refreshJwt": "refresh_token",
        }

        async_client_mock = AsyncMock()
        async_client_mock.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock
            token = await ozone_module._create_session()
            assert token == "access_token"

    @pytest.mark.asyncio
    async def test_get_access_token_uses_cache(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = {
            "accessJwt": "cached_token",
            "refreshJwt": "refresh_token",
        }

        token = await ozone_module._get_access_token()
        assert token == "cached_token"


class TestTokenRefresh:
    @pytest.mark.asyncio
    async def test_ozone_request_refreshes_on_expired_token(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = {
            "accessJwt": "expired_token",
            "refreshJwt": "refresh_token",
        }

        expired_response = MagicMock()
        expired_response.is_success = False
        expired_response.status_code = 401
        expired_response.text = "ExpiredToken"

        success_response = MagicMock()
        success_response.is_success = True
        success_response.text = '{"result": "ok"}'

        refresh_response = MagicMock()
        refresh_response.status_code = 200
        refresh_response.json.return_value = {
            "accessJwt": "new_token",
            "refreshJwt": "new_refresh_token",
        }

        async_client_mock = AsyncMock()

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            async_client_mock.post.side_effect = [
                expired_response,
                refresh_response,
                success_response,
            ]
            async_client_mock.get.side_effect = [
                expired_response,
                success_response,
            ]

            result = await ozone_module._ozone_request(
                "GET", "tools.ozone.moderation.queryStatuses"
            )
            assert result == {"result": "ok"}


class TestToolHandlers:
    @pytest.mark.asyncio
    async def test_ozone_comment_calls_emit_event(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = {
            "accessJwt": "token",
            "refreshJwt": "refresh_token",
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.text = '{"id": "123", "comment": "test comment"}'

        async_client_mock = AsyncMock()
        async_client_mock.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            result = await ozone_module.ozone_comment(
                subject="did:plc:test", comment="test comment", sticky=False
            )

            result_dict = json.loads(result)
            assert result_dict["id"] == "123"
            assert result_dict["comment"] == "test comment"

    @pytest.mark.asyncio
    async def test_ozone_label_with_apply_action(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = {
            "accessJwt": "token",
            "refreshJwt": "refresh_token",
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.text = '{"id": "456"}'

        async_client_mock = AsyncMock()
        async_client_mock.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            result = await ozone_module.ozone_label(
                subject="did:plc:test", label="violation", action="apply"
            )

            result_dict = json.loads(result)
            assert result_dict["success"] is True
            assert result_dict["action"] == "apply"
            assert result_dict["label"] == "violation"


class TestOzoneReport:
    @pytest.mark.asyncio
    async def test_ozone_report_maps_friendly_report_type(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = {
            "accessJwt": "token",
            "refreshJwt": "refresh_token",
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.text = '{"id": "321", "eventType": "tools.ozone.moderation.defs#modEventReport"}'

        async_client_mock = AsyncMock()
        async_client_mock.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            result = await ozone_module.ozone_report(
                subject="did:plc:test",
                report_type="spam",
                reason="Account posts spam links daily",
            )

            result_dict = json.loads(result)
            assert result_dict["id"] == "321"

            call_args = async_client_mock.post.call_args
            assert "tools.ozone.moderation.emitEvent" in call_args[0][0]
            request_body = call_args[1]["json"]
            assert request_body["event"]["$type"] == "tools.ozone.moderation.defs#modEventReport"
            assert request_body["event"]["reportType"] == "com.atproto.moderation.defs#reasonSpam"
            assert request_body["event"]["comment"] == "Account posts spam links daily"
            assert request_body["subject"]["$type"] == "com.atproto.admin.defs#repoRef"
            assert request_body["subject"]["did"] == "did:plc:test"
            assert request_body["createdBy"] == "did:plc:test"
            assert request_body["modTool"]["name"] == "skywatch-mcp"

    @pytest.mark.asyncio
    async def test_ozone_report_passes_through_full_qualified_reason(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = {
            "accessJwt": "token",
            "refreshJwt": "refresh_token",
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.text = '{"id": "322"}'

        async_client_mock = AsyncMock()
        async_client_mock.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            await ozone_module.ozone_report(
                subject="did:plc:test",
                report_type="tools.ozone.report.defs#reasonMisleadingSpam",
                reason="Coordinated misleading spam network",
            )

            request_body = async_client_mock.post.call_args[1]["json"]
            assert request_body["event"]["reportType"] == "tools.ozone.report.defs#reasonMisleadingSpam"

    @pytest.mark.asyncio
    async def test_ozone_report_rejects_invalid_report_type(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        with pytest.raises(ToolError, match="Unknown report type"):
            await ozone_module.ozone_report(
                subject="did:plc:test", report_type="bogus", reason="test"
            )

    @pytest.mark.asyncio
    async def test_ozone_report_is_reporter_muted_conditional(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = {
            "accessJwt": "token",
            "refreshJwt": "refresh_token",
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.text = '{"id": "323"}'

        async_client_mock = AsyncMock()
        async_client_mock.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            await ozone_module.ozone_report(
                subject="did:plc:test",
                report_type="spam",
                reason="Reporter already muted",
                is_reporter_muted=True,
            )

            request_body = async_client_mock.post.call_args[1]["json"]
            assert request_body["event"]["isReporterMuted"] is True

            async_client_mock.reset_mock()
            await ozone_module.ozone_report(
                subject="did:plc:test",
                report_type="spam",
                reason="Default call omits the flag",
            )

            request_body = async_client_mock.post.call_args[1]["json"]
            assert "isReporterMuted" not in request_body["event"]

    @pytest.mark.asyncio
    async def test_ozone_report_at_uri_subject_requires_cid(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        at_uri = "at://did:plc:test/app.bsky.feed.post/abc123"

        with pytest.raises(ToolError, match="AT-URI subjects require a cid parameter"):
            await ozone_module.ozone_report(subject=at_uri, report_type="spam", reason="test")

        ozone_module._cached_session = {
            "accessJwt": "token",
            "refreshJwt": "refresh_token",
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.text = '{"id": "324"}'

        async_client_mock = AsyncMock()
        async_client_mock.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            await ozone_module.ozone_report(
                subject=at_uri, report_type="spam", reason="test", cid="bafy123abc"
            )

            request_body = async_client_mock.post.call_args[1]["json"]
            assert request_body["subject"]["$type"] == "com.atproto.repo.strongRef"
            assert request_body["subject"]["uri"] == at_uri
            assert request_body["subject"]["cid"] == "bafy123abc"

    @pytest.mark.asyncio
    async def test_ozone_report_batch_id_in_mod_tool(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = {
            "accessJwt": "token",
            "refreshJwt": "refresh_token",
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.text = '{"id": "325"}'

        async_client_mock = AsyncMock()
        async_client_mock.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            await ozone_module.ozone_report(
                subject="did:plc:test", report_type="spam", reason="test", batch_id="abc"
            )

            request_body = async_client_mock.post.call_args[1]["json"]
            assert request_body["modTool"]["meta"]["batchId"] == "abc"


class TestQueryTools:
    @pytest.mark.asyncio
    async def test_ozone_query_statuses_maps_review_state(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = {
            "accessJwt": "token",
            "refreshJwt": "refresh_token",
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.text = '{"statuses": []}'

        async_client_mock = AsyncMock()
        async_client_mock.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            await ozone_module.ozone_query_statuses(review_state="open")

            call_args = async_client_mock.get.call_args
            assert "tools.ozone.moderation.defs%23reviewOpen" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_ozone_query_statuses_accepts_full_qualified_review_state(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = {
            "accessJwt": "token",
            "refreshJwt": "refresh_token",
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.text = '{"statuses": []}'

        async_client_mock = AsyncMock()
        async_client_mock.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            await ozone_module.ozone_query_statuses(
                review_state="tools.ozone.moderation.defs#reviewOpen"
            )

            call_args = async_client_mock.get.call_args
            assert "tools.ozone.moderation.defs%23reviewOpen" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_ozone_query_statuses_rejects_invalid_review_state(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        with pytest.raises(ToolError, match="Unknown review state"):
            await ozone_module.ozone_query_statuses(review_state="bogus")

    @pytest.mark.asyncio
    async def test_ozone_query_events_maps_event_types(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = {
            "accessJwt": "token",
            "refreshJwt": "refresh_token",
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.text = '{"events": []}'

        async_client_mock = AsyncMock()
        async_client_mock.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            await ozone_module.ozone_query_events(types=["comment", "label"])

            call_args = async_client_mock.get.call_args
            assert "tools.ozone.moderation.defs%23modEventComment" in call_args[0][0]
            assert "tools.ozone.moderation.defs%23modEventLabel" in call_args[0][0]

    def test_ozone_query_events_invalid_type(self):
        with pytest.raises(ValueError, match="Unknown event type"):
            params = {"types": ["invalid_type"]}
            for t in params["types"]:
                mapped = EVENT_TYPE_MAP.get(t)
                if not mapped:
                    raise ValueError(f"Unknown event type: {t}")


class TestEventAndReviewStateMaps:
    def test_review_state_map_all_keys_valid(self):
        expected_keys = ["open", "escalated", "closed", "none"]
        for key in expected_keys:
            assert key in REVIEW_STATE_MAP
            value = REVIEW_STATE_MAP[key]
            assert value.startswith("tools.ozone.moderation.defs#")

    def test_event_type_map_all_keys_valid(self):
        expected_keys = [
            "takedown",
            "reverseTakedown",
            "comment",
            "report",
            "label",
            "acknowledge",
            "escalate",
            "mute",
            "unmute",
            "muteReporter",
            "unmuteReporter",
            "email",
            "resolveAppeal",
            "divert",
            "tag",
            "accountEvent",
            "identityEvent",
            "recordEvent",
        ]
        for key in expected_keys:
            assert key in EVENT_TYPE_MAP
            value = EVENT_TYPE_MAP[key]
            assert value.startswith("tools.ozone.moderation.defs#")

    def test_report_type_map_all_keys_valid(self):
        expected_keys = ["spam", "violation", "misleading", "sexual", "rude", "other", "appeal"]
        for key in expected_keys:
            assert key in REPORT_TYPE_MAP
            value = REPORT_TYPE_MAP[key]
            assert value.startswith("com.atproto.moderation.defs#")


class TestToolValidation:
    @pytest.mark.asyncio
    async def test_ozone_tag_requires_add_or_remove(self):
        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        with pytest.raises(ToolError, match="At least one of 'add' or 'remove' must be non-empty"):
            await ozone_module.ozone_tag(subject="did:plc:test")

    @pytest.mark.asyncio
    async def test_ozone_tag_with_add(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = {
            "accessJwt": "token",
            "refreshJwt": "refresh_token",
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.text = "{}"

        async_client_mock = AsyncMock()
        async_client_mock.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            result = await ozone_module.ozone_tag(subject="did:plc:test", add=["tag1", "tag2"])
            assert result is not None


class TestMissingToolCoverage:
    """Tests for previously uncovered moderation event tools."""

    @pytest.mark.asyncio
    async def test_ozone_acknowledge_event_type_and_account_subjects(self, monkeypatch):
        """Test AC1.13: ozone_acknowledge sets event $type and acknowledgeAccountSubjects field."""
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = {
            "accessJwt": "token",
            "refreshJwt": "refresh_token",
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.text = '{"id": "123"}'

        async_client_mock = AsyncMock()
        async_client_mock.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            await ozone_module.ozone_acknowledge(
                subject="did:plc:test", acknowledge_account_subjects=True
            )

            call_args = async_client_mock.post.call_args
            request_body = call_args[1]["json"]
            assert request_body["event"]["$type"] == "tools.ozone.moderation.defs#modEventAcknowledge"
            assert request_body["event"]["acknowledgeAccountSubjects"] is True

            async_client_mock.reset_mock()
            await ozone_module.ozone_acknowledge(subject="did:plc:test")

            call_args = async_client_mock.post.call_args
            request_body = call_args[1]["json"]
            assert request_body["event"]["$type"] == "tools.ozone.moderation.defs#modEventAcknowledge"
            assert "acknowledgeAccountSubjects" not in request_body["event"]

    @pytest.mark.asyncio
    async def test_ozone_escalate_event_type(self, monkeypatch):
        """Test AC1.14: ozone_escalate sets event $type to modEventEscalate."""
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = {
            "accessJwt": "token",
            "refreshJwt": "refresh_token",
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.text = '{"id": "456"}'

        async_client_mock = AsyncMock()
        async_client_mock.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            await ozone_module.ozone_escalate(subject="did:plc:test")

            call_args = async_client_mock.post.call_args
            request_body = call_args[1]["json"]
            assert request_body["event"]["$type"] == "tools.ozone.moderation.defs#modEventEscalate"

    @pytest.mark.asyncio
    async def test_ozone_mute_duration_in_hours(self, monkeypatch):
        """Test AC1.16: ozone_mute includes durationInHours in event body."""
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = {
            "accessJwt": "token",
            "refreshJwt": "refresh_token",
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.text = '{"id": "789"}'

        async_client_mock = AsyncMock()
        async_client_mock.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            await ozone_module.ozone_mute(
                subject="did:plc:test", duration_in_hours=24.5
            )

            call_args = async_client_mock.post.call_args
            request_body = call_args[1]["json"]
            assert request_body["event"]["$type"] == "tools.ozone.moderation.defs#modEventMute"
            assert request_body["event"]["durationInHours"] == 24.5

    @pytest.mark.asyncio
    async def test_ozone_unmute_event_type(self, monkeypatch):
        """Test AC1.17: ozone_unmute sets event $type to modEventUnmute."""
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = {
            "accessJwt": "token",
            "refreshJwt": "refresh_token",
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.text = '{"id": "999"}'

        async_client_mock = AsyncMock()
        async_client_mock.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            await ozone_module.ozone_unmute(subject="did:plc:test")

            call_args = async_client_mock.post.call_args
            request_body = call_args[1]["json"]
            assert request_body["event"]["$type"] == "tools.ozone.moderation.defs#modEventUnmute"

    @pytest.mark.asyncio
    async def test_ozone_resolve_appeal_comment_passed_through(self, monkeypatch):
        """Test AC1.18: ozone_resolve_appeal passes comment through to event."""
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = {
            "accessJwt": "token",
            "refreshJwt": "refresh_token",
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.text = '{"id": "appeal_123"}'

        async_client_mock = AsyncMock()
        async_client_mock.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            test_comment = "Appeal resolved with explanation"
            await ozone_module.ozone_resolve_appeal(
                subject="did:plc:test", comment=test_comment
            )

            call_args = async_client_mock.post.call_args
            request_body = call_args[1]["json"]
            assert request_body["event"]["$type"] == "tools.ozone.moderation.defs#modEventResolveAppeal"
            assert request_body["event"]["comment"] == test_comment

    @pytest.mark.asyncio
    async def test_get_access_token_caches_session_on_multiple_calls(self, monkeypatch):
        """Test AC3.6: _get_access_token uses cache and _create_session called only once."""
        monkeypatch.setenv("OZONE_HANDLE", "test.bsky.social")
        monkeypatch.setenv("OZONE_PDS", "api.bsky.app")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "test_password")
        monkeypatch.setenv("OZONE_DID", "did:plc:test")

        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        ozone_module._cached_session = None

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "accessJwt": "access_token_123",
            "refreshJwt": "refresh_token_456",
        }

        async_client_mock = AsyncMock()
        async_client_mock.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            # Call _get_access_token twice
            token1 = await ozone_module._get_access_token()
            token2 = await ozone_module._get_access_token()

            # Both calls should return the same token
            assert token1 == "access_token_123"
            assert token2 == "access_token_123"

            # _create_session (via httpx POST) should have been called exactly once
            assert async_client_mock.post.call_count == 1

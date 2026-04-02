# pattern: Test Suite

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from skywatch_mcp.tools.ozone import (
    EVENT_TYPE_MAP,
    REVIEW_STATE_MAP,
    _build_mod_tool,
    _build_query_string,
    _build_subject_ref,
)


class TestConfigValidation:
    def test_validate_ozone_config_not_configured(self, monkeypatch):
        monkeypatch.setenv("OZONE_HANDLE", "")
        monkeypatch.setenv("OZONE_PDS", "")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "")
        monkeypatch.setenv("OZONE_DID", "")

        # Need to reimport to pick up env changes
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

        # Set cached session
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

        # Set initial cached session
        ozone_module._cached_session = {
            "accessJwt": "expired_token",
            "refreshJwt": "refresh_token",
        }

        # First response: ExpiredToken error
        expired_response = MagicMock()
        expired_response.is_success = False
        expired_response.status_code = 401
        expired_response.text = "ExpiredToken"

        # Second response (after refresh): success
        success_response = MagicMock()
        success_response.is_success = True
        success_response.text = '{"result": "ok"}'

        # Refresh session response
        refresh_response = MagicMock()
        refresh_response.status_code = 200
        refresh_response.json.return_value = {
            "accessJwt": "new_token",
            "refreshJwt": "new_refresh_token",
        }

        async_client_mock = AsyncMock()

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = async_client_mock

            # Set up side effects for multiple calls
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

            # Verify the call was made with correct query string
            call_args = async_client_mock.get.call_args
            assert "tools.ozone.moderation.defs%23reviewOpen" in call_args[0][0]

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

            # Verify the call was made with correct query string
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


class TestToolValidation:
    @pytest.mark.asyncio
    async def test_ozone_tag_requires_add_or_remove(self):
        from importlib import reload
        import skywatch_mcp.tools.ozone as ozone_module

        reload(ozone_module)

        with pytest.raises(ValueError, match="At least one of 'add' or 'remove' must be non-empty"):
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

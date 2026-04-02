"""Tests for configuration loading (AC5.1, AC5.2)."""

from __future__ import annotations

from _pytest.monkeypatch import MonkeyPatch


class TestClickHouseSettings:
    """ClickHouse configuration loading and defaults."""

    def test_default_host(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.2: Default host is http://localhost."""
        monkeypatch.delenv("CLICKHOUSE_HOST", raising=False)
        from skywatch_mcp.config import ClickHouseSettings

        ch = ClickHouseSettings()
        assert ch.host == "http://localhost"

    def test_default_port(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.2: Default port is 8123."""
        monkeypatch.delenv("CLICKHOUSE_PORT", raising=False)
        from skywatch_mcp.config import ClickHouseSettings

        ch = ClickHouseSettings()
        assert ch.port == 8123

    def test_default_user(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.2: Default user is 'default'."""
        monkeypatch.delenv("CLICKHOUSE_USER", raising=False)
        from skywatch_mcp.config import ClickHouseSettings

        ch = ClickHouseSettings()
        assert ch.user == "default"

    def test_default_password(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.2: Default password is empty string."""
        monkeypatch.delenv("CLICKHOUSE_PASSWORD", raising=False)
        from skywatch_mcp.config import ClickHouseSettings

        ch = ClickHouseSettings()
        assert ch.password == ""

    def test_default_database(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.2: Default database is 'default'."""
        monkeypatch.delenv("CLICKHOUSE_DATABASE", raising=False)
        from skywatch_mcp.config import ClickHouseSettings

        ch = ClickHouseSettings()
        assert ch.database == "default"

    def test_read_host_from_env(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.1: Read CLICKHOUSE_HOST from environment."""
        monkeypatch.setenv("CLICKHOUSE_HOST", "http://192.168.1.1")
        from skywatch_mcp.config import ClickHouseSettings

        ch = ClickHouseSettings()
        assert ch.host == "http://192.168.1.1"

    def test_read_port_from_env(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.1: Read CLICKHOUSE_PORT from environment as int."""
        monkeypatch.setenv("CLICKHOUSE_PORT", "9000")
        from skywatch_mcp.config import ClickHouseSettings

        ch = ClickHouseSettings()
        assert ch.port == 9000

    def test_read_user_from_env(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.1: Read CLICKHOUSE_USER from environment."""
        monkeypatch.setenv("CLICKHOUSE_USER", "admin")
        from skywatch_mcp.config import ClickHouseSettings

        ch = ClickHouseSettings()
        assert ch.user == "admin"

    def test_read_password_from_env(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.1: Read CLICKHOUSE_PASSWORD from environment."""
        monkeypatch.setenv("CLICKHOUSE_PASSWORD", "secret123")
        from skywatch_mcp.config import ClickHouseSettings

        ch = ClickHouseSettings()
        assert ch.password == "secret123"

    def test_read_database_from_env(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.1: Read CLICKHOUSE_DATABASE from environment."""
        monkeypatch.setenv("CLICKHOUSE_DATABASE", "skywatch")
        from skywatch_mcp.config import ClickHouseSettings

        ch = ClickHouseSettings()
        assert ch.database == "skywatch"

    def test_tailnet_ip_none_by_default(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.2: CLICKHOUSE_TAILNET_IP defaults to None."""
        monkeypatch.delenv("CLICKHOUSE_TAILNET_IP", raising=False)
        from skywatch_mcp.config import ClickHouseSettings

        ch = ClickHouseSettings()
        assert ch.tailnet_ip is None

    def test_read_tailnet_ip_from_env(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.1: Read CLICKHOUSE_TAILNET_IP from environment."""
        monkeypatch.setenv("CLICKHOUSE_TAILNET_IP", "100.64.0.1")
        from skywatch_mcp.config import ClickHouseSettings

        ch = ClickHouseSettings()
        assert ch.tailnet_ip == "100.64.0.1"

    def test_effective_host_without_tailnet_ip(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.1: effective_host returns host when tailnet_ip is None."""
        monkeypatch.setenv("CLICKHOUSE_HOST", "http://192.168.1.1")
        monkeypatch.delenv("CLICKHOUSE_TAILNET_IP", raising=False)
        from skywatch_mcp.config import ClickHouseSettings

        ch = ClickHouseSettings()
        assert ch.effective_host == "http://192.168.1.1"

    def test_effective_host_with_tailnet_ip_overrides(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.1: effective_host returns tailnet_ip-based host when set."""
        monkeypatch.setenv("CLICKHOUSE_HOST", "http://192.168.1.1")
        monkeypatch.setenv("CLICKHOUSE_TAILNET_IP", "100.64.0.1")
        from skywatch_mcp.config import ClickHouseSettings

        ch = ClickHouseSettings()
        assert ch.effective_host == "http://100.64.0.1"


class TestOzoneSettings:
    """Ozone configuration loading and defaults."""

    def test_default_service_url_none(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.2: OZONE_SERVICE_URL defaults to None."""
        monkeypatch.delenv("OZONE_SERVICE_URL", raising=False)
        from skywatch_mcp.config import OzoneSettings

        oz = OzoneSettings()
        assert oz.service_url is None

    def test_default_handle_none(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.2: OZONE_HANDLE defaults to None."""
        monkeypatch.delenv("OZONE_HANDLE", raising=False)
        from skywatch_mcp.config import OzoneSettings

        oz = OzoneSettings()
        assert oz.handle is None

    def test_default_admin_password_none(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.2: OZONE_ADMIN_PASSWORD defaults to None."""
        monkeypatch.delenv("OZONE_ADMIN_PASSWORD", raising=False)
        from skywatch_mcp.config import OzoneSettings

        oz = OzoneSettings()
        assert oz.admin_password is None

    def test_default_did_none(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.2: OZONE_DID defaults to None."""
        monkeypatch.delenv("OZONE_DID", raising=False)
        from skywatch_mcp.config import OzoneSettings

        oz = OzoneSettings()
        assert oz.did is None

    def test_default_pds_none(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.2: OZONE_PDS defaults to None."""
        monkeypatch.delenv("OZONE_PDS", raising=False)
        from skywatch_mcp.config import OzoneSettings

        oz = OzoneSettings()
        assert oz.pds is None

    def test_read_service_url_from_env(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.1: Read OZONE_SERVICE_URL from environment."""
        monkeypatch.setenv("OZONE_SERVICE_URL", "https://mod.service.local")
        from skywatch_mcp.config import OzoneSettings

        oz = OzoneSettings()
        assert oz.service_url == "https://mod.service.local"

    def test_read_handle_from_env(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.1: Read OZONE_HANDLE from environment."""
        monkeypatch.setenv("OZONE_HANDLE", "admin")
        from skywatch_mcp.config import OzoneSettings

        oz = OzoneSettings()
        assert oz.handle == "admin"

    def test_read_admin_password_from_env(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.1: Read OZONE_ADMIN_PASSWORD from environment."""
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "modpass123")
        from skywatch_mcp.config import OzoneSettings

        oz = OzoneSettings()
        assert oz.admin_password == "modpass123"

    def test_read_did_from_env(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.1: Read OZONE_DID from environment."""
        monkeypatch.setenv("OZONE_DID", "did:plc:test1234")
        from skywatch_mcp.config import OzoneSettings

        oz = OzoneSettings()
        assert oz.did == "did:plc:test1234"

    def test_read_pds_from_env(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.1: Read OZONE_PDS from environment."""
        monkeypatch.setenv("OZONE_PDS", "https://bsky.social")
        from skywatch_mcp.config import OzoneSettings

        oz = OzoneSettings()
        assert oz.pds == "https://bsky.social"

    def test_is_configured_false_when_all_none(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.2: is_configured returns False when all fields are None."""
        monkeypatch.delenv("OZONE_HANDLE", raising=False)
        monkeypatch.delenv("OZONE_ADMIN_PASSWORD", raising=False)
        monkeypatch.delenv("OZONE_DID", raising=False)
        monkeypatch.delenv("OZONE_PDS", raising=False)
        from skywatch_mcp.config import OzoneSettings

        oz = OzoneSettings()
        assert oz.is_configured is False

    def test_is_configured_false_when_partial(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.2: is_configured returns False when only some fields set."""
        monkeypatch.setenv("OZONE_HANDLE", "admin")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "pass123")
        monkeypatch.delenv("OZONE_DID", raising=False)
        monkeypatch.delenv("OZONE_PDS", raising=False)
        from skywatch_mcp.config import OzoneSettings

        oz = OzoneSettings()
        assert oz.is_configured is False

    def test_is_configured_true_when_all_set(self, monkeypatch: MonkeyPatch) -> None:
        """AC5.2: is_configured returns True when all four fields set."""
        monkeypatch.setenv("OZONE_HANDLE", "admin")
        monkeypatch.setenv("OZONE_ADMIN_PASSWORD", "pass123")
        monkeypatch.setenv("OZONE_DID", "did:plc:test1234")
        monkeypatch.setenv("OZONE_PDS", "https://bsky.social")
        from skywatch_mcp.config import OzoneSettings

        oz = OzoneSettings()
        assert oz.is_configured is True

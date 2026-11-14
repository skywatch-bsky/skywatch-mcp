# pattern: Functional Core

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class ClickHouseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLICKHOUSE_", env_file=".env", extra="ignore")

    host: str = Field(default="http://localhost")
    port: int = Field(default=8123)
    user: str = Field(default="default")
    password: str = Field(default="")
    database: str = Field(default="default")
    tailnet_ip: str | None = Field(default=None)

    @property
    def effective_host(self) -> str:
        if self.tailnet_ip:
            return f"http://{self.tailnet_ip}"
        return self.host


class OzoneSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OZONE_", env_file=".env", extra="ignore")

    service_url: str | None = Field(default=None)
    handle: str | None = Field(default=None)
    admin_password: str | None = Field(default=None)
    did: str | None = Field(default=None)
    pds: str | None = Field(default=None)

    @property
    def is_configured(self) -> bool:
        return all([self.handle, self.admin_password, self.did, self.pds])


class ServerSettings(BaseSettings):
    """Server process settings. ``transport="http"`` serves streamable HTTP instead of stdio."""

    model_config = SettingsConfigDict(env_prefix="SKYWATCH_", env_file=".env", extra="ignore")

    transport: Literal["stdio", "http"] = Field(default="stdio")
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000)

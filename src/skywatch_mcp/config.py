# pattern: Functional Core

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

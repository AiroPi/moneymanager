from pydantic import BaseModel, Field


class MoneymanagerConfig(BaseModel):
    readers_dirname: str | None = Field(default=None)
    exports_direname: str | None = Field(default=None)
    groups_filename: str | None = Field(default=None)
    account_settings_filename: str | None = Field(default=None)
    grafana_dirname: str | None = Field(default=None)

"""Request bodies for the CRUD endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PersonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    color: str = ""
    note: str = ""


class PersonUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    color: str | None = None
    note: str | None = None


class DeviceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str | None = None
    person_id: int | None = None
    clear_person: bool = False


class DeviceAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person_id: int | None = None
    client_ids: list[int] = Field(default_factory=list)


class TagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Literal["tag", "category"] = "tag"
    color: str = ""
    description: str = ""


class TagUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    color: str | None = None
    description: str | None = None


class DomainTagsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag_ids: list[int] = Field(default_factory=list)


class RuleCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = "domain"
    operator: str = "suffix"
    value: str


class RuleTag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Literal["tag", "category"] = "tag"


class RuleWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    enabled: bool = True
    priority: int = 100
    match_mode: Literal["any", "all"] = "any"
    conditions: list[RuleCondition] = Field(default_factory=list)
    tags: list[RuleTag] = Field(default_factory=list)


class SavedFilterCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    filter: dict[str, Any] | list[Any] | None = None


class SavedFilterUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    filter: dict[str, Any] | list[Any] | None = None


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, Any] = Field(default_factory=dict)

from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field

MatchLevel = Literal["EXACT", "HIGH", "MEDIUM", "LOW", "CONFLICT"]

class ProductIdentity(BaseModel):
    brand: str | None = None
    manufacturer: str | None = None
    product_name: str | None = None
    model: str | None = None
    mpn: str | None = None
    sku: str | None = None
    ean: str | None = None
    upc: str | None = None
    gtin: str | None = None
    variant: str | None = None
    capacity: str | None = None
    color: str | None = None
    region: str | None = None
    confidence: float = 0.0
    match_level: MatchLevel = "LOW"
    identifiers_confirmed: list[str] = Field(default_factory=list)
    identifiers_conflicting: list[str] = Field(default_factory=list)

class Evidence(BaseModel):
    attribute: str
    raw_value: Any = None
    normalized_value: Any = None
    unit: str | None = None
    source_url: str | None = None
    source_type: str
    source_title: str | None = None
    page: int | None = None
    selector: str | None = None
    match_level: MatchLevel = "LOW"
    confidence: float = 0.0

class ProductRecord(BaseModel):
    identity: ProductIdentity
    specifications: dict[str, Any] = Field(default_factory=dict)
    additional_attributes: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    images: list[dict[str, Any]] = Field(default_factory=list)
    videos: list[dict[str, Any]] = Field(default_factory=list)
    media: list[dict[str, Any]] = Field(default_factory=list)
    site_profile: dict[str, Any] = Field(default_factory=dict)
    evidence_graph: dict[str, Any] = Field(default_factory=dict)
    technical_notes: list[dict[str, Any]] = Field(default_factory=list)
    fetch: dict[str, Any] = Field(default_factory=dict)

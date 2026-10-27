"""Page-scoped extension retention; the standalone canvas DSL stays strict.

Only declared fields have rendering semantics. Extra JSON members are opaque
document data; all inherited geometry, colour and shape validators still run.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.canvas.models import (
    Canvas,
    CanvasArea,
    CanvasContent,
    CircleShape,
    EllipseShape,
    GradientShape,
    LineShape,
    PolygonShape,
    RectShape,
    TextShape,
)


class ExtensibleDocument(BaseModel):
    """Retain JSON extensions without accepting arbitrary Python objects."""

    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    __pydantic_extra__: dict[str, JsonValue] = Field(init=False)


class DocumentRect(RectShape, ExtensibleDocument):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class DocumentCircle(CircleShape, ExtensibleDocument):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class DocumentEllipse(EllipseShape, ExtensibleDocument):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class DocumentLine(LineShape, ExtensibleDocument):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class DocumentPolygon(PolygonShape, ExtensibleDocument):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class DocumentText(TextShape, ExtensibleDocument):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class DocumentGradient(GradientShape, ExtensibleDocument):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


DocumentShape = Annotated[
    DocumentRect | DocumentCircle | DocumentEllipse | DocumentLine | DocumentPolygon | DocumentText | DocumentGradient,
    Field(discriminator="type"),
]


class DocumentContent(CanvasContent, ExtensibleDocument):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    shapes: list[DocumentShape] = Field(default_factory=list)


class DocumentArea(CanvasArea, ExtensibleDocument):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class DocumentCanvas(Canvas, ExtensibleDocument):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    area: DocumentArea
    content: DocumentContent | None = None


# These fields are allocated by the server, never portable author content.
PAGE_SERVER_FIELDS = frozenset(
    {"id", "created_at", "updated_at", "revision", "expected_revision", "edit_protocol", "document_protocol"}
)
PAGE_SHARE_EXCLUDED = PAGE_SERVER_FIELDS | {"demo_plugin_id"}

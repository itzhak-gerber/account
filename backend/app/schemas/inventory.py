import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models import MovementKind
from app.schemas.catalog import ItemOut

Quantity = Annotated[Decimal, Field(max_digits=14, decimal_places=3)]


class AdjustmentIn(BaseModel):
    # A stock count (the quantity actually on the shelf) or a correction (+/-): one of the two.
    counted: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=3)] | None = None
    change: Quantity | None = None
    # Cost per unit of goods added (e.g. an opening balance); default: the current average.
    unit_cost: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)] | None = None
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class StockItemOut(BaseModel):
    item: ItemOut
    quantity: Decimal
    average_cost: Decimal
    value: Decimal
    low: bool


class KitOut(BaseModel):
    item: ItemOut
    # How many complete kits the stock on hand allows (None: no stock-tracked components).
    available: Decimal | None


class StockOut(BaseModel):
    items: list[StockItemOut]
    kits: list[KitOut]
    total_value: Decimal


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: MovementKind
    quantity: Decimal
    unit_cost: Decimal
    balance_after: Decimal
    document_id: uuid.UUID | None
    kit_item_id: uuid.UUID | None
    reason: str
    created_at: datetime

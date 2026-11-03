"""
Pydantic schema for a supplier quotation document.

Delivery is captured as a raw value + unit so the LLM never has to
convert "4 weeks" → an integer.  Python handles the conversion.
"""
from typing import Optional
from pydantic import BaseModel, Field


class SupplierDoc(BaseModel):
    supplier_name: Optional[str] = Field(
        default=None,
        description="Full name of the supplier company.",
    )
    item_code: Optional[str] = Field(
        default=None,
        description="Single uppercase letter item code (A–E) from the purchase request.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Item description as written in the document.",
    )
    quantity: Optional[float] = Field(
        default=None,
        description="Numeric quantity offered. Null if unclear.",
    )
    unit: Optional[str] = Field(
        default=None,
        description="Unit of measure (e.g. metre, piece, cone).",
    )
    unit_price: Optional[float] = Field(
        default=None,
        description="Unit price in BDT. Null if missing.",
    )
    line_total: Optional[float] = Field(
        default=None,
        description="Line total in BDT (quantity × unit price). Null if missing.",
    )
    subtotal: Optional[float] = Field(
        default=None,
        description="Subtotal before VAT. Null if not shown.",
    )
    vat_amount: Optional[float] = Field(
        default=None,
        description="VAT amount in BDT. Null if not shown.",
    )
    vat_shown_separately: Optional[bool] = Field(
        default=None,
        description="True only if VAT appears as a separate line item.",
    )
    vat_rate: Optional[float] = Field(
        default=None,
        description="VAT percentage rate (e.g. 15). Null if not stated.",
    )
    total: Optional[float] = Field(
        default=None,
        description="Grand total including VAT. Null if missing.",
    )
    tin: Optional[str] = Field(
        default=None,
        description=(
            "Supplier TIN (Tax Identification Number) – exactly 12 digits. "
            "Null if not present or format does not match. "
            "Do NOT infer from partial text or 'available on request' phrasing."
        ),
    )
    bin: Optional[str] = Field(
        default=None,
        description=(
            "Supplier BIN (Business Identification Number) – exactly 9 digits. "
            "Null if not present or format does not match. "
            "Do NOT infer from partial text or 'available on request' phrasing."
        ),
    )
    advance_percent: Optional[float] = Field(
        default=None,
        description="Advance payment as a percentage (e.g. 20). Null if unclear.",
    )
    payment_terms_text: Optional[str] = Field(
        default=None,
        description="Exact text describing payment terms.",
    )
    payment_days_after_delivery: Optional[int] = Field(
        default=None,
        description=(
            "Number of days after delivery when payment is due. "
            "Null if vague, a range, or 'as agreed'."
        ),
    )
    # Delivery: raw value + unit instead of forcing the model to convert
    delivery_value: Optional[float] = Field(
        default=None,
        description=(
            "Numeric part of the delivery lead-time (e.g. 4 for '4 weeks', "
            "30 for '30 days'). "
            "Null if vague, a range, or 'as agreed'."
        ),
    )
    delivery_unit: Optional[str] = Field(
        default=None,
        description=(
            "Time unit for delivery (e.g. 'days', 'weeks'). "
            "Null if delivery_value is null."
        ),
    )
    has_penalty_clause: Optional[bool] = Field(
        default=None,
        description=(
            "True if the document contains a late-delivery penalty clause. "
            "False if it explicitly says there is none. "
            "Null if the document is silent on the matter."
        ),
    )
    penalty_percent_per_week: Optional[float] = Field(
        default=None,
        description=(
            "Late-delivery penalty as % of order value per week. "
            "Null if not stated or penalty clause is absent."
        ),
    )
    penalty_text: Optional[str] = Field(
        default=None,
        description="Exact text of the penalty clause, or null.",
    )
    validity_days: Optional[int] = Field(
        default=None,
        description="Number of days the quotation is valid for. Null if not stated.",
    )
    # quotes: field_name → exact substring from the document supporting that field
    quotes: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Mapping of every non-null field name to the exact verbatim substring "
            "from the document that supports it."
        ),
    )

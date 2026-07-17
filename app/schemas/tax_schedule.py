from pydantic import BaseModel


class TaxDeadlineItem(BaseModel):
    tax_type: str
    label: str
    due_date: str  # ISO 형식 (YYYY-MM-DD)
    d_day: int


class TaxScheduleResponse(BaseModel):
    business_type: str
    items: list[TaxDeadlineItem]

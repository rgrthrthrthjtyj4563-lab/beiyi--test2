from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class BillingItem(BaseModel):
    level: str
    name: str
    unit: str
    price: float
    is_existing: bool  # 是否来自现有业务
    can_simulate: bool # 制作对账单要求 contains '模拟'
    must_use: bool     # 计算是否必须使用 == '必须'
    category: str = ""
    billing_note: str = ""

class StatementItem(BaseModel):
    level: str
    name: str
    unit: str
    price: float
    quantity: float
    amount: float
    source: str # 'System', 'Simulation', 'Manual'
    category: str = ""
    billing_note: str = ""

class StatementSummary(BaseModel):
    target_amount: float
    generated_amount: float
    diff: float
    layers: dict # { "L1": {"amount": ..., "ratio": ...}, ... }
    warnings: List[str] = [] # List of validation warnings

class Statement(BaseModel):
    customer: str
    period: str
    target_amount: float
    summary: StatementSummary
    items: List[StatementItem]


class BillingItemConfigBase(BaseModel):
    code: Optional[str] = None
    name: str
    level: str
    category: str = ""
    unit: str
    price: float
    is_existing: bool = False
    can_simulate: bool = False
    must_use: bool = False
    allow_discount: bool = False
    status: str = "ACTIVE"
    sort_order: int = 0
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    billing_note: str = ""


class BillingItemConfigCreate(BillingItemConfigBase):
    pass


class BillingItemConfigUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    level: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    price: Optional[float] = None
    is_existing: Optional[bool] = None
    can_simulate: Optional[bool] = None
    must_use: Optional[bool] = None
    allow_discount: Optional[bool] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    billing_note: Optional[str] = None


class BillingItemConfig(BillingItemConfigBase):
    id: int
    created_at: str
    updated_at: str


class BusinessDataPreview(BaseModel):
    period: str
    filters: dict
    rows_total: int
    rows_used: int
    matched_columns: List[str]
    unmatched_columns: List[str]
    quantities: dict


class FieldMappingEntry(BaseModel):
    source_column: str
    target_item: str


class FieldMappingTemplateUpdate(BaseModel):
    template_name: str = "default"
    mappings: Dict[str, str] = Field(default_factory=dict)


class FieldMappingTemplate(BaseModel):
    template_name: str
    mappings: Dict[str, str]


class AllocationRuleTemplateUpdate(BaseModel):
    template_name: str = "standard"
    ratios: Dict[str, float] = Field(default_factory=lambda: {"L1": 0.55, "L2": 0.30, "L3": 0.10, "L4": 0.05})
    l4_max_ratio: float = 0.05
    ratio_warning_threshold: float = 0.15
    fill_order: List[str] = Field(default_factory=lambda: ["L2", "L3", "L4"])
    strategy_name: str = "equal_split_v1"


class AllocationRuleTemplate(BaseModel):
    template_name: str
    ratios: Dict[str, float]
    l4_max_ratio: float
    ratio_warning_threshold: float
    fill_order: List[str]
    strategy_name: str
    version: int = 1


class AllocationRuleVersion(BaseModel):
    template_name: str
    version: int
    ratios: Dict[str, float]
    l4_max_ratio: float
    ratio_warning_threshold: float
    fill_order: List[str]
    strategy_name: str
    created_at: str


class AllocationStrategyOption(BaseModel):
    key: str
    label: str


class DataSourceRecord(BaseModel):
    id: int
    statement_id: Optional[str] = None
    source_type: str
    source_name: Optional[str] = None
    period: Optional[str] = None
    no_data_reason: Optional[str] = None
    rows_total: int = 0
    rows_used: int = 0
    matched_columns: int = 0
    unmatched_columns: int = 0
    created_at: str

from typing import Dict, List, Optional

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# V2.0 计费模式（中文）
BILLING_MODES = ("固定入账", "智能择取", "模拟填充")

# 优先级默认值按层级
DEFAULT_PICK_PRIORITY = {"L1": 10, "L2": 50, "L3": 100, "L4": 200}


class BillingItem(BaseModel):
    """计费项模型 - V2.0简化版"""
    id: Optional[int] = None
    name: str  # 计费项名称
    level: str  # 计费层级: L1/L2/L3/L4
    unit: str  # 计量单位
    price: float  # 单价
    billing_mode: str = "智能择取"  # 计费模式: 固定入账/智能择取/模拟填充
    pick_priority: int = 100  # 择取优先级（数字越小优先级越高）
    require_business_data: bool = True  # 是否需业务数据
    category: str = ""  # 计费分类
    billing_note: str = ""  # 计费说明
    status: str = "启用"  # 状态: 启用/停用
    
    # 以下字段保留用于历史数据兼容，不参与新计算逻辑
    is_existing: bool = False  # 是否来自现有业务（只读）
    can_simulate: bool = False  # V1遗留（只读）
    must_use: bool = False  # V1遗留（只读）
    is_enabled_default: bool = True  # V1遗留（只读）
    quantity_mode: str = "ACTUAL_FULL"  # V1遗留（只读）
    min_pick_ratio: float = 0.0  # V1遗留（只读）
    max_pick_ratio: float = 1.0  # V1遗留（只读）
    report_required: bool = False  # V1遗留（只读）
    tail_balance_eligible: bool = False  # V1遗留（只读）


class StatementItem(BaseModel):
    level: str
    name: str
    unit: str
    price: float
    quantity: float
    amount: float
    source: str  # '业务真实数据', '择取计费', '规则分配', '尾差调平', '人工录入'
    quantity_mode: str = "ACTUAL_FULL"
    actual_qty: float = 0.0
    billed_qty: float = 0.0
    unbilled_qty: float = 0.0
    decision_reason_code: str = ""
    category: str = ""
    billing_note: str = ""


class StatementSummary(BaseModel):
    target_amount: float
    generated_amount: float
    diff: float
    layers: dict
    warnings: List[str] = Field(default_factory=list)
    calc_snapshot_json: Dict = Field(default_factory=dict)
    item_decision_json: List[Dict] = Field(default_factory=list)


class Statement(BaseModel):
    customer: str
    period: str
    target_amount: float
    summary: StatementSummary
    items: List[StatementItem]


class BillingItemConfigBase(BaseModel):
    """计费项配置基础模型 - V2.0 简化版"""
    # 核心字段
    name: str  # 计费项名称
    level: str  # 计费层级: L1/L2/L3/L4
    unit: str  # 计量单位
    price: float  # 单价
    billing_mode: str = "智能择取"  # 计费模式: 固定入账/智能择取/模拟填充
    pick_priority: int = 100  # 择取优先级（数字越小优先级越高）
    require_business_data: bool = True  # 是否需业务数据
    category: str = ""  # 计费分类
    billing_note: str = ""  # 计费说明
    status: str = "启用"  # 状态: 启用/停用
    
    # 可选字段
    code: Optional[str] = None  # 编码
    sort_order: int = 0  # 排序权重
    effective_from: Optional[str] = None  # 生效时间
    effective_to: Optional[str] = None  # 失效时间
    
    # V1遗留字段（保留用于兼容，不参与新计算逻辑）
    is_existing: bool = False
    can_simulate: bool = False
    must_use: bool = False
    is_enabled_default: bool = True
    quantity_mode: str = "ACTUAL_FULL"
    min_pick_ratio: float = 0.0
    max_pick_ratio: float = 1.0
    report_required: bool = False
    tail_balance_eligible: bool = False
    allow_discount: bool = False


class BillingItemConfigCreate(BaseModel):
    """创建计费项请求模型"""
    name: str
    level: str
    unit: str
    price: float
    billing_mode: str = "智能择取"
    pick_priority: Optional[int] = None  # 不传则按层级自动设置
    require_business_data: bool = True
    category: str = ""
    billing_note: str = ""
    code: Optional[str] = None


class BillingItemConfigUpdate(BaseModel):
    """更新计费项请求模型"""
    name: Optional[str] = None
    level: Optional[str] = None
    unit: Optional[str] = None
    price: Optional[float] = None
    billing_mode: Optional[str] = None
    pick_priority: Optional[int] = None
    require_business_data: Optional[bool] = None
    category: Optional[str] = None
    billing_note: Optional[str] = None
    status: Optional[str] = None  # 启用/停用


class BatchBillingItemUpdate(BaseModel):
    """批量更新计费项请求模型"""
    item_ids: List[int]
    updates: Dict[str, Any]  # 允许更新的字段


class BatchBillingItemDelete(BaseModel):
    """批量删除计费项请求模型"""
    item_ids: List[int]


class BillingItemConfig(BillingItemConfigBase):
    """计费项配置响应模型"""
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
    selection_strategy: str = "priority_greedy_v1"
    enabled_item_ids: List[int] = Field(default_factory=list)
    tail_diff_threshold: float = 0.0
    fallback_l3_item_id: Optional[int] = None
    max_simulation_ratio: float = 1.0


class AllocationRuleTemplate(BaseModel):
    template_name: str
    ratios: Dict[str, float]
    l4_max_ratio: float
    ratio_warning_threshold: float
    fill_order: List[str]
    strategy_name: str
    selection_strategy: str = "priority_greedy_v1"
    enabled_item_ids: List[int] = Field(default_factory=list)
    tail_diff_threshold: float = 0.0
    fallback_l3_item_id: Optional[int] = None
    max_simulation_ratio: float = 1.0
    version: int = 1


class AllocationRuleVersion(BaseModel):
    template_name: str
    version: int
    ratios: Dict[str, float]
    l4_max_ratio: float
    ratio_warning_threshold: float
    fill_order: List[str]
    strategy_name: str
    selection_strategy: str = "priority_greedy_v1"
    enabled_item_ids: List[int] = Field(default_factory=list)
    tail_diff_threshold: float = 0.0
    fallback_l3_item_id: Optional[int] = None
    max_simulation_ratio: float = 1.0
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
    rows_total: int = 0
    rows_used: int = 0
    matched_columns: int = 0
    unmatched_columns: int = 0
    created_at: str

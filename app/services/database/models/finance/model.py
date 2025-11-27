from datetime import datetime
from datetime import date as date_type
from typing import Optional
from sqlmodel import Field, SQLModel


class UserGoal(SQLModel, table=True):
    """用户年度目标配置"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", unique=True, index=True)
    
    # 起始配置
    start_date: date_type                         # 开始日期
    total_months: int = Field(default=12)         # 总周期（月）
    
    # 储蓄目标
    savings_target: float                         # 储蓄目标金额
    initial_savings: float                        # 初始储蓄金额
    current_savings: float                        # 当前储蓄金额
    
    # 债务目标（初始总债务，用于计算进度）
    initial_total_debt: float                     # 初始总债务
    
    # 每日预算
    daily_budget_limit: float = Field(default=150)
    monthly_income: Optional[float] = None        # 月收入（可选）
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Transaction(SQLModel, table=True):
    """收支记录"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str = Field(max_length=100)                    # 描述：午餐、工资
    amount: float                                         # 金额（正数）
    type: str = Field(max_length=20)                     # "income" | "expense"
    category: str = Field(max_length=50, index=True)     # food, traffic, salary...
    date: date_type = Field(index=True)                  # 记录日期
    note: Optional[str] = Field(default=None, max_length=500)  # 备注
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Budget(SQLModel, table=True):
    """预算设置 - 每个用户每个类别一条记录"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    category: str = Field(max_length=50)                 # 类别
    monthly_limit: float                                  # 月预算上限
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        # 每个用户每个类别只有一条记录
        table_name = "budget"


class Debt(SQLModel, table=True):
    """债务追踪"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str = Field(max_length=100)                    # 债务名称：信用卡A、花呗
    total_amount: float                                   # 总欠款
    remaining_amount: float                               # 剩余欠款
    interest_rate: Optional[float] = Field(default=0)    # 年利率（可选）
    due_date: Optional[date_type] = None                 # 截止日期
    is_cleared: bool = Field(default=False)              # 是否已还清
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SavingsGoal(SQLModel, table=True):
    """储蓄目标 - 每个用户一条记录"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, unique=True)
    target_amount: float = Field(default=50000)          # 目标金额
    current_amount: float = Field(default=0)             # 当前已存
    deadline: Optional[date_type] = None                 # 目标日期
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UserSettings(SQLModel, table=True):
    """用户个性化设置"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", unique=True)
    daily_budget_limit: float = Field(default=150)       # 每日消费限额
    monthly_income: Optional[float] = None               # 月收入（用于计算）
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


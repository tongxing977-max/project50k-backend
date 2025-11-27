"""
财务模块 API
- 收支记录 CRUD
- 预算管理
- 债务追踪
- 储蓄目标
- Dashboard 综合数据
"""
from datetime import date as DateType, datetime, timedelta
from typing import Optional
from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from app.services.database.models.finance.model import (
    Transaction, Budget, Debt, SavingsGoal, UserSettings, UserGoal
)
from app.services.deps import get_session

router = APIRouter(prefix="/finance", tags=["finance"])


# ============== Pydantic Schemas ==============

class TransactionCreate(BaseModel):
    name: str
    amount: float
    type: str  # "income" | "expense"
    category: str
    date: DateType | None = None
    note: str | None = None


class TransactionOut(BaseModel):
    model_config = {"from_attributes": True}
    
    id: int
    name: str
    amount: float
    type: str
    category: str
    date: DateType
    note: str | None
    created_at: datetime


class BudgetSet(BaseModel):
    category: str
    monthly_limit: float


class BudgetOut(BaseModel):
    category: str
    monthly_limit: float


class DebtCreate(BaseModel):
    name: str
    total_amount: float
    remaining_amount: float | None = None
    interest_rate: float | None = 0
    due_date: DateType | None = None


class DebtOut(BaseModel):
    model_config = {"from_attributes": True}
    
    id: int
    name: str
    total_amount: float
    remaining_amount: float
    interest_rate: float
    due_date: DateType | None
    is_cleared: bool
    progress_percent: float  # 已还百分比


class DebtPayment(BaseModel):
    amount: float


class UserGoalCreate(BaseModel):
    start_date: DateType
    total_months: int = 12
    savings_target: float
    initial_savings: float
    current_savings: float
    initial_total_debt: float
    daily_budget_limit: float = 150
    monthly_income: float | None = None


class UserGoalUpdate(BaseModel):
    current_savings: float | None = None
    daily_budget_limit: float | None = None
    monthly_income: float | None = None


class UserGoalOut(BaseModel):
    model_config = {"from_attributes": True}
    
    start_date: DateType
    total_months: int
    savings_target: float
    initial_savings: float
    current_savings: float
    initial_total_debt: float
    daily_budget_limit: float
    monthly_income: float | None


# Dashboard 相关 Schema
class YearlyGoalData(BaseModel):
    total_target: float           # 需要完成的总额
    current_progress: float       # 当前已完成
    progress_percent: float       # 完成百分比
    remaining: float              # 剩余需要完成
    paid_debt: float              # 已还债务
    savings_growth: float         # 储蓄增长
    remaining_months: int         # 剩余月数
    monthly_target: float         # 月度目标


class TodayData(BaseModel):
    date: DateType
    expense: float
    remaining_budget: float
    daily_limit: float
    transactions: list[TransactionOut]


class MonthlyData(BaseModel):
    year_month: str
    income: float
    expense: float
    balance: float
    by_category: dict


class SavingsData(BaseModel):
    current: float
    target: float
    initial: float
    growth: float
    progress_percent: float
    net_worth: float              # 净资产 = 当前储蓄 - 当前债务
    net_worth_target: float       # 净资产目标 = 储蓄目标 - 0（债务清零）


class AlertItem(BaseModel):
    type: str  # "error" | "warning"
    category: str
    message: str


class DashboardOverview(BaseModel):
    yearly_goal: YearlyGoalData
    today: TodayData
    monthly: MonthlyData
    savings: SavingsData
    debts: list[DebtOut]
    total_debt: float
    budgets: dict
    budget_usage: dict  # 各分类已用金额
    alerts: list[AlertItem]
    daily_budget_limit: float     # 每日预算限额（可调整）


# ============== 用户ID（临时，后续从JWT获取） ==============

def get_current_user_id() -> int:
    return 1  # TODO: 从 JWT token 获取


# ============== 工具函数 ==============

def get_remaining_months(start_date: DateType, total_months: int) -> int:
    """计算剩余月数"""
    end_date = start_date + relativedelta(months=total_months)
    today = DateType.today()
    
    if today >= end_date:
        return 1  # 至少1个月
    
    # 计算从起始日期到今天过了几个月
    months_passed = (today.year - start_date.year) * 12 + (today.month - start_date.month)
    return max(1, total_months - months_passed)


def get_current_month_str() -> str:
    """获取当月字符串 YYYY-MM"""
    return DateType.today().strftime("%Y-%m")


# ============== Transaction API ==============

@router.post("/transactions", response_model=TransactionOut)
async def create_transaction(
    payload: TransactionCreate,
    db: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id)
):
    """新增收支记录"""
    tx = Transaction(
        user_id=user_id,
        name=payload.name,
        amount=payload.amount,
        type=payload.type,
        category=payload.category,
        date=payload.date or DateType.today(),
        note=payload.note,
    )
    db.add(tx)
    await db.commit()
    await db.refresh(tx)
    return tx


@router.get("/transactions", response_model=list[TransactionOut])
async def list_transactions(
    start_date: DateType | None = Query(None),
    end_date: DateType | None = Query(None),
    category: str | None = Query(None),
    type: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id)
):
    """获取收支记录列表"""
    query = select(Transaction).where(Transaction.user_id == user_id)
    
    if start_date:
        query = query.where(Transaction.date >= start_date)
    if end_date:
        query = query.where(Transaction.date <= end_date)
    if category:
        query = query.where(Transaction.category == category)
    if type:
        query = query.where(Transaction.type == type)
    
    query = query.order_by(Transaction.date.desc(), Transaction.created_at.desc())
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()


@router.delete("/transactions/{tx_id}", status_code=204)
async def delete_transaction(
    tx_id: int,
    db: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id)
):
    """删除收支记录"""
    result = await db.execute(
        select(Transaction).where(
            Transaction.id == tx_id,
            Transaction.user_id == user_id
        )
    )
    tx = result.scalar()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    await db.delete(tx)
    await db.commit()
    return None


# ============== Budget API ==============

@router.get("/budgets", response_model=list[BudgetOut])
async def list_budgets(
    db: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id)
):
    """获取预算设置"""
    result = await db.execute(
        select(Budget).where(Budget.user_id == user_id)
    )
    return result.scalars().all()


@router.post("/budgets", response_model=BudgetOut)
async def set_budget(
    payload: BudgetSet,
    db: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id)
):
    """设置/更新某类别预算"""
    result = await db.execute(
        select(Budget).where(
            Budget.user_id == user_id,
            Budget.category == payload.category
        )
    )
    budget = result.scalar()
    
    if budget:
        budget.monthly_limit = payload.monthly_limit
        budget.updated_at = datetime.utcnow()
    else:
        budget = Budget(
            user_id=user_id,
            category=payload.category,
            monthly_limit=payload.monthly_limit,
        )
        db.add(budget)
    
    await db.commit()
    await db.refresh(budget)
    return budget


# ============== Debt API ==============

@router.get("/debts", response_model=list[DebtOut])
async def list_debts(
    db: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id)
):
    """获取债务列表"""
    result = await db.execute(
        select(Debt).where(Debt.user_id == user_id).order_by(Debt.created_at.desc())
    )
    debts = result.scalars().all()
    
    return [
        DebtOut(
            id=d.id,
            name=d.name,
            total_amount=d.total_amount,
            remaining_amount=d.remaining_amount,
            interest_rate=d.interest_rate or 0,
            due_date=d.due_date,
            is_cleared=d.is_cleared,
            progress_percent=round(((d.total_amount - d.remaining_amount) / d.total_amount) * 100, 1) if d.total_amount > 0 else 0
        )
        for d in debts
    ]


@router.post("/debts", response_model=DebtOut)
async def create_debt(
    payload: DebtCreate,
    db: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id)
):
    """新增债务"""
    debt = Debt(
        user_id=user_id,
        name=payload.name,
        total_amount=payload.total_amount,
        remaining_amount=payload.remaining_amount or payload.total_amount,
        interest_rate=payload.interest_rate or 0,
        due_date=payload.due_date,
    )
    db.add(debt)
    await db.commit()
    await db.refresh(debt)
    
    return DebtOut(
        id=debt.id,
        name=debt.name,
        total_amount=debt.total_amount,
        remaining_amount=debt.remaining_amount,
        interest_rate=debt.interest_rate or 0,
        due_date=debt.due_date,
        is_cleared=debt.is_cleared,
        progress_percent=0
    )


@router.put("/debts/{debt_id}/pay", response_model=DebtOut)
async def pay_debt(
    debt_id: int,
    payload: DebtPayment,
    db: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id)
):
    """还款"""
    result = await db.execute(
        select(Debt).where(Debt.id == debt_id, Debt.user_id == user_id)
    )
    debt = result.scalar()
    if not debt:
        raise HTTPException(status_code=404, detail="Debt not found")
    
    debt.remaining_amount = max(0, debt.remaining_amount - payload.amount)
    debt.is_cleared = debt.remaining_amount == 0
    debt.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(debt)
    
    return DebtOut(
        id=debt.id,
        name=debt.name,
        total_amount=debt.total_amount,
        remaining_amount=debt.remaining_amount,
        interest_rate=debt.interest_rate or 0,
        due_date=debt.due_date,
        is_cleared=debt.is_cleared,
        progress_percent=round(((debt.total_amount - debt.remaining_amount) / debt.total_amount) * 100, 1) if debt.total_amount > 0 else 0
    )


@router.delete("/debts/{debt_id}", status_code=204)
async def delete_debt(
    debt_id: int,
    db: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id)
):
    """删除债务"""
    result = await db.execute(
        select(Debt).where(Debt.id == debt_id, Debt.user_id == user_id)
    )
    debt = result.scalar()
    if not debt:
        raise HTTPException(status_code=404, detail="Debt not found")
    
    await db.delete(debt)
    await db.commit()
    return None


# ============== User Goal API ==============

@router.get("/goal", response_model=UserGoalOut)
async def get_user_goal(
    db: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id)
):
    """获取用户目标配置"""
    result = await db.execute(
        select(UserGoal).where(UserGoal.user_id == user_id)
    )
    goal = result.scalar()
    
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not configured. Please initialize first.")
    
    return goal


@router.post("/goal", response_model=UserGoalOut)
async def create_user_goal(
    payload: UserGoalCreate,
    db: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id)
):
    """创建/更新用户目标配置"""
    result = await db.execute(
        select(UserGoal).where(UserGoal.user_id == user_id)
    )
    goal = result.scalar()
    
    if goal:
        # 更新
        goal.start_date = payload.start_date
        goal.total_months = payload.total_months
        goal.savings_target = payload.savings_target
        goal.initial_savings = payload.initial_savings
        goal.current_savings = payload.current_savings
        goal.initial_total_debt = payload.initial_total_debt
        goal.daily_budget_limit = payload.daily_budget_limit
        goal.monthly_income = payload.monthly_income
        goal.updated_at = datetime.utcnow()
    else:
        # 创建
        goal = UserGoal(
            user_id=user_id,
            **payload.model_dump()
        )
        db.add(goal)
    
    await db.commit()
    await db.refresh(goal)
    return goal


@router.put("/goal", response_model=UserGoalOut)
async def update_user_goal(
    payload: UserGoalUpdate,
    db: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id)
):
    """更新用户目标（部分更新）"""
    result = await db.execute(
        select(UserGoal).where(UserGoal.user_id == user_id)
    )
    goal = result.scalar()
    
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not configured")
    
    if payload.current_savings is not None:
        goal.current_savings = payload.current_savings
    if payload.daily_budget_limit is not None:
        goal.daily_budget_limit = payload.daily_budget_limit
    if payload.monthly_income is not None:
        goal.monthly_income = payload.monthly_income
    
    goal.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(goal)
    return goal


# ============== Dashboard API ==============

@router.get("/dashboard", response_model=DashboardOverview)
async def get_dashboard(
    db: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id)
):
    """获取 Dashboard 综合数据（所有计算在这里完成）"""
    
    # 1. 获取用户目标配置
    goal_result = await db.execute(
        select(UserGoal).where(UserGoal.user_id == user_id)
    )
    goal = goal_result.scalar()
    
    if not goal:
        raise HTTPException(status_code=404, detail="请先初始化目标配置 POST /api/v1/finance/goal")
    
    # 2. 获取所有债务
    debts_result = await db.execute(
        select(Debt).where(Debt.user_id == user_id)
    )
    debts = debts_result.scalars().all()
    
    # 3. 获取预算设置
    budgets_result = await db.execute(
        select(Budget).where(Budget.user_id == user_id)
    )
    budgets_list = budgets_result.scalars().all()
    budgets = {b.category: b.monthly_limit for b in budgets_list}
    
    # 4. 获取今日交易
    today = DateType.today()
    today_tx_result = await db.execute(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.date == today
        ).order_by(Transaction.created_at.desc())
    )
    today_transactions = today_tx_result.scalars().all()
    
    # 5. 获取本月交易
    month_start = today.replace(day=1)
    month_end = (month_start + relativedelta(months=1)) - timedelta(days=1)
    month_tx_result = await db.execute(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.date >= month_start,
            Transaction.date <= month_end
        )
    )
    month_transactions = month_tx_result.scalars().all()
    
    # 6. 获取所有交易（用于计算当前储蓄）
    all_tx_result = await db.execute(
        select(Transaction).where(Transaction.user_id == user_id)
    )
    all_transactions = all_tx_result.scalars().all()
    
    # ============== 计算逻辑 ==============
    
    # 今日数据
    today_expense = sum(t.amount for t in today_transactions if t.type == "expense")
    today_remaining = goal.daily_budget_limit - today_expense
    
    # 本月数据
    monthly_income = sum(t.amount for t in month_transactions if t.type == "income")
    monthly_expense = sum(t.amount for t in month_transactions if t.type == "expense")
    monthly_balance = monthly_income - monthly_expense
    
    # 本月分类支出
    by_category = {}
    for t in month_transactions:
        if t.type == "expense":
            by_category[t.category] = by_category.get(t.category, 0) + t.amount
    
    # 债务计算
    current_total_debt = sum(d.remaining_amount for d in debts if not d.is_cleared)
    paid_debt = goal.initial_total_debt - current_total_debt
    
    # ============== 储蓄动态计算 ==============
    # 当前储蓄 = 初始储蓄 + 总收入 - 总支出 - 已还债务
    total_income = sum(t.amount for t in all_transactions if t.type == "income")
    total_expense = sum(t.amount for t in all_transactions if t.type == "expense")
    current_savings = goal.initial_savings + total_income - total_expense - paid_debt
    savings_growth = current_savings - goal.initial_savings
    
    # 年度目标计算
    # 总目标 = 储蓄目标 + 初始债务（要存够50000 + 还清21800 = 71800）
    total_target = goal.savings_target + goal.initial_total_debt
    
    # 当前进度 = 当前储蓄 + 已还债务
    current_progress = current_savings + paid_debt
    
    # 剩余
    remaining = max(0, total_target - current_progress)
    
    # 完成百分比
    progress_percent = round((current_progress / total_target) * 100, 1) if total_target > 0 else 0
    
    # 剩余月数
    remaining_months = get_remaining_months(goal.start_date, goal.total_months)
    
    # 月度目标
    monthly_target = round(remaining / remaining_months) if remaining_months > 0 else 0
    
    # ============== 预警检测 ==============
    alerts = []
    
    # 今日超支
    if today_remaining < 0:
        alerts.append(AlertItem(
            type="error",
            category="daily_budget",
            message=f"今日已超支 ¥{abs(today_remaining):.0f}"
        ))
    elif today_remaining < goal.daily_budget_limit * 0.2:
        alerts.append(AlertItem(
            type="warning",
            category="daily_budget",
            message=f"今日预算仅剩 ¥{today_remaining:.0f}"
        ))
    
    # 分类预算超支
    category_labels = {
        "food": "餐饮", "traffic": "交通", "shopping": "购物",
        "entertainment": "娱乐", "love": "恋爱", "family": "生活用品",
        "health": "健康/运动", "other": "其他"
    }
    for cat, spent in by_category.items():
        limit = budgets.get(cat, 0)
        if limit > 0:
            if spent > limit:
                alerts.append(AlertItem(
                    type="error",
                    category="category_budget",
                    message=f"{category_labels.get(cat, cat)}已超预算 ¥{spent - limit:.0f}"
                ))
            elif spent > limit * 0.8:
                alerts.append(AlertItem(
                    type="warning",
                    category="category_budget",
                    message=f"{category_labels.get(cat, cat)}预算已用 {int(spent / limit * 100)}%"
                ))
    
    # ============== 组装返回数据 ==============
    
    debts_out = [
        DebtOut(
            id=d.id,
            name=d.name,
            total_amount=d.total_amount,
            remaining_amount=d.remaining_amount,
            interest_rate=d.interest_rate or 0,
            due_date=d.due_date,
            is_cleared=d.is_cleared,
            progress_percent=round(((d.total_amount - d.remaining_amount) / d.total_amount) * 100, 1) if d.total_amount > 0 else 0
        )
        for d in debts
    ]
    
    today_tx_out = [
        TransactionOut(
            id=t.id,
            name=t.name,
            amount=t.amount,
            type=t.type,
            category=t.category,
            date=t.date,
            note=t.note,
            created_at=t.created_at
        )
        for t in today_transactions
    ]
    
    return DashboardOverview(
        yearly_goal=YearlyGoalData(
            total_target=total_target,
            current_progress=current_progress,
            progress_percent=progress_percent,
            remaining=remaining,
            paid_debt=paid_debt,
            savings_growth=savings_growth,
            remaining_months=remaining_months,
            monthly_target=monthly_target
        ),
        today=TodayData(
            date=today,
            expense=today_expense,
            remaining_budget=today_remaining,
            daily_limit=goal.daily_budget_limit,
            transactions=today_tx_out
        ),
        monthly=MonthlyData(
            year_month=today.strftime("%Y-%m"),
            income=monthly_income,
            expense=monthly_expense,
            balance=monthly_balance,
            by_category=by_category
        ),
        savings=SavingsData(
            current=current_savings,  # 使用动态计算的储蓄
            target=goal.savings_target,
            initial=goal.initial_savings,
            growth=savings_growth,
            progress_percent=round((current_savings / goal.savings_target) * 100, 1) if goal.savings_target > 0 else 0,
            net_worth=current_savings - current_total_debt,  # 净资产也用动态储蓄
            net_worth_target=goal.savings_target
        ),
        debts=debts_out,
        total_debt=current_total_debt,
        budgets=budgets,
        budget_usage=by_category,
        alerts=alerts,
        daily_budget_limit=goal.daily_budget_limit
    )


# ============== 初始化数据接口 ==============

@router.post("/init", status_code=201)
async def initialize_data(
    db: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id)
):
    """
    初始化用户数据（一次性调用）
    创建目标配置和初始债务
    """
    # 检查是否已初始化
    existing = await db.execute(
        select(UserGoal).where(UserGoal.user_id == user_id)
    )
    if existing.scalar():
        raise HTTPException(status_code=400, detail="已经初始化过了")
    
    # 创建目标配置
    goal = UserGoal(
        user_id=user_id,
        start_date=date(2025, 11, 28),
        total_months=12,
        savings_target=50000,
        initial_savings=11150,
        current_savings=11150,
        initial_total_debt=21800,
        daily_budget_limit=150,
        monthly_income=10600
    )
    db.add(goal)
    
    # 创建初始债务
    debts = [
        Debt(user_id=user_id, name="抖音", total_amount=6000, remaining_amount=6000),
        Debt(user_id=user_id, name="京东", total_amount=15000, remaining_amount=15000),
        Debt(user_id=user_id, name="美团", total_amount=800, remaining_amount=800),
    ]
    for d in debts:
        db.add(d)
    
    # 创建默认预算
    default_budgets = [
        ("food", 2000), ("traffic", 500), ("shopping", 800),
        ("entertainment", 500), ("love", 1000), ("family", 600),
        ("health", 300), ("other", 300)
    ]
    for cat, limit in default_budgets:
        budget = Budget(user_id=user_id, category=cat, monthly_limit=limit)
        db.add(budget)
    
    await db.commit()
    
    return {"message": "初始化成功", "user_id": user_id}

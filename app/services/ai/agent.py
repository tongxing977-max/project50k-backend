"""
财务 AI Agent 服务
使用 DeepSeek API 进行智能分类和消费分析
"""
import json
import os
from typing import Optional
from pydantic import BaseModel
from openai import AsyncOpenAI


# ================= 配置 =================

# 优先从环境变量读取，否则使用默认值
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-d0323888535b4436aae5ebc4c0ccce71") #  我们在这里接通deepseek的key
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com") #  我们在这里接通deepseek的api


# ================= 数据模型 =================

class ClassifyResult(BaseModel):
    """分类结果"""
    category: str
    amount: float = 0
    is_latte: bool = False  # 拿铁因子：非必要消费
    comment: str = ""
    confidence: float = 0.9


class InsightResult(BaseModel):
    """消费洞察结果"""
    summary: str
    warnings: list[str] = []
    suggestions: list[str] = []


# ================= Prompts =================

CLASSIFY_SYSTEM_PROMPT = """你是一个专业的财务审计 Agent，服务于一名正在执行 "Project 50k" 计划的程序员，他的目标是存钱！
你的任务是将用户的自然语言输入转化为结构化的 JSON 数据。

核心规则：

1. 【分类】根据 type 从对应列表中选择最匹配的一个：
   - 支出(expense): ["food", "coffee", "traffic", "shopping", "entertainment", "love", "family", "health", "AI_productivity", "other"]
   - 收入(income): ["salary", "bonus", "sidejob", "AI_productivity", "other"]
   
   分类说明：
   - food: 餐饮（餐厅、外卖、食材、零食、沃尔玛、山姆等超市买吃的）
   - coffee: 咖啡（星巴克、瑞幸等咖啡店消费）
   - traffic: 交通（地铁、打车、公交）
   - shopping: 购物（衣服、电子产品、日用品）
   - entertainment: 娱乐（电影、游戏、KTV）
   - love: 恋爱（约会、礼物给对象）
   - family: 生活用品（水电费、房租、家居）
   - health: 健康/运动（医药、健身、体检）
   - AI_productivity: AI 生产力（AI 工具、AI 课程、API、OpenAI、DeepSeek、Claude 等）
   - other: 无法归类的其他消费

2. 【金额】提取数字，如果没说金额，使用传入的 amount 参数。

3. 【拿铁因子判定】(is_latte):
   - 如果是奶茶、咖啡、打车（非必要）、盲盒、游戏充值等提升情绪但非生存必要的，设为 true。
   - 吃饭、地铁、房租等生存必要的，设为 false。

4. 【评价】(comment): 用简短犀利的语言点评这笔消费（少于20字）。
   
   ⚠️ 评价必须结合【金额大小】来判断，不能只看消费类型！
   
   金额评判标准：
   - 金额 < 30：小额消费，可以轻松点评
   - 金额 30-100：中等消费，正常点评
   - 金额 100-300：较大消费要提醒"有点贵"、"这笔不小"
   - 金额 > 300：大额消费，必须警示！ 这个是本质,无关同类的
   
   评价规则：
   - 拿铁因子：温和地阴阳怪气
   - 小额必要消费（如 ¥15 午餐）：夸奖省钱
   - 大额消费（如 ¥299 山姆）：即使是必要消费也要提醒"这笔花销不小哦"
   - 超大额（¥500+）：严肃警告

请务必只返回 JSON 格式，不要包含 Markdown 代码块标记。

格式示例（小额）：
{
    "category": "food",
    "amount": 15.0,
    "is_latte": false,
    "comment": "老乡鸡yyds，省钱冠军！"
}

格式示例（大额）：
{
    "category": "food",
    "amount": 299.0,
    "is_latte": false,
    "comment": "山姆一趟300，钱包在哭泣"
}
"""

INSIGHT_SYSTEM_PROMPT = """你是一个专业的财务分析师，正在帮助用户分析消费数据。
请根据提供的消费数据，给出简洁有力的分析报告。

分析要点：
1. 总结消费概况
2. 指出潜在问题（超支、拿铁因子过多等）
3. 给出 2-3 条具体可行的建议

返回 JSON 格式：
{
    "summary": "本月消费概况...",
    "warnings": ["警告1", "警告2"],
    "suggestions": ["建议1", "建议2"]
}
"""


# ================= Agent 类 =================

class FinanceAgent:
    """财务 AI Agent"""
    
    def __init__(self, api_key: str = None, base_url: str = None):
        self.client = AsyncOpenAI(
            api_key=api_key or DEEPSEEK_API_KEY,
            base_url=base_url or DEEPSEEK_BASE_URL
        )
    
    async def classify(
        self, 
        description: str,   
        amount: float = 0,
        tx_type: str = "expense"
    ) -> Optional[ClassifyResult]:
        """
        智能分类消费/收入
        
        Args:
            description: 消费描述，如 "美团外卖 麦当劳"
            amount: 金额（可选，AI 会尝试从描述中提取）
            tx_type: 类型 "expense" | "income"
        
        Returns:
            ClassifyResult 或 None（如果失败）
        """
        try:
            user_message = f"类型: {tx_type}\n描述: {description}\n金额: {amount}"
            
            response = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1,  # 低温度保证格式稳定
                max_tokens=200
            )
            
            print(response)
            result_text = response.choices[0].message.content.strip()
            
            # 清洗 Markdown 格式
            if result_text.startswith("```"):
                result_text = result_text.replace("```json", "").replace("```", "").strip()
            
            data = json.loads(result_text)
            
            return ClassifyResult(
                category=data.get("category", "other"),
                amount=data.get("amount", amount),
                is_latte=data.get("is_latte", False),
                comment=data.get("comment", ""),
                confidence=0.9
            )
            
        except json.JSONDecodeError as e:
            print(f"[AI Agent] JSON 解析失败: {e}, 原始响应: {result_text}")
            return None
        except Exception as e:
            print(f"[AI Agent] 分类失败: {e}")
            return None
    
    async def analyze_spending(
        self,
        transactions: list[dict],
        period: str = "本月"
    ) -> Optional[InsightResult]:
        """
        分析消费数据，给出洞察
        
        Args:
            transactions: 交易记录列表
            period: 分析周期描述
        
        Returns:
            InsightResult 或 None
        """
        try:
            # 构建数据摘要
            summary_data = self._build_summary(transactions)
            user_message = f"分析周期: {period}\n消费数据:\n{json.dumps(summary_data, ensure_ascii=False, indent=2)}"
            
            response = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": INSIGHT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            result_text = response.choices[0].message.content.strip()
            
            if result_text.startswith("```"):
                result_text = result_text.replace("```json", "").replace("```", "").strip()
            
            data = json.loads(result_text)
            
            return InsightResult(
                summary=data.get("summary", ""),
                warnings=data.get("warnings", []),
                suggestions=data.get("suggestions", [])
            )
            
        except Exception as e:
            print(f"[AI Agent] 分析失败: {e}")
            return None
    
    def _build_summary(self, transactions: list[dict]) -> dict:
        """构建交易数据摘要"""
        total_expense = 0
        total_income = 0
        by_category = {}
        
        for tx in transactions:
            amount = tx.get("amount", 0)
            category = tx.get("category", "other")
            tx_type = tx.get("type", "expense")
            
            if tx_type == "expense":
                total_expense += amount
                by_category[category] = by_category.get(category, 0) + amount
            else:
                total_income += amount
        
        return {
            "total_expense": total_expense,
            "total_income": total_income,
            "balance": total_income - total_expense,
            "by_category": by_category,
            "transaction_count": len(transactions)
        }


# ================= 单例实例 =================

_agent_instance: Optional[FinanceAgent] = None


def get_agent() -> FinanceAgent:
    """获取 Agent 单例"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = FinanceAgent()
    return _agent_instance


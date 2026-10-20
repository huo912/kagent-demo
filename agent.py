"""kagent BYO 示例 Agent:一个带计算器工具的最小 Python Agent。

该 Agent 使用 KAgent 的 BYO(Bring Your Own)模式:
- 通过 A2A 协议对外提供服务,监听 0.0.0.0:8080
- 部署到 k8s 后,kagent 控制器会自动注入 KAGENT_URL / KAGENT_NAME / KAGENT_NAMESPACE
  环境变量,并自动创建 Deployment 与 Service。
- /health 与 /.well-known/agent-card.json 等端点由 KAgentApp.build() 自动注册。
"""

import logging
import os

# 本地直接运行时回退值(仅当环境变量未设置时生效;在 k8s 集群中,
# kagent 控制器注入的 KAGENT_URL / KAGENT_NAME / KAGENT_NAMESPACE 优先,不会被覆盖)。
# 注意:必须在 import kagent 之前设置,因为 kagent.core 在导入时会缓存这些环境变量。
os.environ.setdefault("KAGENT_URL", "http://localhost:8083")
os.environ.setdefault("KAGENT_NAME", "basic-agent")
os.environ.setdefault("KAGENT_NAMESPACE", "default")

from a2a.types import AgentCard
from agents.agent import Agent
from agents.tool import function_tool
from kagent.core import KAgentConfig
from kagent.openai import KAgentApp

logger = logging.getLogger(__name__)


@function_tool
def calculate(expression: str) -> str:
    """计算一个数学表达式并返回结果。

    Args:
        expression: 要计算的数学表达式(例如 "2 + 2"、"10 * 5")

    Returns:
        计算结果字符串
    """
    try:
        # 注意:生产环境应使用安全的表达式解析器
        result = eval(expression, {"__builtins__": {}}, {})
        return f"{expression} 的计算结果是 {result}"
    except Exception as e:
        return f"计算 {expression} 出错: {e}"


# 构建 OpenAI Agents SDK 的 Agent,绑定工具
# 如需指定模型,加 model 参数,例如: model="gpt-4o-mini"
# (base_url 由 OPENAI_API_BASE 环境变量控制,见 agent.yaml)
agent = Agent(
    name="BasicAssistant",
    instructions="你是一个乐于助人的助手,可以使用工具来解决问题,例如用 calculate 工具做数学计算。",
    tools=[calculate],
)

# A2A 协议要求的 AgentCard 元数据
agent_card = AgentCard(
    name="basic-agent",
    description="一个带计算器工具的最小 KAgent BYO Python Agent",
    url="localhost:8080",
    version="0.1.0",
    capabilities={"streaming": True},
    defaultInputModes=["text"],
    defaultOutputModes=["text"],
    skills=[
        {
            "id": "basic",
            "name": "Basic Assistant",
            "description": "能做数学计算的小助手",
            "tags": ["calculator"],
        }
    ],
)

# KAgentConfig 读取 KAGENT_* 环境变量(集群中由 kagent 控制器自动注入)
config = KAgentConfig()

# 构建 KAgentApp 与底层 FastAPI 应用(A2A + /health + AgentCard 自动注册)
app = KAgentApp(agent=agent, agent_card=agent_card, config=config)
fastapi_app = app.build()


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    logger.info("Starting kagent demo basic agent on http://0.0.0.0:8080")
    uvicorn.run(fastapi_app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))

# kagent-demo-basic-agent

一个**最小但流程完整**的示例:用 Python 写一个 Agent,打包成镜像,部署到运行 **kagent** 的 Kubernetes 集群。

- **Agent 框架**: [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) + [kagent-openai](https://pypi.org/project/kagent-openai/)
- **部署模式**: kagent **BYO (Bring Your Own)** —— 你提供镜像,kagent 控制器负责创建 Deployment/Service 并注入环境变量
- **对外协议**: A2A (Agent-to-Agent),监听 `8080` 端口
- **功能**: 一个 `calculate` 计算器工具,演示 Agent + Tool 的完整链路

---

## 目录结构

```
.
├── agent.py          # Python Agent 源码(工具 + Agent + KAgentApp)
├── pyproject.toml    # 项目与依赖声明
├── uv.lock           # 锁定依赖(保证镜像构建可复现)
├── Dockerfile        # 多阶段构建镜像
├── agent.yaml        # kagent BYO Agent 部署清单 (kagent.dev/v1alpha2)
└── README.md         # 本文档
```

---

## 一、前置条件

| 工具 | 用途 |
|------|------|
| Python ≥ 3.11 | 本地运行 Agent |
| [uv](https://docs.astral.sh/uv/) | 依赖管理与锁定 |
| Docker | 构建镜像 |
| 一个镜像仓库 | 存放镜像(如 Docker Hub / GHCR / 本地 registry) |
| Kubernetes 集群 | 部署目标 |
| [kagent](https://kagent.dev) | 集群中的 Agent 运行时(已安装) |
| kubectl | 应用部署清单 |

---

## 二、本地运行(可选,验证代码)

```bash
uv sync
uv run python agent.py
```

启动后:

- 健康检查: `curl http://localhost:8080/health`
- Agent 卡片: `curl http://localhost:8080/.well-known/agent-card.json`
- 交互文档: 浏览器打开 `http://localhost:8080/docs`

> 本地运行时,`agent.py` 会使用回退的 `KAGENT_URL/KAGENT_NAME/KAGENT_NAMESPACE` 环境变量;
> 部署到集群后,这些变量由 kagent 控制器自动注入,无需手动设置。

---

## 三、构建镜像

```bash
# 1. 构建镜像(多阶段构建,产物最小化)
docker build -t <your-registry>/kagent-demo-basic-agent:0.1.0 .

# 2. 推送到镜像仓库
docker push <your-registry>/kagent-demo-basic-agent:0.1.0
```

> 本地无 registry 时,可先起一个本地 registry 用于测试:
> ```bash
> docker run -d -p 5001:5000 --name registry registry:2
> docker build -t localhost:5001/kagent-demo-basic-agent:latest .
> docker push localhost:5001/kagent-demo-basic-agent:latest
> ```

---

## 四、部署到 kagent 集群

### 1. 创建 LLM 凭据 Secret

Agent 处理消息时需调用 LLM,先在集群中创建 Secret:

```bash
kubectl create secret generic kagent-openai \
  --from-literal=OPENAI_API_KEY=<your-openai-api-key>
```

> **自定义 LLM 地址(base_url)**:如需使用 OpenAI 兼容网关(Azure AI Foundry、LiteLLM、vLLM、Ollama 等),
> 在 [agent.yaml](./agent.yaml) 的 `spec.byo.deployment.env` 中取消注释并设置 `OPENAI_API_BASE`。
> kagent 检测到 `OPENAI_API_BASE` + `OPENAI_API_KEY` 后会自动创建指向该地址的客户端,
> 并切换为 `chat_completions` 模式;不设置则默认走 `https://api.openai.com`。

### 2. 修改镜像地址

编辑 [agent.yaml](./agent.yaml),把 `spec.byo.deployment.image` 改成你的镜像地址:

```yaml
spec:
  type: BYO
  byo:
    deployment:
      image: <your-registry>/kagent-demo-basic-agent:0.1.0
```

### 3. 应用清单

```bash
kubectl apply -f agent.yaml
```

kagent 控制器会:

- 自动创建 **Deployment** 与 **Service**
- 向 Pod 注入 `KAGENT_URL` / `KAGENT_NAME` / `KAGENT_NAMESPACE` 环境变量
- 通过 `/health` 端点做健康检查

### 4. 验证部署

> kagent 控制器为每个 Agent 创建的 Deployment/Service/Pod 统一打标签
> `app=kagent` + `kagent=<agent名>`,以下命令均基于此。

```bash
# 1) 查看 Agent 资源(确认控制器已接管)
kubectl get agents
kubectl describe agent basic-agent

# 2) 查看控制器创建的 Deployment / Service / Pod
kubectl get deploy,svc,pod -l kagent=basic-agent

# 3) 查看 Pod 日志(应看到 uvicorn 启动、A2A 端点就绪)
kubectl logs -l kagent=basic-agent -f

# 4) 端口转发后验证端点
kubectl port-forward svc/basic-agent 8080:8080
curl http://localhost:8080/health                                  # 期望: OK
curl http://localhost:8080/.well-known/agent-card.json            # 期望: AgentCard JSON
```

**5) 端到端对话验证(让 Agent 调用 calculate 工具)**

A2A 协议是 JSON-RPC,直接 POST `message/send`:

```bash
curl -s http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "messageId": "m-1",
        "role": "user",
        "parts": [{ "kind": "text", "text": "请用计算器计算 12 * 8" }]
      }
    }
  }'
```

期望响应中 `result.message.parts` 包含类似 `12 * 8 的计算结果是 96` 的文本
(说明 LLM 成功调用了 `calculate` 工具)。

> 若响应是 LLM 报错(如 401/404),检查 `OPENAI_API_KEY` / `OPENAI_API_BASE`
> 是否配置正确,以及 Pod 能否访问该 LLM 地址。

---

## 五、在 kagent 中使用该 Agent

### 聊天界面在哪里?

kagent 自带一个 **Web UI**(Next.js 应用),随 Helm chart 一起部署,
Service 名为 **`kagent-ui`**(在 `kagent` 命名空间,端口 8080)。
部署完成后,你的 Agent 会出现在 UI 的 Agent 列表中,选中即可对话。

**方式 1:端口转发(本地开发最常用)**

```bash
kubectl port-forward -n kagent service/kagent-ui 8082:8080
# 浏览器打开
http://localhost:8082
```

**方式 2:kagent CLI(仅 macOS/Linux 自动开浏览器)**

```bash
kagent dashboard
```

**方式 3:集群内/生产环境**

- 默认 Service 是 `ClusterIP`,集群外不可直接访问。
- 如需外部访问,可配置 Ingress/Gateway(模板 `ui-httproute.yaml` 支持
  Gateway API),或临时改为 `ui.service.type: NodePort/LoadBalancer`。

> 默认未启用 SSO(`oauth2-proxy.enabled: false`),直接打开即可使用;
> 生产环境建议启用 `oauth2-proxy` 做认证。

### 对话验证

在 UI 的 Agent 列表中找到 `basic-agent`,发送"请用计算器计算 12 * 8",
期望回复包含 `12 * 8 的计算结果是 96`。

---

## 六、清理

```bash
kubectl delete -f agent.yaml
```

---

## 参考

- [kagent 官方 BYO 示例](https://github.com/kagent-dev/kagent/tree/release/v0.10.x/python/samples/openai/basic_agent)
- [kagent 文档](https://kagent.dev)
- [OpenAI Agents SDK](https://github.com/openai/openai-agents-python)

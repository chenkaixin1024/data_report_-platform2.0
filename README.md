# 📊 数据分析报告生成器

LLM 驱动的数据分析报告生成工具。上传 Excel 数据，AI 自主规划分析步骤、执行 Python 代码、生成 ECharts 可视化报告。

## 特性

- 🤖 **自主 Agent 循环** — LLM 作为独立决策者，自主制定计划、调用工具、决定何时结束
- 📊 **丰富可视化** — ECharts 图表、Markdown 文本、Mermaid 流程图
- 💻 **动态代码执行** — Python 代码沙箱执行，实时返回结果
- 🔄 **流式输出** — 后端推送结构化事件，前端实时渲染
- 🎨 **简洁 UI** — Shadcn/ui 构建，支持多类型内容分开显示

## 架构

```
Frontend (Next.js + Shadcn/ui)     Backend (Python FastAPI)
├── Upload Panel                   ├── /api/upload     文件上传
├── Thinking Block (思考过程)      ├── /api/analyze    SSE 流式分析
├── Code Block (代码 + 输出)       ├── Agent Loop      自主决策循环
├── Chart Block (ECharts)          ├── run_code        Python 执行沙箱
├── Markdown Block (文本分析)      ├── Protocol Parser 流协议解析器
└── Mermaid Block (流程图)         └── LLM Client      OpenAI 兼容接口
```

## 流式协议

LLM 输出使用显式标签进行层次化标记：

```text
<<<THINKING>>>  推理内容     <<<END_THINKING>>>
<<<PLAN>>>      计划步骤     <<<END_PLAN>>>
<<<CODE>>>      Python 代码  <<<END_CODE>>>
<<<CHART>>>     ECharts 配置 <<<END_CHART>>>
<<<MARKDOWN>>>  Markdown 文本 <<<END_MARKDOWN>>>
<<<MERMAID>>>   Mermaid 图   <<<END_MERMAID>>>
<<<FINISH>>>    最终总结     <<<END_FINISH>>>
```

后端协议解析器在流读取过程中将长文本切分为结构化事件，再通过 SSE 分发给前端对应 UI 模块。

## 快速开始

### 1. 配置 LLM API

编辑 `backend/.env`：

```bash
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
```

支持任何 OpenAI 兼容 API（DeepSeek、Moonshot、Ollama 等），详见 `backend/.env.example`。

### 2. 安装依赖

```bash
# 后端
pip3 install -r backend/requirements.txt

# 前端
cd frontend && npm install
```

### 3. 启动服务

**方式一：一键启动**
```bash
chmod +x start.sh
./start.sh
```

**方式二：手动启动**
```bash
# 后端 (端口 8000)
cd backend && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 前端 (端口 3001)
cd frontend && npm run dev
```

### 4. 使用

1. 打开 http://localhost:3001
2. 上传 Excel/CSV 文件（或使用 `sample_data.xlsx` 测试数据）
3. 输入分析需求
4. 点击"开始分析"

## 项目结构

```
data_report_demo_2/
├── backend/
│   ├── main.py              # FastAPI 应用
│   ├── agent.py             # LLM Agent 循环
│   ├── run_code.py          # Python 代码执行沙箱
│   ├── protocol.py          # 流协议解析器
│   ├── llm_client.py        # OpenAI 兼容 LLM 客户端
│   ├── prompts.py           # 系统提示词
│   ├── config.py            # 配置管理
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── app/             # Next.js 页面
│       ├── components/
│       │   ├── upload-panel.tsx      # 文件上传面板
│       │   ├── analysis-stream.tsx   # 流式分析容器
│       │   ├── thinking-block.tsx    # 思考过程
│       │   ├── code-block.tsx        # 代码 + 执行结果
│       │   ├── chart-block.tsx       # ECharts 图表
│       │   ├── markdown-block.tsx    # Markdown 渲染
│       │   ├── mermaid-block.tsx     # Mermaid 流程图
│       │   └── ui/                   # Shadcn/ui 组件
│       └── lib/
│           └── sse-client.ts         # SSE 客户端
├── sample_data.xlsx         # 测试数据
└── start.sh                 # 一键启动脚本
```

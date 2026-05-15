# 📝 智能作业批改系统 (Homework Correcting)

基于 AI 大模型 + OCR 的智能作业批改系统，支持拍照上传试题图片，自动识别题目并进行智能批改、评分与解析。

## ✨ 功能特性

- **AI 智能批改**：上传作业图片，AI 自动识别题目并批改，给出评分和详细解析
- **OCR 文字识别**：集成 RapidOCR，支持本地 OCR 预处理，提升识别准确率
- **历史题目管理**：查看所有历史批改中的题目，按单题维度展示
- **题库收藏**：从历史题目中选择收藏到个人题库
- **随机训练**：从题库中乱序抽题练习，支持文本作答与自动对答案
- **批改记录**：保存每次批改的详细记录，支持下载 Markdown 格式报告

## 🛠 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| AI 模型 | LangChain + OpenAI 兼容 API |
| OCR 引擎 | RapidOCR (ONNX Runtime) |
| 前端 | Vue 3 (CDN) + Element Plus |
| 包管理 | uv (Python ≥ 3.13) |

## 📁 项目结构

```
homework-correcting/
├── src/
│   ├── agents/          # AI Agent 智能体
│   │   └── homework_agent.py
│   ├── api/             # FastAPI 路由
│   │   └── routes.py
│   ├── models/          # 数据模型
│   │   └── schemas.py
│   ├── services/        # 服务层（图像处理、OCR）
│   │   ├── image_service.py
│   │   └── ocr_service.py
│   ├── config.py        # 配置管理
│   └── main.py          # 应用入口
├── static/              # 前端静态文件
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
├── uploads/             # 批改记录存储
├── .env.example         # 环境变量模板
├── pyproject.toml       # 项目依赖配置
└── README.md
```

## 🚀 快速开始

### 1. 环境要求

- Python ≥ 3.13
- [uv](https://docs.astral.sh/uv/) 包管理器

### 2. 安装依赖

```bash
uv sync
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

```env
# 模型配置（支持 OpenAI 兼容的 API）
MODEL_API_KEY=your-api-key-here
MODEL_NAME=your-model-name
MODEL_BASE_URL=https://your-api-url/v1

# 应用配置
HOST=0.0.0.0
PORT=8000
DEBUG=False

# OCR 配置（设为 True 启用本地 OCR 预处理）
OCR_ENABLED=True
```

### 4. 启动服务

```bash
uv run python -m src.main
```

服务启动后访问 http://localhost:8000 即可使用。

## 📖 使用说明

1. **作业批改**：点击上传区域或拖入试题图片，AI 将自动识别并批改
2. **历史题目**：查看所有已批改过的题目，可将题目加入题库
3. **题库**：管理收藏的题目，支持清空操作
4. **训练**：设置出题数量，从题库乱序抽题，输入答案后点击"对答案"查看结果

## 📄 License

MIT

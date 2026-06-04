# 修改日志

**日期**: 2026-06-04 16:00

---

### 1. `init_db.py` — 新增 dotenv 支持

**修改内容**: 在文件头部新增两行：
```python
from dotenv import load_dotenv
load_dotenv()
```

**修改原因**: `init_db.py` 原本只从系统环境变量读取配置，不会自动加载项目 `.env` 文件。添加 `load_dotenv()` 后，脚本启动时自动读取 `.env` 中的 `MYSQL_PASSWORD` 等变量，无需每次手动传 `--password` 参数。

---

### 2. `.env` — 修复注释语法

**修改内容**: 第 17 行 `MYSQL_PORT=3306  //端口` 改为 `MYSQL_PORT=3306  #端口`

**修改原因**: dotenv 不支持 `//` 注释语法，`3306  //端口` 整段被当作端口号的值，导致 `int()` 转换时报错 `ValueError`。改用 `#` 注释即可正常解析。

---

### 3. `.env` — API 更换为 Kimi

**修改内容**: 
- `MODEL_API_KEY` 更换为 Kimi API Key
- `MODEL_NAME` 由 `qwen-vl-max-latest` 改为 `moonshot-v1-auto`
- `MODEL_BASE_URL` 由 `https://dashscope.aliyuncs.com/compatible-mode/v1` 改为 `https://api.moonshot.cn/v1`

**修改原因**: 从阿里云百炼 API 切换至 Kimi (Moonshot) API。Kimi 使用 OpenAI 兼容格式，`moonshot-v1-auto` 会根据上下文长度自动选择合适模型。

---

### 4. AI 出题模块优化

**修改内容**:
- `static/js/app.js`:
  - 新增 `abortController` 和 `addedGeneratedKeys` 状态
  - `generateQuestions()` 支持 AbortController 取消请求
  - 新增 `cancelGeneration()` 终止生成函数
  - `addGeneratedToBank()` 加入题库后标记为已加入
  - 新增 `isGeneratedAdded()` 判断题目是否已加入
  - 导出 `cancelGeneration`、`isGeneratedAdded`
- `static/index.html`:
  - 出题按钮区域改为双按钮布局："生成题目" + "终止生成"
  - "加入题库"按钮改为与历史题目一致的 `已加入` 禁用样式
  - `app.js` 版本号 `v21` → `v22`
- `static/css/style.css`:
  - 新增 `.ai-generate-buttons` 样式，对齐首页 `.submit-area`
  - 新增移动端响应式规则

**修改原因**: 优化 AI 出题体验——允许用户中断耗时较长的生成过程，加入题库后提供明确视觉反馈，按钮样式保持与首页一致。

---

### 5. 训练模块改造 — 乱序抽题 + Word 导出试卷

**修改内容**:
- `static/js/app.js`:
  - 删除旧训练状态 (`trainingActive`, `trainingCount`, `trainingQuestions`, `trainingChecked`, `trainingScore`)
  - 删除旧函数 (`startTraining`, `checkTrainingAnswers`, `endTraining`)
  - 新增 `examPaperCount`, `examPaperQuestions` 状态
  - 新增 `generateExamPaper()` — 乱序抽题组卷
  - 新增 `downloadExamPaper()` — POST 题目数据到后端，blob 下载
  - 保留 `shuffleArray()`
- `static/index.html`:
  - 训练页面重写：未出卷（选择数量 + 生成）→ 已出卷（预览 + 导出/重新生成）
  - 新增 `examPaperSubject` 选择科目（不限/语文/数学），`getQuestionSubject()` 通过文件名+题目文本关键词自动判定科目
  - `app.js` 版本号 `v22` → `v24`
- `static/css/style.css`:
  - 删除旧训练样式，新增 `.exam-paper-*` 系列样式
  - 新增移动端响应式规则
- `src/api/routes.py`:
  - 新增 `POST /api/exam-paper/export` 端点，接收题目列表，用 python-docx 生成试卷 Word（题目在前，答案在后）

**修改原因**: 训练模块从"在线答题对答案"改为"乱序抽题组卷 → 导出 Word"，更贴合实际使用场景（打印试卷/分发练习）。

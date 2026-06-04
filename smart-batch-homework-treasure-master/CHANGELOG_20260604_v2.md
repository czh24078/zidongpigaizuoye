# 修改日志

**日期**: 2026-06-04 19:00

---

### 1. 训练模块 — 删除前端关键词科目识别，改用数据库 `subject` 字段

**修改内容**:
- `static/js/app.js`:
  - 删除 `getQuestionSubject()` 函数（约 20 行关键词匹配逻辑）
  - `addToBank` 的 subject 回退值从 `getQuestionSubject(q)` 改为 `'其他'`
  - 新增 `examPaperAvailableCount` computed — 按数据库 `q.subject` 字段统计各科目可用题数
  - 导出 `examPaperAvailableCount`
- `static/index.html`:
  - `el-input-number` 的 `:max` 从 `questionBank.length` 改为 `examPaperAvailableCount`
  - 科目下拉 `@change` 时自动将数量 clamp 到可用范围
  - 选科目后显示"语文可用 X 题"
  - 科目可用数为 0 时禁用数量选择器和生成按钮，红色提示"该科目暂无可用题目"
  - `app.js` 版本号 `v26` → `v27`

**修改原因**: 数据库已有 `question_bank.subject` 字段（后端负责赋值），前端不再需要维护关键词匹配逻辑。删除后可避免关键词缺失（如历史科目无关键词导致无法识别）、子串重叠计分等问题。

---

### 2. 后端 — 删除 `SUBJECT_KEYWORDS` 关键词打分，`_guess_subject` 仅保留文件名匹配

**修改内容**:
- `src/api/routes.py`:
  - 删除 `SUBJECT_KEYWORDS` 字典（约 4 行，含语文/数学/物理关键词列表，历史科目关键词缺失）
  - `_guess_subject()` 简化为仅检查文件名是否含科目名（语文/数学/物理/历史），不再对题干文本做关键词打分
  - 文件名无法匹配时直接返回 `"其他"`

**修改原因**: 关键词打分准确率低——单字关键词（如"力"、"功"）在非物理题中也常见，导致误分类；历史科目关键词完全缺失；子串重叠造成重复计分。前端 `addToBank` 和 `addGeneratedToBank` 已直接传递已知科目，图片上传识别路径仅保留可靠的文件名匹配作为 fallback。

---

### 3. 数据库 — 修复 5 道误标为"其他"的数学题

**修改内容**:
- `question_bank` 表：`UPDATE question_bank SET subject='数学' WHERE subject='其他'`（id 14/15/16/20/22，均为四则运算、几何、购物计算等数学题）

**修改原因**: 这些题入库时前端 `addGeneratedToBank` 未传 `subject` 字段，后端 fallback 为"其他"。修复后数学从 2 题变为 7 题。

---

### 4. 训练模块 — 修复科目下拉切换导致无法生成试卷的 bug

**修改内容**:
- `static/index.html`: 科目 `el-select` 的 `@change` 从 `examPaperCount = Math.min(examPaperCount, examPaperAvailableCount)` 改为 `examPaperCount = examPaperAvailableCount > 0 ? Math.min(examPaperCount, examPaperAvailableCount) : examPaperCount`

**修改原因**: 用户选择无可选题目的科目（如历史，可用 0 题）时，`Math.min(n, 0)` 将 `examPaperCount` 归零。再切回有题目的科目时 `Math.min(0, m) = 0`，导致抽 0 道题无任何反应。改为仅在可用题数 > 0 时才调整数量。

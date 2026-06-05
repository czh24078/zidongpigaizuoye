import asyncio
import json
import logging
import os
import re
from typing import List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from src.config import config
from src.services.image_service import image_to_base64, get_image_media_type
from src.services.ocr_service import ocr_image, ocr_available

logger = logging.getLogger(__name__)

# ======================================================================
# Prompt 定义
# ======================================================================

# 批改作业（无标准答案）
SYSTEM_PROMPT = """你是一位严谨的专业教师，请批改作业。批改必须客观、准确、一致。

【逐题全覆盖——最高优先级，违反此条即为批改失败】
1. **必须批改图片中出现的每一道题**，无论题目多少（5题、10题、20题），一题都不能漏。
2. 在报告开头先声明"共识别到 N 道题"，然后逐一批改全部 N 道题。
3. **严禁以"其余题目类似"、"省略"、"略"等任何理由跳过题目**。
4. 输出必须包含图片中所有题目的完整批改，缺一不可。

【核心禁令】
1. **严禁丢弃数字**：题目中的质量、体积、密度等数值必须完整保留，严禁出现 ".kg"、"/" 等残缺表达。如果 OCR 识别不清，请根据物理常识补全（如 0.54kg）。
2. **严禁省略分数**：每题得分必须明确写出，如 [15/20]。
3. **严禁摇摆不定**：同一份作业，每次批改必须给出完全一致的判定和分数。
4. **选择题必须给确定答案**：单选题只能有一个正确选项，逐一排除错误选项后确认，不得模棱两可。

【选择题批改流程】
1. 先独立解出题目的正确答案。
2. 再对照学生的选择，判断是否一致。
3. 在解析中说明每个选项为什么对/错。

【输出模板】
## 1. 识别题目（共 N 题）
1. (完整题干，含所有选项——确保数字准确)
2. (完整题干，含所有选项——确保数字准确)
...（列出全部 N 题）

## 2. 评分
总分：**X / 100**

## 3. 答案及解析
- **第1题**：**[15/20]** ✅
  - **答案**：不能。
  - **解析**：G=mg=0.54kg×10N/kg=5.4N > 5N，超量程。
- **第2题**：**[10/20]** ❌
  - **答案**：28N。
  - **解析**：体积单位错误，应为 m³。
...（逐题批改全部 N 题，不可跳过任何一题）

【注意】
- 即使为了简洁，也不能牺牲数字的准确性。
- 解析要简短，但公式中的数字必须齐全。

【输出末尾】请在批改报告最后一行，直接以纯文本输出一段 JSON 逐题详情（严禁使用任何代码块、严禁用 ``` 包裹）：
[{"question_no": "1", "question_text": "完整题干", "student_answer": "学生答案", "standard_answer": "正确标准答案", "is_correct": true, "score": 15, "full_score": 20, "analysis": "简要解析"}]
（输出 JSON 后立即结束，不要附加任何额外内容）"""

# 从试题图片中提取题目并生成标准答案（图片模式）
EXTRACT_EXAM_PROMPT = """你是一位严谨的学科老师。请识别图片中的题目并生成标准答案。

【核心原则——必须遵守】
1. **逐字精读**：仔细阅读图片中的每一个字、每一个符号、每一个数字，不得遗漏或篡改。
2. **选择题选项**：对于选择题，必须完整抄录所有选项（A. B. C. D.），并标注正确选项。
3. **公式与数字**：数学公式、物理量、单位必须原样保留，严禁四舍五入或近似。
4. **如有模糊处**：根据上下文和学科常识合理推断，推断结果标注在 analysis 字段中。
5. **不可臆造**：无法识别的内容留空，不要自行编造。

【输出】严格以 JSON 数组返回，不要输出任何解释性文字。
[
  {
    "question_no": "1",
    "question_text": "修正后的完整题干（含所有选项）",
    "standard_answer": "标准答案",
    "options": "A. xxx  B. xxx  C. xxx  D. xxx（选择题必填）",
    "analysis": "简要解题要点，如有推断注明推断依据",
    "subject": "语文/数学/物理/历史/其他"
  }
]
"""

# 从试题图片中提取题目并生成标准答案（OCR 文字模式）
EXTRACT_EXAM_OCR_PROMPT = """你是一位严谨的学科老师，擅长审题与出标准答案。以下是通过 OCR 从试题图片中识别出的文字内容，请根据这些文字为每道题目整理出权威的标准答案。

说明：
- OCR 识别可能存在误差（如空格、符号错误、顺序紊乱等），请结合上下文智能纠正。
- 可能包含多张图片的 OCR 结果，它们可能是"题目卷"、"答案卷"或"题目+答案合卷"。
- 请综合所有图片的 OCR 内容进行分析。

要求：
1. 忠实还原每道题目的题号与题干文本（公式可用 LaTeX 或文字描述）。
2. 为每题给出明确、正确的"标准答案"。
3. 为每题补充简要的"解题分析/要点"（可选，若题目较简单可留空字符串）。
4. 严格以 JSON 数组返回，不要输出任何其它解释、前后缀或代码块围栏；若必须使用代码块，请使用 ```json 包裹。

JSON 结构（每个元素必须包含以下字段）：
[
  {
    "question_no": "1",
    "question_text": "题目原文",
    "standard_answer": "标准答案",
    "analysis": "解题要点（可为空字符串）",
    "subject": "语文/数学/物理/历史/其他"
  }
]
"""

# 基于标准答案的结构化批改（图片模式）
CORRECT_WITH_ANSWERS_PROMPT = """你是专业教师，根据标准答案批改作业。批改必须客观、准确、一致。

【逐题全覆盖——最高优先级，违反此条即为批改失败】
1. **标准答案中有多少道题，就必须批改多少道题**，逐题对照，一题都不能漏。
2. 在 summary 中声明"共批改 N 道题"，details 数组必须包含全部 N 道题的批改结果。
3. **严禁以任何理由减少 details 数组中的题目数量**。

【严格禁令】
1. 禁止提及OCR或识别过程。
2. 仅返回 JSON，无任何多余文字。
3. 判定必须依据标准答案，不可主观臆断。

【选择题判定规则——极其重要】
- 学生答案与标准答案完全一致（忽略大小写和空格）→ is_correct: true
- 学生答案与标准答案不一致 → is_correct: false
- 单选题只有一个正确选项，不存在"部分正确"
- 在 analysis 中注明正确选项与学生的差异

输出 JSON 格式：
{
  "total_score": 85,
  "full_score": 100,
  "summary": "共批改N道题，一句话评语",
  "details": [
    {
      "question_no": "1",
      "question_text": "题干",
      "student_answer": "学生作答",
      "standard_answer": "标准答案",
      "is_correct": true,
      "score": 10,
      "full_score": 10,
      "analysis": "判定依据：学生答案与标准答案一致/不一致"
    }
  ],
  "suggestions": "建议"
}
"""

# 基于标准答案的结构化批改（OCR 文字模式）
CORRECT_WITH_ANSWERS_OCR_PROMPT = """你是专业教师，根据标准答案简洁批改OCR识别的作业。批改必须客观、准确、一致。

【逐题全覆盖——最高优先级，违反此条即为批改失败】
1. **标准答案中有多少道题，就必须批改多少道题**，逐题对照，一题都不能漏。
2. 在 summary 中声明"共批改 N 道题"，details 数组必须包含全部 N 道题的批改结果。
3. **严禁以任何理由减少 details 数组中的题目数量**。

【选择题判定规则——极其重要】
- 学生答案与标准答案完全一致（忽略大小写和空格）→ is_correct: true
- 学生答案与标准答案不一致 → is_correct: false
- 单选题无"部分正确"，判定必须明确

输出JSON格式（严格控制长度）：
{
  "total_score": 85,
  "full_score": 100,
  "summary": "共批改N道题，简短评语（30字内）",
  "details": [
    {
      "question_no": "1",
      "question_text": "题干简述",
      "student_answer": "学生答案",
      "standard_answer": "标准答案",
      "is_correct": true,
      "score": 10,
      "full_score": 10,
      "analysis": "判定依据（20字内）"
    }
  ],
  "suggestions": "1-2条建议（每条15字内）"
}

要求：
- 智能纠正OCR错误
- analysis字段必须基于标准答案给出判定依据
- 仅返回JSON，无其他文字"""

# 流式批改（有标准答案——图片模式）
CORRECT_WITH_ANSWERS_STREAM_PROMPT = """你是一位严谨的专业教师，请根据标准答案批改作业。批改必须客观、准确、一致。

【逐题全覆盖——最高优先级，违反此条即为批改失败】
1. **标准答案中有多少道题，就必须批改多少道题**，逐题对照，一题都不能漏。
2. 在报告开头声明"共 N 道题"，表格必须包含全部 N 道题。
3. **严禁以任何理由减少表格中的行数**。

【严格禁令】
1. 禁止提及OCR或识别过程。
2. 严禁丢弃数字，确保每个数值完整准确。
3. 判定必须严格依据标准答案，不可主观臆断。

【选择题判定规则——极其重要】
- 学生答案与标准答案完全一致 → ✅ | 不一致 → ❌
- 单选题只有一个正确选项，不存在"部分正确"
- 分析中注明正确选项与学生选择的差异

【输出模板】
## 作业批改报告

### 总分：X / 100

> 一句话评语

### 逐题批改（共 N 题）

| 题号 | 学生答案 | 标准答案 | 判定 | 得分 | 分析 |
|------|----------|----------|------|------|------|
| 1 | 学生作答 | 标准答案 | ✅/❌ | 10/10 | 判定依据 |
（表格必须包含全部 N 行，缺一不可）

> 改进建议

【输出末尾】请在批改报告最后一行，直接以纯文本输出一段 JSON 逐题详情（严禁使用任何代码块、严禁用 ``` 包裹）：
[{"question_no": "1", "question_text": "完整题干", "student_answer": "学生答案", "standard_answer": "标准答案", "is_correct": true, "score": 10, "full_score": 10, "analysis": "判定依据"}]
（输出 JSON 后立即结束，不要附加任何额外内容）"""

# 流式批改（有标准答案——OCR 文字模式）
CORRECT_WITH_ANSWERS_STREAM_OCR_PROMPT = """你是一位严谨的专业教师，请根据标准答案批改OCR识别的作业。批改必须客观、准确、一致。

【逐题全覆盖——最高优先级，违反此条即为批改失败】
1. **标准答案中有多少道题，就必须批改多少道题**，逐题对照，一题都不能漏。
2. 在报告开头声明"共 N 道题"，表格必须包含全部 N 道题。
3. **严禁以任何理由减少表格中的行数**。

【严格禁令】
1. 禁止提及OCR或识别过程。
2. 严禁丢弃数字，确保每个数值完整准确。
3. 智能纠正OCR识别错误。
4. 判定必须严格依据标准答案，不可主观臆断。

【选择题判定规则——极其重要】
- 学生答案与标准答案完全一致 → ✅ | 不一致 → ❌
- 单选题只有一个正确选项，不存在"部分正确"

【输出模板】
## 作业批改报告

### 总分：X / 100

> 一句话评语

### 逐题批改（共 N 题）

| 题号 | 学生答案 | 标准答案 | 判定 | 得分 | 分析 |
|------|----------|----------|------|------|------|
| 1 | 学生作答 | 标准答案 | ✅/❌ | 10/10 | 判定依据 |
（表格必须包含全部 N 行，缺一不可）

> 改进建议

【输出末尾】请在批改报告最后一行，直接以纯文本输出一段 JSON 逐题详情（严禁使用任何代码块、严禁用 ``` 包裹）：
[{"question_no": "1", "question_text": "完整题干", "student_answer": "学生答案", "standard_answer": "标准答案", "is_correct": true, "score": 10, "full_score": 10, "analysis": "判定依据"}]
（输出 JSON 后立即结束，不要附加任何额外内容）"""

# 无标准答案批改（OCR 文字模式）
SYSTEM_PROMPT_OCR = """你是一位严谨的专业教师，请批改以下作业。批改必须客观、准确、一致。

【逐题全覆盖——最高优先级，违反此条即为批改失败】
1. **必须批改OCR文字中出现的每一道题**，无论题目多少（5题、10题、20题），一题都不能漏。
2. 在报告开头先声明"共识别到 N 道题"，然后逐一批改全部 N 道题。
3. **严禁以"其余题目类似"、"省略"、"略"等任何理由跳过题目**。
4. 输出必须包含OCR文字中所有题目的完整批改，缺一不可。

【绝对禁令】
1. **禁止输出残缺数字**：如 ".kg"、"N"、"/" 是不允许的。必须补全为 "0.54kg"、"5N"、"15/20"。
2. **禁止提及 OCR 过程**。
3. **严禁摇摆不定**：同一份作业，每次批改必须给出完全一致的判定和分数。
4. **选择题必须给确定答案**：单选题只能有一个正确选项，逐一排除后确认。

【选择题批改流程】
1. 先独立解出正确答案。
2. 再对照学生的选择，判断是否一致。
3. 在解析中说明每个选项的对错原因。

【输出结构】
## 1. 识别题目（共 N 题）
(列出修正后的完整题目，确保每个数字都清晰可见，列出全部 N 题)

## 2. 评分
总分：**X / 100**

## 3. 答案及解析
- **第1题**：**[得分/满分]** [判定]
  - **答案**：[正确结果]
  - **解析**：[30字内核心理由，包含关键计算步骤]
（逐题批改全部 N 题，不可跳过任何一题）

请直接输出结果，确保公式和数值的完整性。

【输出末尾】请在批改报告最后一行，直接以纯文本输出一段 JSON 逐题详情（严禁使用任何代码块、严禁用 ``` 包裹）：
[{"question_no": "1", "question_text": "完整题干", "student_answer": "学生答案", "standard_answer": "正确标准答案", "is_correct": true, "score": 15, "full_score": 20, "analysis": "简要解析"}]
（输出 JSON 后立即结束，不要附加任何额外内容）"""

# AI 出题 Prompt
GENERATE_CHINESE_PROMPT = """你是一位资深语文教师，请生成{count}道{grade}语文练习题。

{requirement_block}
【难度要求】{difficulty}

【参考题型】
- 小学阶段：拼音与字词（看拼音写汉字、形近字辨析、多音字、近反义词）、成语与歇后语、修改病句、句式转换（把字句/被字句/反问句转陈述句）、修辞手法判断（比喻/拟人/排比/夸张）、古诗背诵与默写（课标必背篇目）、阅读短文回答问题、口语交际与写作表达
- 初中阶段：古诗文默写与鉴赏（诗句填空、作者/朝代、修辞赏析、情感分析）、文言文阅读（实词解释、虚词用法、句子翻译、内容理解）、现代文阅读（概括主旨、分析人物、理解词句含义、写作手法）、病句修改与成语运用、文学常识（作家作品、文体知识、名著阅读）、写作表达（句式转换、语言运用、作文片段）

【输出格式】严格以 JSON 数组返回，不要输出任何解释性文字。
[
  {{"question_no": "1", "question_text": "完整题干", "standard_answer": "标准答案", "analysis": "简要解析", "difficulty": "{difficulty}"}}
]"""

GENERATE_MATH_PROMPT = """你是一位资深数学教师，请生成{count}道{grade}数学练习题。

{requirement_block}
【难度要求】{difficulty}

【要求】
- 题目要有完整的题干（不能只有一句话）
- 计算题的数值要随机变化，不要每次出一样的数字

【参考知识点】
- 小学阶段：四则混合运算与简便计算、分数与小数的互化与运算、因数与倍数（质数/合数/最大公因数/最小公倍数）、单位换算（长度/面积/体积/重量/时间）、周长与面积（长方形/正方形/三角形/圆）、体积与表面积（长方体/正方体/圆柱）、百分数与比例应用题（折扣/利率/浓度）、方程初步（一元一次方程解应用题）、统计图与平均数
- 初中阶段：代数方程与不等式（一元一次/二次方程、方程组、不等式）、函数（一次函数、二次函数、反比例函数、图像与性质）、几何（三角形、四边形、圆、相似与全等、勾股定理、三角函数入门）、数与式（实数运算、因式分解、分式、二次根式）、概率统计（数据统计、概率计算）

【输出格式】严格以 JSON 数组返回，不要输出任何解释性文字。
[
  {{"question_no": "1", "question_text": "完整题干", "standard_answer": "标准答案", "analysis": "简要解析", "difficulty": "{difficulty}"}}
]"""

GENERATE_QUESTIONS_PROMPT = """你是一位资深学科教师，请根据以下要求生成练习题。

【要求】
科目：{subject}
年级：{grade}
题型：{question_type}
难度：{difficulty}
数量：{count} 道
{requirement_text}

【输出格式】严格以 JSON 数组返回，不要输出任何解释性文字。
[
  {{"question_no": "1", "question_text": "完整题干", "standard_answer": "标准答案", "analysis": "简要解析", "difficulty": "简单/中等/困难"}}
]"""



def _strip_json_fence(text: str) -> str:
    """去除 ```json ... ``` 代码块围栏。"""
    text = text.strip()
    if text.startswith("```"):
        # 去掉首行 ```json 或 ```
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_json_safely(text: str):
    """尽力解析 LLM 返回的 JSON。"""
    cleaned = _strip_json_fence(text)
    try:
        return json.loads(cleaned)
    except Exception:
        # 兜底：从中截取最外层 JSON
        m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                return None
        return None


class HomeworkAgent:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=config.MODEL_NAME,
            base_url=config.MODEL_BASE_URL,
            api_key=config.MODEL_API_KEY,
            temperature=0.0,
            timeout=300,
        )
        self._ocr_enabled = config.OCR_ENABLED and ocr_available()
        self._semaphore = asyncio.Semaphore(5)
        if self._ocr_enabled:
            logger.info("OCR 已启用，将先提取文字再交给大模型")
        else:
            logger.info("OCR 未启用，将直接使用图片多模态模式")

    # ------------------------------------------------------------------
    # 通用：构造多模态消息
    # ------------------------------------------------------------------
    def _build_image_message(self, file_path: str, text: str) -> HumanMessage:
        with open(file_path, "rb") as f:
            image_content = f.read()
        base64_image = image_to_base64(image_content)
        media_type = get_image_media_type(file_path)
        return HumanMessage(content=[
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{base64_image}"}}
        ])

    def _build_multi_image_message(self, file_paths: List[str], text: str) -> HumanMessage:
        """构造包含多张图片的消息。"""
        content = [{"type": "text", "text": text}]
        for fp in file_paths:
            with open(fp, "rb") as f:
                image_content = f.read()
            base64_image = image_to_base64(image_content)
            media_type = get_image_media_type(fp)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{base64_image}"}
            })
        return HumanMessage(content=content)

    # ------------------------------------------------------------------
    # OCR 预处理
    # ------------------------------------------------------------------
    async def _ocr_single(self, file_path: str) -> str:
        """对单张图片进行 OCR，返回识别文字。"""
        try:
            text = await asyncio.to_thread(ocr_image, file_path)
            if text.strip():
                return text
            logger.warning(f"OCR 未识别到文字: {file_path}")
            return ""
        except Exception as e:
            logger.error(f"OCR 失败: {file_path}, 错误: {e}")
            return ""

    async def _ocr_multiple(self, file_paths: List[str]) -> List[str]:
        """对多张图片进行 OCR，返回每张图片的识别文字。"""
        return [await self._ocr_single(fp) for fp in file_paths]

    async def _llm_invoke(self, messages):
        """带并发限流的 LLM 调用。"""
        async with self._semaphore:
            return await self._llm_invoke(messages)

    async def _llm_stream(self, messages):
        """带并发限流的 LLM 流式调用。"""
        async with self._semaphore:
            async for chunk in self._llm_stream(messages):
                yield chunk

    # ------------------------------------------------------------------
    # 提取试题 & 生成标准答案
    # ------------------------------------------------------------------
    async def extract_exam(self, file_paths: List[str]) -> List[dict]:
        """识别试题图片（支持多张），返回题目列表（含 AI 生成的标准答案）。"""
        file_paths = [fp for fp in file_paths if os.path.exists(fp)]
        if not file_paths:
            raise ValueError("未提供有效的图片路径")

        # OCR 模式：先提取文字再交给大模型
        if self._ocr_enabled:
            ocr_texts = await self._ocr_multiple(file_paths)
            # 检查是否有有效的 OCR 结果
            has_text = any(t.strip() for t in ocr_texts)
            if has_text:
                return await self._extract_exam_with_ocr(file_paths, ocr_texts)
            else:
                logger.warning("OCR 未识别到任何文字，回退到图片模式")

        # 图片模式（原有逻辑）
        if len(file_paths) == 1:
            msg = self._build_image_message(
                file_paths[0],
                "请识别这张试题图片并严格按要求输出 JSON。"
            )
        else:
            names = ", ".join(os.path.basename(fp) for fp in file_paths)
            msg = self._build_multi_image_message(
                file_paths,
                f"以下共 {len(file_paths)} 张图片，可能是题目卷与答案卷的组合，请综合分析并严格按要求输出 JSON。文件名：{names}"
            )

        messages = [SystemMessage(content=EXTRACT_EXAM_PROMPT), msg]
        response = await self._llm_invoke(messages)
        parsed = _parse_json_safely(response.content or "")
        if not isinstance(parsed, list):
            raise ValueError("模型返回内容无法解析为题目列表 JSON")
        # 规范字段
        normalized = []
        for i, q in enumerate(parsed, start=1):
            if not isinstance(q, dict):
                continue
            normalized.append({
                "question_no": str(q.get("question_no") or i),
                "question_text": str(q.get("question_text") or "").strip(),
                "standard_answer": str(q.get("standard_answer") or "").strip(),
                "analysis": str(q.get("analysis") or "").strip(),
                "subject": str(q.get("subject") or "").strip(),
            })
        return normalized

    async def _extract_exam_with_ocr(self, file_paths: List[str], ocr_texts: List[str]) -> List[dict]:
        """OCR 模式提取试题：将 OCR 文字发给大模型。"""
        # 拼接所有图片的 OCR 结果
        ocr_content_parts = []
        for i, (fp, text) in enumerate(zip(file_paths, ocr_texts), start=1):
            name = os.path.basename(fp)
            if text.strip():
                ocr_content_parts.append(f"--- 图片 {i}（{name}）OCR 识别结果 ---\n{text}")
            else:
                ocr_content_parts.append(f"--- 图片 {i}（{name}）OCR 识别结果 ---\n（未识别到文字）")
    
        ocr_combined = "\n\n".join(ocr_content_parts)
        prompt_text = (
            f"以下是从 {len(file_paths)} 张试题图片中通过 OCR 识别出的文字内容：\n\n"
            f"{ocr_combined}\n\n"
            "请根据以上 OCR 文字严格按要求输出 JSON。"
        )
        msg = HumanMessage(content=prompt_text)
        messages = [SystemMessage(content=EXTRACT_EXAM_OCR_PROMPT), msg]
    
        logger.info(f"使用 OCR 文字模式提取试题，共 {len(file_paths)} 张图片")
        response = await self._llm_invoke(messages)
        parsed = _parse_json_safely(response.content or "")
        if not isinstance(parsed, list):
            raise ValueError("模型返回内容无法解析为题目列表 JSON")
    
        normalized = []
        for i, q in enumerate(parsed, start=1):
            if not isinstance(q, dict):
                continue
            normalized.append({
                "question_no": str(q.get("question_no") or i),
                "question_text": str(q.get("question_text") or "").strip(),
                "standard_answer": str(q.get("standard_answer") or "").strip(),
                "analysis": str(q.get("analysis") or "").strip(),
                "subject": str(q.get("subject") or "").strip(),
            })
        return normalized

    # ------------------------------------------------------------------
    # 批改：无标准答案
    # ------------------------------------------------------------------
    async def correct(self, file_path: str, standard_answers: Optional[List[dict]] = None
                     ) -> tuple[str, Optional[int], Optional[List[dict]]]:
        """批改作业，返回 (markdown, score, details)。"""
        filename = os.path.basename(file_path)

        if standard_answers:
            return await self._correct_with_answers(file_path, standard_answers)

        # OCR 模式：先提取文字再交给大模型
        if self._ocr_enabled:
            ocr_text = await self._ocr_single(file_path)
            if ocr_text.strip():
                return await self._correct_with_ocr_text(file_path, ocr_text, filename)
            else:
                logger.warning("OCR 未识别到文字，回退到图片模式")

        # 图片模式（原有逻辑）
        msg = self._build_image_message(
            file_path,
            f"请批改这份作业（文件名：{filename}）："
        )
        messages = [SystemMessage(content=SYSTEM_PROMPT), msg]
        response = await self._llm_invoke(messages)
        result = response.content or ""
        result, details = self._extract_details_json(result)
        score = self._extract_score(result, details)
        return result, score, details

    async def _correct_with_ocr_text(self, file_path: str, ocr_text: str, filename: str
                                    ) -> tuple[str, Optional[int], Optional[List[dict]]]:
        """使用 OCR 文字进行无标准答案批改。"""
        prompt_text = (
            f"以下是通过 OCR 从学生作业图片（{filename}）中识别出的文字内容：\n\n"
            f"{ocr_text}\n\n"
            "请根据以上 OCR 识别内容批改这份作业。"
        )
        msg = HumanMessage(content=prompt_text)
        messages = [SystemMessage(content=SYSTEM_PROMPT_OCR), msg]

        logger.info(f"使用 OCR 文字模式批改作业: {filename}")
        response = await self._llm_invoke(messages)
        result = response.content or ""
        result, details = self._extract_details_json(result)
        score = self._extract_score(result, details)
        return result, score, details

    # ------------------------------------------------------------------
    # 批改：带标准答案（结构化输出 -> Markdown）
    # ------------------------------------------------------------------
    async def _correct_with_answers(self, file_path: str, standard_answers: List[dict]
                                   ) -> tuple[str, Optional[int], Optional[List[dict]]]:
        answers_json = json.dumps(standard_answers, ensure_ascii=False, indent=2)

        # OCR 模式
        if self._ocr_enabled:
            ocr_text = await self._ocr_single(file_path)
            if ocr_text.strip():
                return await self._correct_with_answers_ocr(file_path, standard_answers, ocr_text)
            else:
                logger.warning("OCR 未识别到文字，回退到图片模式")

        # 图片模式（原有逻辑）
        prompt_text = (
            f"试题标准答案（共 {len(standard_answers)} 道题，JSON）如下：\n{answers_json}\n\n"
            f"请严格按标准答案批改这份学生作业（文件名：{os.path.basename(file_path)}），"
            f"必须批改全部 {len(standard_answers)} 道题，一题都不能漏。仅返回规定结构的 JSON。"
        )
        msg = self._build_image_message(file_path, prompt_text)
        messages = [SystemMessage(content=CORRECT_WITH_ANSWERS_PROMPT), msg]

        response = await self._llm_invoke(messages)
        parsed = _parse_json_safely(response.content or "")
        if not isinstance(parsed, dict):
            score = self._extract_score(response.content or "")
            return response.content or "", score, None

        details = parsed.get("details") or []
        if not isinstance(details, list):
            details = []

        total_score = parsed.get("total_score")
        try:
            score = int(total_score) if total_score is not None else self._extract_score(
                json.dumps(parsed, ensure_ascii=False)
            )
        except Exception:
            score = None

        return self._render_details_markdown(parsed), score, details

    async def _correct_with_answers_ocr(
        self, file_path: str, standard_answers: List[dict], ocr_text: str
    ) -> tuple[str, Optional[int], Optional[List[dict]]]:
        """OCR 模式：带标准答案的结构化批改。"""
        answers_json = json.dumps(standard_answers, ensure_ascii=False, indent=2)
        prompt_text = (
            f"试题标准答案（共 {len(standard_answers)} 道题，JSON）如下：\n{answers_json}\n\n"
            f"以下是通过 OCR 从学生作业图片（{os.path.basename(file_path)}）中识别出的文字内容：\n\n"
            f"{ocr_text}\n\n"
            f"请严格按标准答案批改学生作答，必须批改全部 {len(standard_answers)} 道题。仅返回规定结构的 JSON。"
        )
        msg = HumanMessage(content=prompt_text)
        messages = [SystemMessage(content=CORRECT_WITH_ANSWERS_OCR_PROMPT), msg]

        logger.info(f"使用 OCR 文字模式 + 标准答案批改: {os.path.basename(file_path)}")
        response = await self._llm_invoke(messages)
        parsed = _parse_json_safely(response.content or "")
        if not isinstance(parsed, dict):
            score = self._extract_score(response.content or "")
            return response.content or "", score, None

        details = parsed.get("details") or []
        if not isinstance(details, list):
            details = []

        total_score = parsed.get("total_score")
        try:
            score = int(total_score) if total_score is not None else self._extract_score(
                json.dumps(parsed, ensure_ascii=False)
            )
        except Exception:
            score = None

        return self._render_details_markdown(parsed), score, details

    def _render_details_markdown(self, parsed: dict) -> str:
        """把结构化 JSON 转成 Markdown，包含每题得分。"""
        total = parsed.get("total_score")
        full = parsed.get("full_score") or 100
        summary = parsed.get("summary") or ""
        suggestions = parsed.get("suggestions") or ""
        details = parsed.get("details") or []

        lines = ["# 作业批改报告"]

        # 1. 识别题目部分（如果是带标准答案模式，通常题目已知，这里可以略过或简写）
        if details:
            lines.append("\n## 1. 识别题目")
            for d in details:
                lines.append(f"- **第{d.get('question_no')}题**：{d.get('question_text', '')}")

        # 2. 评分
        if total is not None:
            lines.append(f"\n## 2. 评分\n总分：**{total} / {full}**")

        if summary:
            lines.append(f"\n> {summary}\n")

        # 3. 答案及解析（表格形式展示每题得分）
        lines.append("\n## 3. 答案及解析\n")
        lines.append("| 题号 | 判定 | 每题得分 | 答案与解析 |")
        lines.append("|------|------|----------|------------|")
        for d in details:
            no = str(d.get("question_no", "")).replace("|", "\\|")
            ok = "✅" if d.get("is_correct") else "❌"
            sc = d.get("score")
            fs = d.get("full_score")
            sc_str = f"{sc}/{fs}" if sc is not None and fs is not None else "-"

            # 组合答案和解析
            content = f"**正确**: {d.get('standard_answer', '')}<br>**解析**: {str(d.get('analysis', ''))[:40]}"
            content = content.replace("|", "\\|").replace("\n", " ")

            lines.append(f"| {no} | {ok} | **{sc_str}** | {content} |")

        if suggestions:
            lines.append(f"\n## 改进建议\n\n{suggestions}\n")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 流式批改
    # ------------------------------------------------------------------
    async def correct_stream(self, file_path: str, standard_answers: Optional[List[dict]] = None):
        if not file_path:
            raise ValueError("未提供文件路径")
        filename = os.path.basename(file_path)
        full_content = ""

        # 如果有标准答案，使用 Markdown 流式批改模式
        if standard_answers:
            answers_json = json.dumps(standard_answers, ensure_ascii=False, indent=2)

            # OCR 模式
            if self._ocr_enabled:
                ocr_text = await self._ocr_single(file_path)
                if ocr_text.strip():
                    prompt_text = (
                        f"试题标准答案（共 {len(standard_answers)} 道题，JSON）如下：\n{answers_json}\n\n"
                        f"以下是通过 OCR 从学生作业图片（{filename}）中识别出的文字内容：\n\n"
                        f"{ocr_text}\n\n"
                        f"请严格按标准答案批改学生作答，必须批改全部 {len(standard_answers)} 道题。"
                    )
                    msg = HumanMessage(content=prompt_text)
                    messages = [SystemMessage(content=CORRECT_WITH_ANSWERS_STREAM_OCR_PROMPT), msg]

                    logger.info(f"流式批改使用 OCR + 标准答案模式: {filename}")
                    async for chunk in self._llm_stream(messages):
                        if chunk.content:
                            full_content += chunk.content
                            yield json.dumps({"event": "content", "text": chunk.content}, ensure_ascii=False)

                    stripped, details = self._extract_details_json(full_content)
                    score = self._extract_score(stripped, details)
                    yield json.dumps({"event": "final_text", "text": stripped}, ensure_ascii=False)
                    yield json.dumps({"event": "result", "score": score, "details": details}, ensure_ascii=False)
                    return

            # 图片模式 + 标准答案
            prompt_text = (
                f"试题标准答案（共 {len(standard_answers)} 道题，JSON）如下：\n{answers_json}\n\n"
                f"请严格按标准答案批改这份学生作业（文件名：{filename}），"
                f"必须批改全部 {len(standard_answers)} 道题。"
            )
            msg = self._build_image_message(file_path, prompt_text)
            messages = [SystemMessage(content=CORRECT_WITH_ANSWERS_STREAM_PROMPT), msg]

            logger.info(f"流式批改使用图片 + 标准答案模式: {filename}")
            async for chunk in self._llm_stream(messages):
                if chunk.content:
                    full_content += chunk.content
                    yield json.dumps({"event": "content", "text": chunk.content}, ensure_ascii=False)

            stripped, details = self._extract_details_json(full_content)
            score = self._extract_score(stripped, details)
            yield json.dumps({"event": "final_text", "text": stripped}, ensure_ascii=False)
            yield json.dumps({"event": "result", "score": score, "details": details}, ensure_ascii=False)
            return

        # 无标准答案模式（原有逻辑）
        # OCR 模式
        if self._ocr_enabled:
            ocr_text = await self._ocr_single(file_path)
            if ocr_text.strip():
                prompt_text = (
                    f"以下是通过 OCR 从学生作业图片（{filename}）中识别出的文字内容：\n\n"
                    f"{ocr_text}\n\n"
                    "请根据以上 OCR 识别内容批改这份作业。"
                )
                msg = HumanMessage(content=prompt_text)
                messages = [SystemMessage(content=SYSTEM_PROMPT_OCR), msg]

                logger.info(f"流式批改使用 OCR 文字模式: {filename}")
                async for chunk in self._llm_stream(messages):
                    if chunk.content:
                        full_content += chunk.content
                        yield json.dumps({"event": "content", "text": chunk.content}, ensure_ascii=False)

                stripped, details = self._extract_details_json(full_content)
                score = self._extract_score(stripped, details)
                yield json.dumps({"event": "final_text", "text": stripped}, ensure_ascii=False)
                yield json.dumps({"event": "result", "score": score, "details": details}, ensure_ascii=False)
                return

        # 图片模式
        msg = self._build_image_message(
            file_path,
            f"请批改这份作业（文件名：{filename}）："
        )
        messages = [SystemMessage(content=SYSTEM_PROMPT), msg]

        async for chunk in self._llm_stream(messages):
            if chunk.content:
                full_content += chunk.content
                yield json.dumps({"event": "content", "text": chunk.content}, ensure_ascii=False)

        stripped, details = self._extract_details_json(full_content)
        score = self._extract_score(stripped, details)
        yield json.dumps({"event": "final_text", "text": stripped}, ensure_ascii=False)
        yield json.dumps({"event": "result", "score": score, "details": details}, ensure_ascii=False)


    @staticmethod
    def _extract_details_json(text: str) -> tuple[str, Optional[List[dict]]]:
        """从批改文本中提取 JSON 详情，返回 (清理后的文本, 详情列表或None)。
        返回的文本保证不含任何 ``` 代码块。"""
        details = None

        json_start = -1
        json_end = -1

        # 策略：从文本末尾向前找 [{"question_no" 标记，括号配对解析 JSON
        tag = '[{"question_no"'
        tag_pos = text.rfind(tag)
        if tag_pos >= 0:
            start = text.rfind('[', 0, tag_pos + 1)
            if start >= 0:
                depth = 0
                for i in range(start, len(text)):
                    ch = text[i]
                    if ch == '[':
                        depth += 1
                    elif ch == ']':
                        depth -= 1
                        if depth == 0:
                            try:
                                parsed = json.loads(text[start:i + 1])
                                if isinstance(parsed, list):
                                    details = parsed
                                    json_start = start
                                    json_end = i + 1
                            except Exception:
                                pass
                            break

        # 清除所有 ``` 代码块
        cleaned = re.sub(r'```[\s\S]*?```', '', text)
        cleaned = re.sub(r'```', '', cleaned)
        # 切除已提取的 JSON 片段
        if json_start >= 0:
            cleaned = (cleaned[:json_start] + cleaned[json_end:])
        cleaned = re.sub(r'\n{4,}', '\n\n\n', cleaned)
        return cleaned.strip(), details

    def _extract_score(self, text: str, details: Optional[List[dict]] = None) -> Optional[int]:
        """从批改文本中提取总分，支持多种常见格式；无法识别时从逐题详情汇总。"""
        patterns = [
            r"总分[：:]\s*\*{0,2}(\d+)\*{0,2}\s*/\s*\*{0,2}100\*{0,2}",
            r"总分[：:]\s*\*{0,2}(\d+)\*{0,2}",
            r"得分[：:]\s*\*{0,2}(\d+)\*{0,2}\s*/\s*\*{0,2}100\*{0,2}",
            r"得分[：:]\s*\*{0,2}(\d+)\*{0,2}",
            r"(\d+)\s*分\s*/\s*100",
            r"总得分[：:]\s*(\d+)",
            r"总分\s*[-—]\s*(\d+)",
            r"评分[：:]\s*(\d+)",
            r"获得了?\s*(\d+)\s*分",
            r"[Ss]core[：:]\s*(\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue

        # 从逐题详情汇总计算总分（兼容外部传入 details）
        details_list = details if details is not None else []
        if details_list:
            total = sum(
                d.get("score", 0) for d in details_list
                if isinstance(d, dict) and isinstance(d.get("score"), (int, float))
            )
            if total > 0:
                return int(total)

        return None

    # ------------------------------------------------------------------
    # AI 出题
    # ------------------------------------------------------------------
    async def generate_questions(
        self, subject: str, grade: str, question_type: str,
        difficulty: str, count: int, requirement: Optional[str] = None,
    ) -> List[dict]:
        """根据参数生成题目列表。"""
        # 出题使用更高 temperature 增加随机性
        gen_llm = ChatOpenAI(
            model=config.MODEL_NAME,
            base_url=config.MODEL_BASE_URL,
            api_key=config.MODEL_API_KEY,
            temperature=0.9,
            timeout=300,
        )

        if requirement:
            requirement_block = (
                f"【核心指令——必须遵守】本次所有{count}道题必须是「{subject}」学科的题目。\n"
                f"出题范围严格限定为以下知识点：「{requirement}」\n"
                f"只能出与上述知识点直接相关的{subject}题，禁止切换到其他学科，禁止出无关题目。\n"
                f"要在同一个知识点下从不同角度、不同题型出题，确保{count}道题各不相同。"
            )
            sys_requirement = (
                f"你只能出{subject}题。本次出题知识点：「{requirement}」。"
                f"每道题必须同时满足：是{subject}题、直接考察该知识点。"
                f"从不同角度出{count}道题。严格按 JSON 格式返回。"
            )
        else:
            requirement_block = "【出题指令】从参考题型/知识点中随机选择不同组合，确保题目多样化，覆盖不同方向。"
            sys_requirement = "每次出题要有新意，避免重复。从不同知识点随机组合。严格按 JSON 格式返回。"

        # 语文/数学使用专用 Prompt，其他科目使用通用 Prompt
        if subject == "语文":
            prompt_text = GENERATE_CHINESE_PROMPT.format(
                count=count, difficulty=difficulty, grade=grade,
                requirement_block=requirement_block,
            )
            system_text = f"你是一位资深语文教师，{sys_requirement}"
        elif subject == "数学":
            prompt_text = GENERATE_MATH_PROMPT.format(
                count=count, difficulty=difficulty, grade=grade,
                requirement_block=requirement_block,
            )
            system_text = f"你是一位资深数学教师，{sys_requirement}"
        else:
            req_text = f"\n【知识点要求】只能围绕以下知识点出题：{requirement}" if requirement else ""
            prompt_text = GENERATE_QUESTIONS_PROMPT.format(
                subject=subject, grade=grade, question_type=question_type,
                difficulty=difficulty, count=count, requirement_text=req_text,
            )
            system_text = "你是一位资深学科教师，擅长出题。请严格按要求输出 JSON 格式题目，不要输出任何解释性文字。"
        messages = [
            SystemMessage(content=system_text),
            HumanMessage(content=prompt_text),
        ]
        async with self._semaphore:
            response = await gen_llm.ainvoke(messages)
        parsed = _parse_json_safely(response.content or "")
        if not isinstance(parsed, list):
            raise ValueError("模型返回内容无法解析为题目列表 JSON")

        normalized = []
        for i, q in enumerate(parsed, start=1):
            if not isinstance(q, dict):
                continue
            normalized.append({
                "question_no": str(q.get("question_no") or i),
                "question_text": str(q.get("question_text") or "").strip(),
                "standard_answer": str(q.get("standard_answer") or "").strip(),
                "analysis": str(q.get("analysis") or "").strip(),
                "difficulty": str(q.get("difficulty") or difficulty).strip(),
            })
        return normalized


# 单例
homework_agent = HomeworkAgent()

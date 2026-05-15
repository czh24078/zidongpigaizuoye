import json
import logging
import os
import re
from typing import List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from src.config import config
from src.services.image_service import image_to_base64, get_image_media_type
from src.services.ocr_service import ocr_image, ocr_images, ocr_available

logger = logging.getLogger(__name__)

# ======================================================================
# Prompt 定义
# ======================================================================

# 批改作业（无标准答案）
SYSTEM_PROMPT = """你是一位经验丰富的专业教师，擅长批改各科作业。请按照以下要求批改学生提交的作业：

1. 总体评价：给出总分（满分100分）和总体评语
2. 逐题分析：对每道题目进行分析
   - 标注正确/错误
   - 如果错误，指出错误原因
   - 给出正确答案和解题思路
3. 改进建议：针对学生的薄弱点给出学习建议

请使用Markdown格式输出，结构清晰，语言友好鼓励。"""

# 从试题图片中提取题目并生成标准答案（图片模式）
EXTRACT_EXAM_PROMPT = """你是一位严谨的学科老师，擅长审题与出标准答案。请仔细识别提供的所有图片中的题目与答案信息，并为每道题目整理出权威的标准答案。

说明：
- 可能提供 1~2 张图片。它们可能是“题目卷”（包含题干）、“答案卷”（只写答案）、或“题目+答案合在一起的试卷”。
- 如果多张图都包含同一题号的信息，请综合分析：优先从题目卷提取“题干”，从答案卷提取“标准答案”。
- 如果某张图上某题只有答案、没有题干，请根据题号与另一张图匹配，补全题干。
- 如果某题完全缺少题干，请将 question_text 留空字符串，等待用户后续手动补充。

要求：
1. 忠实还原每道题目的题号与题干文本（公式可用 LaTeX 或文字描述）。
2. 为每题给出明确、正确的“标准答案”。
3. 为每题补充简要的“解题分析/要点”（可选，若题目较简单可留空字符串）。
4. 严格以 JSON 数组返回，不要输出任何其它解释、前后缀或代码块围栏；若必须使用代码块，请使用 ```json 包裹。

JSON 结构（每个元素必须包含以下字段）：
[
  {
    "question_no": "1",
    "question_text": "题目原文",
    "standard_answer": "标准答案",
    "analysis": "解题要点（可为空字符串）"
  }
]
"""

# 从试题图片中提取题目并生成标准答案（OCR 文字模式）
EXTRACT_EXAM_OCR_PROMPT = """你是一位严谨的学科老师，擅长审题与出标准答案。以下是通过 OCR 从试题图片中识别出的文字内容，请根据这些文字为每道题目整理出权威的标准答案。

说明：
- OCR 识别可能存在误差（如空格、符号错误、顺序紊乱等），请结合上下文智能纠正。
- 可能包含多张图片的 OCR 结果，它们可能是“题目卷”、“答案卷”或“题目+答案合卷”。
- 请综合所有图片的 OCR 内容进行分析。

要求：
1. 忠实还原每道题目的题号与题干文本（公式可用 LaTeX 或文字描述）。
2. 为每题给出明确、正确的“标准答案”。
3. 为每题补充简要的“解题分析/要点”（可选，若题目较简单可留空字符串）。
4. 严格以 JSON 数组返回，不要输出任何其它解释、前后缀或代码块围栏；若必须使用代码块，请使用 ```json 包裹。

JSON 结构（每个元素必须包含以下字段）：
[
  {
    "question_no": "1",
    "question_text": "题目原文",
    "standard_answer": "标准答案",
    "analysis": "解题要点（可为空字符串）"
  }
]
"""

# 基于标准答案的结构化批改（图片模式）
CORRECT_WITH_ANSWERS_PROMPT = """你是一位严谨专业的学科老师，正在根据已知的“标准答案”批改学生的作业图片。

你将收到：
1. 一张学生作业图片（学生的书写内容）；
2. 本次试题对应的标准答案列表（JSON）。

请严格按照标准答案逐题批改，识别学生作答并判定对错。输出必须是 JSON，不要任何多余文字说明，结构如下：

{
  "total_score": 85,
  "full_score": 100,
  "summary": "总体评语",
  "details": [
    {
      "question_no": "1",
      "question_text": "题目原文",
      "student_answer": "学生作答（如无法识别，写 '未作答' 或 '无法识别'）",
      "standard_answer": "标准答案",
      "is_correct": true,
      "score": 10,
      "full_score": 10,
      "analysis": "详细批改分析：学生哪里正确/错误、错误原因、正确思路"
    }
  ],
  "suggestions": "总体改进建议"
}

若必须使用代码块，请使用 ```json 包裹。除 JSON 外不要输出任何内容。"""

# 基于标准答案的结构化批改（OCR 文字模式）
CORRECT_WITH_ANSWERS_OCR_PROMPT = """你是一位严谨专业的学科老师，正在根据已知的“标准答案”批改学生的作业。

你将收到：
1. 学生作业的 OCR 识别文字（通过光学字符识别从学生作业图片中提取）；
2. 本次试题对应的标准答案列表（JSON）。

注意：OCR 识别可能存在误差（空格、符号错误、顺序紊乱等），请结合上下文智能纠正后再批改。

请严格按照标准答案逐题批改，识别学生作答并判定对错。输出必须是 JSON，不要任何多余文字说明，结构如下：

{
  "total_score": 85,
  "full_score": 100,
  "summary": "总体评语",
  "details": [
    {
      "question_no": "1",
      "question_text": "题目原文",
      "student_answer": "学生作答（如无法识别，写 '未作答' 或 '无法识别'）",
      "standard_answer": "标准答案",
      "is_correct": true,
      "score": 10,
      "full_score": 10,
      "analysis": "详细批改分析：学生哪里正确/错误、错误原因、正确思路"
    }
  ],
  "suggestions": "总体改进建议"
}

若必须使用代码块，请使用 ```json 包裹。除 JSON 外不要输出任何内容。"""

# 无标准答案批改（OCR 文字模式）
SYSTEM_PROMPT_OCR = """你是一位经验丰富的专业教师，擅长批改各科作业。以下是通过 OCR 从学生作业图片中识别出的文字内容，请按照以下要求批改：

1. 总体评价：给出总分（满分100分）和总体评语
2. 逐题分析：对每道题目进行分析
   - 标注正确/错误
   - 如果错误，指出错误原因
   - 给出正确答案和解题思路
3. 改进建议：针对学生的薄弱点给出学习建议

注意：OCR 识别可能存在误差，请结合上下文智能纠正后再批改。
请使用Markdown格式输出，结构清晰，语言友好鼓励。"""


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
            temperature=0.3,
            timeout=300,
        )
        self.last_score = None
        self.last_details: Optional[List[dict]] = None
        self._last_file_path = None
        self._last_filename = None
        self._ocr_enabled = config.OCR_ENABLED and ocr_available()
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
    def _ocr_single(self, file_path: str) -> str:
        """对单张图片进行 OCR，返回识别文字。"""
        try:
            text = ocr_image(file_path)
            if text.strip():
                return text
            logger.warning(f"OCR 未识别到文字: {file_path}")
            return ""
        except Exception as e:
            logger.error(f"OCR 失败: {file_path}, 错误: {e}")
            return ""

    def _ocr_multiple(self, file_paths: List[str]) -> List[str]:
        """对多张图片进行 OCR，返回每张图片的识别文字。"""
        return [self._ocr_single(fp) for fp in file_paths]

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
            ocr_texts = self._ocr_multiple(file_paths)
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
        response = await self.llm.ainvoke(messages)
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
        response = await self.llm.ainvoke(messages)
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
            })
        return normalized
    
    # ------------------------------------------------------------------
    # 批改：无标准答案
    # ------------------------------------------------------------------
    async def correct(self, file_path: str, standard_answers: Optional[List[dict]] = None) -> str:
        """批改作业并返回 Markdown。
        standard_answers 非空时启用“带标准答案”模式，同时填充 last_details。
        """
        self._last_file_path = file_path
        self._last_filename = os.path.basename(file_path)
        self.last_details = None
    
        if standard_answers:
            return await self._correct_with_answers(file_path, standard_answers)
    
        # OCR 模式：先提取文字再交给大模型
        if self._ocr_enabled:
            ocr_text = self._ocr_single(file_path)
            if ocr_text.strip():
                return await self._correct_with_ocr_text(file_path, ocr_text)
            else:
                logger.warning("OCR 未识别到文字，回退到图片模式")
    
        # 图片模式（原有逻辑）
        msg = self._build_image_message(
            file_path,
            f"请批改这份作业（文件名：{self._last_filename}）："
        )
        messages = [SystemMessage(content=SYSTEM_PROMPT), msg]
        response = await self.llm.ainvoke(messages)
        result = response.content or ""
        self.last_score = self._extract_score(result)
        return result
    
    async def _correct_with_ocr_text(self, file_path: str, ocr_text: str) -> str:
        """使用 OCR 文字进行无标准答案批改。"""
        prompt_text = (
            f"以下是通过 OCR 从学生作业图片（{self._last_filename}）中识别出的文字内容：\n\n"
            f"{ocr_text}\n\n"
            "请根据以上 OCR 识别内容批改这份作业。"
        )
        msg = HumanMessage(content=prompt_text)
        messages = [SystemMessage(content=SYSTEM_PROMPT_OCR), msg]
    
        logger.info(f"使用 OCR 文字模式批改作业: {self._last_filename}")
        response = await self.llm.ainvoke(messages)
        result = response.content or ""
        self.last_score = self._extract_score(result)
        return result

    # ------------------------------------------------------------------
    # 批改：带标准答案（结构化输出 -> Markdown）
    # ------------------------------------------------------------------
    async def _correct_with_answers(self, file_path: str, standard_answers: List[dict]) -> str:
        answers_json = json.dumps(standard_answers, ensure_ascii=False, indent=2)

        # OCR 模式
        if self._ocr_enabled:
            ocr_text = self._ocr_single(file_path)
            if ocr_text.strip():
                return await self._correct_with_answers_ocr(file_path, standard_answers, ocr_text)
            else:
                logger.warning("OCR 未识别到文字，回退到图片模式")

        # 图片模式（原有逻辑）
        prompt_text = (
            f"试题标准答案（JSON）如下：\n{answers_json}\n\n"
            f"请严格按标准答案批改这份学生作业（文件名：{os.path.basename(file_path)}），"
            "仅返回规定结构的 JSON。"
        )
        msg = self._build_image_message(file_path, prompt_text)
        messages = [SystemMessage(content=CORRECT_WITH_ANSWERS_PROMPT), msg]

        response = await self.llm.ainvoke(messages)
        parsed = _parse_json_safely(response.content or "")
        if not isinstance(parsed, dict):
            # 解析失败，降级为纯文本
            self.last_score = self._extract_score(response.content or "")
            return response.content or ""

        details = parsed.get("details") or []
        if not isinstance(details, list):
            details = []
        self.last_details = details

        total_score = parsed.get("total_score")
        try:
            self.last_score = int(total_score) if total_score is not None else self._extract_score(
                json.dumps(parsed, ensure_ascii=False)
            )
        except Exception:
            self.last_score = None

        return self._render_details_markdown(parsed)

    async def _correct_with_answers_ocr(
        self, file_path: str, standard_answers: List[dict], ocr_text: str
    ) -> str:
        """OCR 模式：带标准答案的结构化批改。"""
        answers_json = json.dumps(standard_answers, ensure_ascii=False, indent=2)
        prompt_text = (
            f"试题标准答案（JSON）如下：\n{answers_json}\n\n"
            f"以下是通过 OCR 从学生作业图片（{os.path.basename(file_path)}）中识别出的文字内容：\n\n"
            f"{ocr_text}\n\n"
            "请严格按标准答案批改学生作答，仅返回规定结构的 JSON。"
        )
        msg = HumanMessage(content=prompt_text)
        messages = [SystemMessage(content=CORRECT_WITH_ANSWERS_OCR_PROMPT), msg]

        logger.info(f"使用 OCR 文字模式 + 标准答案批改: {os.path.basename(file_path)}")
        response = await self.llm.ainvoke(messages)
        parsed = _parse_json_safely(response.content or "")
        if not isinstance(parsed, dict):
            self.last_score = self._extract_score(response.content or "")
            return response.content or ""

        details = parsed.get("details") or []
        if not isinstance(details, list):
            details = []
        self.last_details = details

        total_score = parsed.get("total_score")
        try:
            self.last_score = int(total_score) if total_score is not None else self._extract_score(
                json.dumps(parsed, ensure_ascii=False)
            )
        except Exception:
            self.last_score = None

        return self._render_details_markdown(parsed)

    def _render_details_markdown(self, parsed: dict) -> str:
        """把结构化 JSON 转成易读的 Markdown。"""
        total = parsed.get("total_score")
        full = parsed.get("full_score") or 100
        summary = parsed.get("summary") or ""
        suggestions = parsed.get("suggestions") or ""
        details = parsed.get("details") or []

        lines = ["# 作业批改报告"]
        if total is not None:
            lines.append(f"\n## 总分：{total} / {full}\n")
        if summary:
            lines.append(f"> {summary}\n")

        lines.append("\n## 逐题批改\n")
        lines.append("| 题号 | 学生答案 | 标准答案 | 判定 | 得分 | 分析 |")
        lines.append("|------|----------|----------|------|------|------|")
        for d in details:
            no = str(d.get("question_no", "")).replace("|", "\\|")
            sa = str(d.get("student_answer", "")).replace("\n", " ").replace("|", "\\|")
            std = str(d.get("standard_answer", "")).replace("\n", " ").replace("|", "\\|")
            ok = "✅" if d.get("is_correct") else "❌"
            sc = d.get("score")
            fs = d.get("full_score")
            sc_str = f"{sc}/{fs}" if sc is not None and fs is not None else (str(sc) if sc is not None else "-")
            analysis = str(d.get("analysis", "")).replace("\n", " ").replace("|", "\\|")
            lines.append(f"| {no} | {sa} | {std} | {ok} | {sc_str} | {analysis} |")

        if suggestions:
            lines.append(f"\n## 改进建议\n\n{suggestions}\n")

        lines.append("\n> 本次批改由 AI 根据标准答案自动完成，如有疑问请咨询任课老师。")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 流式批改（保留旧接口，增加 OCR 支持）
    # ------------------------------------------------------------------
    async def correct_stream(self, file_path: str = None):
        if file_path:
            self._last_file_path = file_path
            self._last_filename = os.path.basename(file_path)
        elif self._last_file_path:
            file_path = self._last_file_path
        else:
            raise ValueError("未提供文件路径，且没有缓存的上次文件路径")

        # OCR 模式
        if self._ocr_enabled:
            ocr_text = self._ocr_single(file_path)
            if ocr_text.strip():
                prompt_text = (
                    f"以下是通过 OCR 从学生作业图片（{self._last_filename}）中识别出的文字内容：\n\n"
                    f"{ocr_text}\n\n"
                    "请根据以上 OCR 识别内容批改这份作业。"
                )
                msg = HumanMessage(content=prompt_text)
                messages = [SystemMessage(content=SYSTEM_PROMPT_OCR), msg]

                logger.info(f"流式批改使用 OCR 文字模式: {self._last_filename}")
                full_content = ""
                async for chunk in self.llm.astream(messages):
                    if chunk.content:
                        full_content += chunk.content
                        yield chunk.content

                self.last_score = self._extract_score(full_content)
                return
            else:
                logger.warning("OCR 未识别到文字，流式批改回退到图片模式")

        # 图片模式
        msg = self._build_image_message(
            file_path,
            f"请批改这份作业（文件名：{self._last_filename}）："
        )
        messages = [SystemMessage(content=SYSTEM_PROMPT), msg]

        full_content = ""
        async for chunk in self.llm.astream(messages):
            if chunk.content:
                full_content += chunk.content
                yield chunk.content

        self.last_score = self._extract_score(full_content)

    def _extract_score(self, text: str) -> int:
        patterns = [
            r"总分[：:]\s*(\d+)\s*/\s*100",
            r"总分[：:]\s*(\d+)",
            r"得分[：:]\s*(\d+)\s*/\s*100",
            r"(\d+)\s*分\s*/\s*100",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue
        return 85


# 单例
homework_agent = HomeworkAgent()

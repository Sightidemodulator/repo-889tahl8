"""Qwen-VL backend (DashScope OpenAI-compatible). Backend-swappable."""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from openai import OpenAI

import config

SYSTEM_PROMPT = """你是一名资深的自动驾驶 2D/3D 混合数据标注答疑助手。
你的知识来自《联合标注规则V2.5》以及历史答疑表格（含大量示例图片）。
回答要求：
1. 结合检索到的【规则/答疑片段】和【示例图片】作答，并理解用户上传的图片。
2. 先给出明确结论（标 / 不标 / 怎么标 / 给哪个类别），再简要说明依据。
3. 引用依据时标注来源（如“规则PDF 第X页”或“答疑《表名》第X行”）。
4. 【非常重要】只依据检索到的资料和图片作答，严禁编造规则或类别。
   - 若检索到的资料与问题不相关、不足以支撑结论，或你无法从图片中看清关键信息，
     必须明确回答“**我不确定 / 现有资料不足**”，并说明缺什么、建议用户补充哪些信息
     或人工核对规范，绝不能猜测一个答案。
   - 宁可说不知道，也不要给可能错误的结论。
5. 用简体中文，简洁专业。"""

LOW_RELEVANCE_NOTE = (
    "\n\n【系统提示】本次检索到的资料与问题的相关度较低，"
    "很可能知识库里没有直接对应的规则。请如实告知用户“资料不足/不确定”，"
    "不要强行给结论。"
)


def _img_data_url(path: Path) -> str | None:
    if not path.exists():
        return None
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def _client() -> OpenAI:
    if not config.DASHSCOPE_API_KEY:
        raise RuntimeError("DASHSCOPE_API_KEY 未设置")
    return OpenAI(api_key=config.DASHSCOPE_API_KEY, base_url=config.DASHSCOPE_BASE_URL)


def answer(
    question: str,
    contexts: list,
    user_image_paths: list[str] | None = None,
    weak_retrieval: bool = False,
) -> str:
    """contexts: list of dicts {title, text, images(list of abs paths)}."""
    client = _client()

    content: list[dict] = []

    # User-uploaded images first
    user_image_paths = user_image_paths or []
    for p in user_image_paths:
        url = _img_data_url(Path(p))
        if url:
            content.append({"type": "text", "text": "【我上传的图片】"})
            content.append({"type": "image_url", "image_url": {"url": url}})

    # Retrieved text + images
    text_block = ["以下是从规则文档和答疑表中检索到的相关资料：\n"]
    n_imgs = 0
    pending_images: list[tuple[str, str]] = []  # (label, url)
    for i, ctx in enumerate(contexts, 1):
        text_block.append(f"[资料{i}] 来源：{ctx['title']}\n{ctx['text'][:1200]}\n")
        for img in ctx.get("images", []):
            if n_imgs >= config.MAX_CONTEXT_IMAGES:
                break
            url = _img_data_url(Path(img))
            if url:
                pending_images.append((f"[资料{i} 的示例图]", url))
                n_imgs += 1

    content.append({"type": "text", "text": "\n".join(text_block)})
    for label, url in pending_images:
        content.append({"type": "text", "text": label})
        content.append({"type": "image_url", "image_url": {"url": url}})

    q_text = f"\n我的问题：{question}"
    if weak_retrieval:
        q_text += LOW_RELEVANCE_NOTE
    content.append({"type": "text", "text": q_text})

    resp = client.chat.completions.create(
        model=config.VL_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""

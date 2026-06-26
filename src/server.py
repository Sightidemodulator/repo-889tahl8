"""FastAPI backend + static frontend for the annotation Q&A assistant."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import config
import llm
from kb import Retriever

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
UPLOAD_DIR = config.KB_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="标注答疑助手")
_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever


def _img_url(rel_path: str) -> str:
    return f"/kb/image?path={rel_path}"


def _save_uploads(files: list[UploadFile], prefix: str) -> list[str]:
    """Save uploads under KB images, return KB-relative paths."""
    saved = []
    for f in files:
        if not f.filename:
            continue
        ext = Path(f.filename).suffix or ".jpg"
        name = f"uploads/{prefix}_{uuid.uuid4().hex[:8]}{ext}"
        dest = config.KB_DIR / name
        dest.write_bytes(f.file.read())
        saved.append(name)
    return saved


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/kb/image")
def kb_image(path: str) -> FileResponse:
    # prevent path traversal: resolve and ensure inside KB_DIR
    target = (config.KB_DIR / path).resolve()
    if not str(target).startswith(str(config.KB_DIR.resolve())) or not target.exists():
        raise HTTPException(status_code=404, detail="image not found")
    return FileResponse(target)


def _retrieve(question: str):
    """Run retrieval, build llm contexts + citations + gallery payloads."""
    hits = get_retriever().search(question)
    best = hits[0][1] if hits else 0.0
    weak = best < config.MIN_RELEVANCE

    contexts, citations, gallery = [], [], []
    for doc, score in hits:
        abs_imgs = [str(config.KB_DIR / p) for p in doc.images
                    if (config.KB_DIR / p).exists()]
        contexts.append({"title": doc.title, "text": doc.text, "images": abs_imgs})
        citations.append({"title": doc.title, "score": round(score, 3),
                          "source": doc.source})
        for rel in doc.images:
            if (config.KB_DIR / rel).exists():
                gallery.append({"url": _img_url(rel), "caption": doc.title})
    return contexts, citations, gallery[: config.MAX_CONTEXT_IMAGES], best, weak


@app.post("/api/ask")
async def ask(question: str = Form(...), images: list[UploadFile] = File(default=[])):
    if not question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    user_imgs_rel = _save_uploads(images, "ask")
    user_imgs_abs = [str(config.KB_DIR / p) for p in user_imgs_rel]

    contexts, citations, gallery, best, weak = _retrieve(question)

    try:
        ans = llm.answer(question, contexts, user_imgs_abs, weak_retrieval=weak)
        error = None
    except Exception as e:  # noqa: BLE001
        ans = ""
        error = str(e)

    return JSONResponse({
        "answer": ans,
        "error": error,
        "weak": weak,
        "best_score": round(best, 3),
        "citations": citations,
        "images": gallery,
        "user_images": [_img_url(p) for p in user_imgs_rel],
    })


@app.post("/api/ask/stream")
async def ask_stream(question: str = Form(...), images: list[UploadFile] = File(default=[])):
    if not question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    user_imgs_rel = _save_uploads(images, "ask")
    user_imgs_abs = [str(config.KB_DIR / p) for p in user_imgs_rel]

    def sse(event: str, payload: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def gen():
        yield sse("step", {"text": "正在检索知识库（规则文档 + 答疑表）…"})
        contexts, citations, gallery, best, weak = _retrieve(question)
        n_imgs = len(gallery)
        yield sse("step", {
            "text": f"检索到 {len(citations)} 条相关资料，正在查看 {n_imgs} 张示例图片…"
        })
        if user_imgs_abs:
            yield sse("step", {"text": f"正在结合你上传的 {len(user_imgs_abs)} 张图片进行对比…"})
        if weak:
            yield sse("step", {"text": f"⚠ 最高相关度仅 {round(best, 3)}，资料可能不足，将如实告知。"})
        # send metadata up front so the UI can render badge/citations/gallery
        yield sse("meta", {
            "weak": weak,
            "best_score": round(best, 3),
            "citations": citations,
            "images": gallery,
            "user_images": [_img_url(p) for p in user_imgs_rel],
        })
        yield sse("step", {"text": "正在结合规则与图片推理并生成回答…"})
        try:
            started = False
            for kind, text in llm.answer_stream(
                question, contexts, user_imgs_abs, weak_retrieval=weak
            ):
                if kind == "reasoning":
                    yield sse("reasoning", {"text": text})
                else:
                    if not started:
                        started = True
                        yield sse("answer_start", {})
                    yield sse("delta", {"text": text})
            yield sse("done", {})
        except Exception as e:  # noqa: BLE001
            yield sse("error", {"message": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@app.post("/api/learn")
async def learn(
    text: str = Form(...),
    title: str = Form(default=""),
    images: list[UploadFile] = File(default=[]),
):
    if not text.strip():
        raise HTTPException(status_code=400, detail="内容不能为空")
    title = title.strip() or f"用户补充知识 · {time.strftime('%Y-%m-%d %H:%M')}"
    saved = _save_uploads(images, "learn")
    doc = get_retriever().add_document(text=text.strip(), images=saved, title=title)
    return JSONResponse({
        "ok": True,
        "id": doc.id,
        "title": doc.title,
        "images": [_img_url(p) for p in saved],
        "total_docs": len(get_retriever().docs),
    })


@app.get("/api/stats")
def stats():
    r = get_retriever()
    learned = sum(1 for d in r.docs if d.source == "learned")
    return {"total_docs": len(r.docs), "learned": learned, "model": config.VL_MODEL}


# static assets (css/js)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)

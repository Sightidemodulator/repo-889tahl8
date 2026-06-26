"""Knowledge base: load records, build a vector index, and retrieve."""
from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import config


@dataclass
class Doc:
    id: int
    source: str
    title: str        # human-readable origin (section / sheet+row)
    text: str
    images: list      # paths relative to KB_DIR


def _load_records() -> list[Doc]:
    docs: list[Doc] = []
    idx = 0
    pdf_file = config.KB_DIR / "pdf_records.jsonl"
    xlsx_file = config.KB_DIR / "xlsx_records.jsonl"

    if pdf_file.exists():
        for line in pdf_file.open(encoding="utf-8"):
            r = json.loads(line)
            docs.append(Doc(
                id=idx,
                source=r["source"],
                title=f"规则PDF 第{r['page']}页 · {r['section']}",
                text=r["text"],
                images=r.get("images", []),
            ))
            idx += 1

    if xlsx_file.exists():
        for line in xlsx_file.open(encoding="utf-8"):
            r = json.loads(line)
            # skip empty/near-empty rows
            if len(r.get("text", "").strip()) < 4 and not r.get("images"):
                continue
            docs.append(Doc(
                id=idx,
                source=r["source"],
                title=f"答疑表《{r['sheet']}》第{r['row']}行",
                text=r["text"],
                images=r.get("images", []),
            ))
            idx += 1

    # User-contributed knowledge (added via the "learn" feature)
    learned_file = config.KB_DIR / "learned_records.jsonl"
    if learned_file.exists():
        for line in learned_file.open(encoding="utf-8"):
            r = json.loads(line)
            docs.append(Doc(
                id=idx,
                source=r.get("source", "learned"),
                title=r.get("title", "用户补充知识"),
                text=r["text"],
                images=r.get("images", []),
            ))
            idx += 1
    return docs


def build_index() -> None:
    from sentence_transformers import SentenceTransformer

    docs = _load_records()
    if not docs:
        raise SystemExit("No records found. Run ingest_pdf.py / ingest_xlsx.py first.")

    model = SentenceTransformer(config.EMBED_MODEL)
    # bge models recommend a query/passage instruction; embed passages plainly
    texts = [d.text[:2000] for d in docs]
    emb = model.encode(
        texts, batch_size=64, show_progress_bar=True, normalize_embeddings=True
    ).astype("float32")

    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(config.INDEX_DIR / "embeddings.npy", emb)
    with open(config.INDEX_DIR / "docs.pkl", "wb") as f:
        pickle.dump([d.__dict__ for d in docs], f)
    print(f"Indexed {len(docs)} docs, dim={emb.shape[1]}")


class Retriever:
    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self.emb = np.load(config.INDEX_DIR / "embeddings.npy")
        with open(config.INDEX_DIR / "docs.pkl", "rb") as f:
            self.docs = [Doc(**d) for d in pickle.load(f)]
        self.model = SentenceTransformer(config.EMBED_MODEL)

    def search(self, query: str, top_k: int | None = None) -> list[tuple[Doc, float]]:
        top_k = top_k or config.TOP_K
        q = self.model.encode(
            [f"为这个句子生成表示以用于检索相关文章：{query}"],
            normalize_embeddings=True,
        ).astype("float32")[0]
        scores = self.emb @ q
        order = np.argsort(-scores)[:top_k]
        return [(self.docs[i], float(scores[i])) for i in order]

    def add_document(self, text: str, images: list[str], title: str) -> Doc:
        """Incrementally add a user-contributed record: embed, append, persist."""
        new_id = (max((d.id for d in self.docs), default=-1)) + 1
        doc = Doc(id=new_id, source="learned", title=title, text=text, images=images)

        vec = self.model.encode(
            [text[:2000]], normalize_embeddings=True
        ).astype("float32")
        self.emb = np.vstack([self.emb, vec])
        self.docs.append(doc)

        # persist: rebuild npy/pkl + append to learned_records.jsonl
        np.save(config.INDEX_DIR / "embeddings.npy", self.emb)
        with open(config.INDEX_DIR / "docs.pkl", "wb") as f:
            pickle.dump([d.__dict__ for d in self.docs], f)
        learned_file = config.KB_DIR / "learned_records.jsonl"
        with open(learned_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(
                {"source": "learned", "title": title, "text": text, "images": images},
                ensure_ascii=False,
            ) + "\n")
        return doc


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        r = Retriever()
        for doc, score in r.search(" ".join(sys.argv[2:]) or "重卡和挂车怎么区分"):
            print(f"[{score:.3f}] {doc.title}  imgs={len(doc.images)}")
            print("   ", doc.text[:160].replace("\n", " "))
    else:
        build_index()

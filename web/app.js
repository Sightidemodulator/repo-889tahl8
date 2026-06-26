const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

// ---- tabs ----
$$(".tab").forEach((t) => {
  t.onclick = () => {
    $$(".tab").forEach((x) => x.classList.remove("active"));
    $$(".panel").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    $("#panel-" + t.dataset.tab).classList.add("active");
  };
});

// ---- stats ----
fetch("/api/stats").then((r) => r.json()).then((s) => {
  $("#stats").innerHTML = `知识库 ${s.total_docs} 条<br>已学习补充 ${s.learned} 条 · ${s.model}`;
}).catch(() => {});

// ---- file selection state ----
function makeFilePicker(inputSel, thumbsSel) {
  const input = $(inputSel), thumbs = $(thumbsSel);
  let files = [];
  function render() {
    thumbs.innerHTML = "";
    files.forEach((f, i) => {
      const url = URL.createObjectURL(f);
      const div = document.createElement("div");
      div.className = "t";
      div.innerHTML = `<img src="${url}"><span class="rm">×</span>`;
      div.querySelector(".rm").onclick = () => { files.splice(i, 1); render(); };
      thumbs.appendChild(div);
    });
  }
  input.onchange = () => { files = files.concat([...input.files]); input.value = ""; render(); };
  return { get: () => files, clear: () => { files = []; render(); } };
}
const askFiles = makeFilePicker("#ask-files", "#ask-thumbs");
const learnFiles = makeFilePicker("#learn-files", "#learn-thumbs");

// ---- chat helpers ----
const chat = $("#chat");
function clearHint() { const h = $(".empty-hint"); if (h) h.remove(); }

function addUser(text, imgUrls) {
  clearHint();
  const el = document.createElement("div");
  el.className = "msg user";
  let imgs = "";
  if (imgUrls && imgUrls.length)
    imgs = `<div class="gallery">${imgUrls.map(u => `<figure><img src="${u}" data-full="${u}"></figure>`).join("")}</div>`;
  el.innerHTML = `<div class="role">你</div><div class="bubble">${escapeHtml(text)}${imgs}</div>`;
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
}

function addTyping() {
  const el = document.createElement("div");
  el.className = "msg ai"; el.id = "typing";
  el.innerHTML = `<div class="role">助手</div><div class="bubble typing">正在查阅文档与图片<span class="dot">.</span><span class="dot">.</span><span class="dot">.</span></div>`;
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
}

function addAI(data) {
  const t = $("#typing"); if (t) t.remove();
  const el = document.createElement("div");
  el.className = "msg ai";
  let body = "";
  if (data.error) {
    body = `<div class="badge-warn">调用模型出错</div><p>${escapeHtml(data.error)}</p>
      <p class="hint">请检查 DASHSCOPE_API_KEY 是否有效。下面是检索到的相关资料图片。</p>`;
  } else {
    if (data.weak)
      body += `<div class="badge-warn">⚠ 资料相关度较低（${data.best_score}），回答可能不确定</div>`;
    body += marked.parse(data.answer || "");
  }
  // citations
  if (data.citations && data.citations.length) {
    const items = data.citations.map(c => `<li>${escapeHtml(c.title)} <span style="opacity:.6">(${c.score})</span></li>`).join("");
    body += `<details class="citations"><summary>参考来源 ${data.citations.length} 条</summary><ul>${items}</ul></details>`;
  }
  // gallery
  if (data.images && data.images.length) {
    const figs = data.images.map(im =>
      `<figure><img src="${im.url}" data-full="${im.url}"><figcaption>${escapeHtml(im.caption)}</figcaption></figure>`).join("");
    body += `<div class="gallery">${figs}</div>`;
  }
  el.innerHTML = `<div class="role">助手</div><div class="bubble">${body}</div>`;
  chat.appendChild(el);
  bindLightbox(el);
  chat.scrollTop = chat.scrollHeight;
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// ---- ask ----
async function sendAsk() {
  const input = $("#ask-input");
  const q = input.value.trim();
  if (!q) return;
  const files = askFiles.get();
  const localUrls = files.map(f => URL.createObjectURL(f));
  addUser(q, localUrls);
  input.value = ""; input.style.height = "auto";
  const fd = new FormData();
  fd.append("question", q);
  files.forEach(f => fd.append("images", f));
  askFiles.clear();
  $("#ask-send").disabled = true;
  addTyping();
  try {
    const res = await fetch("/api/ask", { method: "POST", body: fd });
    const data = await res.json();
    addAI(data);
  } catch (e) {
    addAI({ error: String(e) });
  } finally {
    $("#ask-send").disabled = false;
  }
}
$("#ask-send").onclick = sendAsk;
$("#ask-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendAsk(); }
});
$("#ask-input").addEventListener("input", function () {
  this.style.height = "auto"; this.style.height = Math.min(this.scrollHeight, 180) + "px";
});
$$(".chip").forEach(c => c.onclick = () => { $("#ask-input").value = c.textContent; sendAsk(); });

// ---- learn ----
$("#learn-send").onclick = async () => {
  const text = $("#learn-text").value.trim();
  const result = $("#learn-result");
  if (!text) { result.className = "learn-result err"; result.textContent = "内容不能为空"; return; }
  const fd = new FormData();
  fd.append("text", text);
  fd.append("title", $("#learn-title").value.trim());
  learnFiles.get().forEach(f => fd.append("images", f));
  $("#learn-send").disabled = true;
  result.className = "learn-result"; result.textContent = "写入中…";
  try {
    const res = await fetch("/api/learn", { method: "POST", body: fd });
    const data = await res.json();
    result.className = "learn-result ok";
    result.textContent = `✓ 已写入知识库：「${data.title}」，当前共 ${data.total_docs} 条，立即可被检索。`;
    $("#learn-text").value = ""; $("#learn-title").value = ""; learnFiles.clear();
    fetch("/api/stats").then(r => r.json()).then(s => {
      $("#stats").innerHTML = `知识库 ${s.total_docs} 条<br>已学习补充 ${s.learned} 条 · ${s.model}`;
    });
  } catch (e) {
    result.className = "learn-result err"; result.textContent = "写入失败：" + e;
  } finally {
    $("#learn-send").disabled = false;
  }
};

// ---- lightbox ----
const lb = document.createElement("div");
lb.className = "lightbox"; lb.innerHTML = "<img>";
document.body.appendChild(lb);
lb.onclick = () => lb.classList.remove("show");
function bindLightbox(scope) {
  scope.querySelectorAll("img[data-full]").forEach(img => {
    img.onclick = () => { lb.querySelector("img").src = img.dataset.full; lb.classList.add("show"); };
  });
}

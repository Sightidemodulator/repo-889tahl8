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
function refreshStats() {
  fetch("/api/stats")
    .then((r) => (r.ok ? r.json() : null))
    .then((s) => {
      if (s) $("#stats").innerHTML = `知识库 ${s.total_docs} 条<br>已学习补充 ${s.learned} 条 · ${s.model}`;
    })
    .catch(() => {});
}

// ---- access password gate ----
function showGate() {
  const gate = $("#gate"), input = $("#gate-input"), btn = $("#gate-btn"), err = $("#gate-err");
  gate.hidden = false;
  setTimeout(() => input.focus(), 50);
  async function submit() {
    if (!input.value) return;
    err.textContent = "";
    btn.disabled = true;
    const fd = new FormData();
    fd.append("password", input.value);
    try {
      const res = await fetch("/api/login", { method: "POST", body: fd });
      if (res.ok) { gate.hidden = true; refreshStats(); }
      else { err.textContent = "密码错误，请重试"; input.value = ""; input.focus(); }
    } catch (e) {
      err.textContent = "登录失败：" + e;
    } finally {
      btn.disabled = false;
    }
  }
  btn.onclick = submit;
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } });
}

fetch("/api/auth")
  .then((r) => r.json())
  .then((a) => { if (a.required && !a.authed) showGate(); else refreshStats(); })
  .catch(() => refreshStats());

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
  return {
    get: () => files,
    add: (f) => { files.push(f); render(); },
    clear: () => { files = []; render(); },
  };
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

// ---- streaming AI message ----
// Returns a controller with methods the SSE loop calls as events arrive.
function addStreamingAI() {
  clearHint();
  const el = document.createElement("div");
  el.className = "msg ai";
  el.innerHTML = `
    <div class="role">助手</div>
    <div class="bubble">
      <details class="think" open>
        <summary><span class="spin"></span><span class="think-label">思考中…</span></summary>
        <div class="think-body"><ul class="steps"></ul><div class="reasoning"></div></div>
      </details>
      <div class="answer"></div>
      <div class="extras"></div>
    </div>`;
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;

  const think = el.querySelector(".think");
  const thinkLabel = el.querySelector(".think-label");
  const steps = el.querySelector(".steps");
  const reasoning = el.querySelector(".reasoning");
  const answer = el.querySelector(".answer");
  const extras = el.querySelector(".extras");
  let answerRaw = "", reasoningRaw = "";
  const t0 = Date.now();

  function scroll() { chat.scrollTop = chat.scrollHeight; }

  return {
    step(text) {
      const li = document.createElement("li");
      li.textContent = text;
      steps.appendChild(li);
      scroll();
    },
    reasoning(text) {
      reasoningRaw += text;
      reasoning.textContent = reasoningRaw;
      scroll();
    },
    meta(data) {
      if (data.weak)
        answer.insertAdjacentHTML("beforebegin",
          `<div class="badge-warn">⚠ 资料相关度较低（${data.best_score}），回答可能不确定</div>`);
      // build citations + gallery now, append after streaming finishes
      let ex = "";
      if (data.citations && data.citations.length) {
        const items = data.citations.map(c =>
          `<li>${escapeHtml(c.title)} <span style="opacity:.6">(${c.score})</span></li>`).join("");
        ex += `<details class="citations"><summary>参考来源 ${data.citations.length} 条</summary><ul>${items}</ul></details>`;
      }
      if (data.images && data.images.length) {
        const figs = data.images.map(im =>
          `<figure><img src="${im.url}" data-full="${im.url}"><figcaption>${escapeHtml(im.caption)}</figcaption></figure>`).join("");
        ex += `<div class="gallery">${figs}</div>`;
      }
      extras.dataset.html = ex;
    },
    answerStart() {
      think.removeAttribute("open");
    },
    delta(text) {
      answerRaw += text;
      answer.innerHTML = marked.parse(answerRaw);
      scroll();
    },
    done() {
      const secs = ((Date.now() - t0) / 1000).toFixed(1);
      thinkLabel.textContent = `思考过程（用时 ${secs}s）`;
      think.querySelector(".spin").remove();
      think.removeAttribute("open");
      if (extras.dataset.html) { extras.innerHTML = extras.dataset.html; bindLightbox(extras); }
      scroll();
    },
    error(msg) {
      think.removeAttribute("open");
      answer.innerHTML = `<div class="badge-warn">调用模型出错</div><p>${escapeHtml(msg)}</p>
        <p class="hint">请检查 DASHSCOPE_API_KEY 是否有效。</p>`;
      if (extras.dataset.html) { extras.innerHTML = extras.dataset.html; bindLightbox(extras); }
      scroll();
    },
  };
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// ---- SSE stream parser over fetch body ----
async function streamSSE(url, fd, ctrl) {
  const res = await fetch(url, { method: "POST", body: fd });
  if (!res.ok || !res.body) { ctrl.error(`HTTP ${res.status}`); return; }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, idx); buf = buf.slice(idx + 2);
      let event = "message", data = "";
      raw.split("\n").forEach(line => {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      });
      let payload = {}; try { payload = data ? JSON.parse(data) : {}; } catch (_) {}
      if (event === "step") ctrl.step(payload.text);
      else if (event === "reasoning") ctrl.reasoning(payload.text);
      else if (event === "meta") ctrl.meta(payload);
      else if (event === "answer_start") ctrl.answerStart();
      else if (event === "delta") ctrl.delta(payload.text);
      else if (event === "done") ctrl.done();
      else if (event === "error") ctrl.error(payload.message);
    }
  }
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
  files.forEach(f => fd.append("images", f, f.name || "image.png"));
  askFiles.clear();
  $("#ask-send").disabled = true;
  const ctrl = addStreamingAI();
  try {
    await streamSSE("/api/ask/stream", fd, ctrl);
  } catch (e) {
    ctrl.error(String(e));
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
// paste images directly into the chat box (Ctrl+V / 截图粘贴)
$("#ask-input").addEventListener("paste", (e) => {
  const items = (e.clipboardData && e.clipboardData.items) || [];
  let added = false;
  for (const it of items) {
    if (it.kind === "file" && it.type.startsWith("image/")) {
      const blob = it.getAsFile();
      if (blob) {
        const ext = (blob.type.split("/")[1] || "png").replace("jpeg", "jpg");
        const file = new File([blob], `pasted-${Date.now()}.${ext}`, { type: blob.type });
        askFiles.add(file);
        added = true;
      }
    }
  }
  if (added) e.preventDefault();
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

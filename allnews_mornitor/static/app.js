const $ = (s) => document.querySelector(s);

const state = {
  platforms: [],
  defaults: {},
  batchItems: [],
  filterPlatform: "",
};

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  return res.json().catch(() => ({}));
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((p) => {
    const on = p.id === `panel-${name}`;
    p.classList.toggle("active", on);
    p.hidden = !on;
  });
  if (name === "settings") renderSettings();
  if (name === "candidates") loadCandidates();
  if (name === "archive") loadArchive();
}

function setStatus(el, text, kind) {
  if (!el) return;
  el.textContent = text || "";
  el.style.color = kind === "error" ? "var(--danger)" : kind === "ok" ? "var(--ok)" : "var(--muted)";
}

async function refreshHealth() {
  try {
    const d = await api("/api/health");
    $("#healthDot").className = "dot " + (d.ok ? "ok" : "bad");
    $("#healthText").textContent = d.ok ? `在线 · ${d.time || ""}` : "异常";
  } catch {
    $("#healthDot").className = "dot bad";
    $("#healthText").textContent = "无法连接";
  }
}

function fillPlatformSelects(platforms) {
  state.platforms = platforms || [];
  const opts = [`<option value="">全部平台</option>`]
    .concat(state.platforms.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`))
    .join("");
  $("#candPlatform").innerHTML = opts;
  $("#archPlatform").innerHTML = opts;
  $("#platBox").innerHTML = state.platforms
    .map(
      (p) =>
        `<label><input type="checkbox" data-plat="${esc(p.id)}" ${p.enabled ? "checked" : ""}/> ${esc(p.name)}</label>`
    )
    .join("");
  $("#filterChips").innerHTML = state.platforms
    .map((p) => `<button class="chip" type="button" data-filter="${esc(p.id)}">${esc(p.name)}</button>`)
    .join("");
  document.querySelectorAll(".chip[data-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.filterPlatform = btn.dataset.filter || "";
      document.querySelectorAll(".chip").forEach((c) => {
        c.classList.toggle("active", (c.dataset.filter || "") === state.filterPlatform);
      });
      renderBatchCards();
    });
  });
}

function selectedPlatforms() {
  return [...document.querySelectorAll("#platBox input[data-plat]:checked")].map((x) => x.dataset.plat);
}

function renderCard(it, { showArchive = false, showAnalyze = false } = {}) {
  const inCand = !!it.in_candidates || showArchive === false && it.platform;
  const badge = it.in_candidates
    ? `<span class="badge ok">已入候选</span>`
    : it.gate_reason
      ? `<span class="badge no">未入候选</span>`
      : `<span class="badge plat">${esc(it.archive_type || it.platform || "")}</span>`;
  const score = Number(it.score || 0);
  return `<article class="card ${it.in_candidates ? "in" : it.gate_reason ? "out" : ""}">
    <div class="meta">
      <span class="badge plat">${esc(it.platform)}</span>
      ${badge}
    </div>
    <h3>${esc(it.title || "(无标题)")}</h3>
    <div class="meta">
      <span>赞 ${it.likes || 0}</span>
      <span>评 ${it.comments || 0}</span>
      <span>分 ${score.toFixed ? score.toFixed(1) : score}</span>
      ${it.author ? `<span>${esc(it.author)}</span>` : ""}
    </div>
    ${it.gate_reason ? `<div class="gate">${esc(it.gate_reason)}</div>` : ""}
    ${it.reason ? `<div class="gate">${esc(it.reason)}</div>` : ""}
    <div class="actions">
      ${it.url ? `<a href="${esc(it.url)}" target="_blank" rel="noreferrer">打开</a>` : ""}
      ${showArchive && it.post_id ? `<button class="btn ghost" data-arch="${esc(it.post_id)}">手动归档</button>` : ""}
      ${showAnalyze && it.post_id ? `<button class="btn ghost" data-analyze="${esc(it.post_id)}">分析要素</button>` : ""}
    </div>
  </article>`;
}

function renderBatchCards() {
  let items = state.batchItems || [];
  if (state.filterPlatform) {
    items = items.filter((x) => x.platform === state.filterPlatform);
  }
  if ($("#onlyCand")?.checked) {
    items = items.filter((x) => x.in_candidates);
  }
  const box = $("#batchList");
  if (!items.length) {
    box.innerHTML = `<div class="card"><h3>暂无本批结果</h3><div class="gate">点「开始 CDP 抓取」或「刷新本批」</div></div>`;
    return;
  }
  box.innerHTML = items.map((it) => renderCard(it, { showArchive: !!it.in_candidates })).join("");
  box.querySelectorAll("[data-arch]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const post_id = btn.getAttribute("data-arch");
      const r = await api("/api/archive", {
        method: "POST",
        body: JSON.stringify({ post_id, note: "手动归档" }),
      });
      setStatus($("#crawlStatus"), r.success ? "已手动归档" : r.error || "失败", r.success ? "ok" : "error");
      if (r.success) btn.disabled = true;
    });
  });
}

async function loadBatch() {
  const full = await api("/api/batch/last?limit=200");
  state.batchItems = full.items || [];
  const m = full.meta || {};
  $("#batchMeta").textContent = m.total_fetched
    ? `本批抓取 ${m.total_fetched} · 入候选 ${m.candidates || 0} · 门槛过滤 ${m.rejected || 0} · 自动归档 ${m.archived || 0}`
    : `共 ${state.batchItems.length} 条`;
  renderBatchCards();
}

async function pollJob(id) {
  for (let i = 0; i < 240; i++) {
    const d = await api(`/api/jobs/${id}`);
    const job = d.job || {};
    setStatus($("#crawlStatus"), job.message || job.status || "运行中…");
    if (job.status === "done") {
      setStatus($("#crawlStatus"), job.message || "完成", "ok");
      if (job.result?.items) {
        state.batchItems = job.result.items;
        const m = job.result;
        $("#batchMeta").textContent =
          `本批抓取 ${m.total_fetched || 0} · 入候选 ${m.candidates || 0} · 门槛过滤 ${m.rejected || 0} · 自动归档 ${m.archived || 0}`;
        renderBatchCards();
      } else {
        await loadBatch();
      }
      return;
    }
    if (job.status === "error") {
      setStatus($("#crawlStatus"), job.message || "失败", "error");
      return;
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  setStatus($("#crawlStatus"), "等待超时", "error");
}

function renderCand(items) {
  const box = $("#candList");
  if (!items.length) {
    box.innerHTML = `<div class="card"><h3>暂无候选</h3><div class="gate">提高抓取量或降低门槛后再试</div></div>`;
    return;
  }
  box.innerHTML = items
    .map((it) => {
      const row = { ...it, in_candidates: true };
      return renderCard(row, { showArchive: true });
    })
    .join("");
  box.querySelectorAll("[data-arch]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const post_id = btn.getAttribute("data-arch");
      const r = await api("/api/archive", {
        method: "POST",
        body: JSON.stringify({ post_id, note: "手动归档" }),
      });
      if (r.success) btn.disabled = true;
    });
  });
}

function renderArch(items) {
  const box = $("#archList");
  if (!items.length) {
    box.innerHTML = `<div class="card"><h3>暂无归档</h3></div>`;
    return;
  }
  box.innerHTML = items
    .map((it) => {
      const card = renderCard(it, { showAnalyze: true });
      const factors =
        it.factors && Object.keys(it.factors).length
          ? `<pre class="gate" style="white-space:pre-wrap">${esc(JSON.stringify(it.factors, null, 2))}</pre>`
          : "";
      return card.replace("</article>", `${factors}</article>`);
    })
    .join("");
  box.querySelectorAll("[data-analyze]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      const post_id = btn.getAttribute("data-analyze");
      const r = await api("/api/analyze", { method: "POST", body: JSON.stringify({ post_id }) });
      btn.disabled = false;
      if (!r.success) {
        alert(r.error || "分析失败");
        return;
      }
      await loadArchive();
    });
  });
}

async function loadCandidates() {
  const qs = new URLSearchParams();
  const p = $("#candPlatform").value;
  if (p) qs.set("platform", p);
  qs.set("limit", "80");
  const d = await api(`/api/candidates?${qs}`);
  renderCand(d.items || []);
}

async function loadArchive() {
  const qs = new URLSearchParams();
  const p = $("#archPlatform").value;
  const t = $("#archType").value;
  if (p) qs.set("platform", p);
  if (t) qs.set("type", t);
  qs.set("limit", "80");
  const d = await api(`/api/archive?${qs}`);
  renderArch(d.items || []);
}

function fillDefaultsForm(defaults) {
  state.defaults = defaults || {};
  const cand = state.defaults.candidate || {};
  $("#defInterval").value = state.defaults.crawl_interval_min ?? 60;
  $("#defLikes").value = cand.min_likes ?? 50;
  $("#defComments").value = cand.min_comments ?? 5;
  $("#defScore").value = cand.min_score ?? 0;
  $("#defRequire").value = cand.require || "all";
}

function renderSettings() {
  fillDefaultsForm(state.defaults);
  $("#platSettings").innerHTML = state.platforms
    .map((p) => {
      const c = p.candidate || {};
      return `<div class="plat-card" data-pid="${esc(p.id)}">
        <h3>${esc(p.name)} <span class="badge plat">${esc(p.id)}</span></h3>
        <div class="form-row">
          <label class="inline" style="min-width:auto;flex-direction:row;padding-top:18px">
            <input type="checkbox" data-k="enabled" ${p.enabled ? "checked" : ""}/> 启用
          </label>
          <label>间隔(分，空=默认)
            <input data-k="crawl_interval_min" type="number" min="5" placeholder="默认 ${esc(p.default_interval_min)}"
              value="${p.crawl_interval_inherited ? "" : esc(p.crawl_interval_min)}" />
          </label>
          <label>最低赞<input data-k="min_likes" type="number" min="0" value="${esc(c.min_likes ?? 0)}" /></label>
          <label>最低评<input data-k="min_comments" type="number" min="0" value="${esc(c.min_comments ?? 0)}" /></label>
          <label>最低分<input data-k="min_score" type="number" min="0" value="${esc(c.min_score ?? 0)}" /></label>
          <label>上次抓取<span style="padding:8px 0;color:var(--ink)">${esc(p.last_crawl_at || "尚未")}</span></label>
          <button class="btn primary" type="button" data-save-plat="${esc(p.id)}">保存</button>
        </div>
      </div>`;
    })
    .join("");

  $("#platSettings").querySelectorAll("[data-save-plat]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-save-plat");
      const card = btn.closest(".plat-card");
      const intervalRaw = card.querySelector('[data-k="crawl_interval_min"]').value;
      const body = {
        id,
        enabled: card.querySelector('[data-k="enabled"]').checked,
        crawl_interval_min: intervalRaw === "" ? null : Number(intervalRaw),
        candidate: {
          min_likes: Number(card.querySelector('[data-k="min_likes"]').value || 0),
          min_comments: Number(card.querySelector('[data-k="min_comments"]').value || 0),
          min_score: Number(card.querySelector('[data-k="min_score"]').value || 0),
        },
      };
      const r = await api("/api/platforms", { method: "POST", body: JSON.stringify(body) });
      if (!r.success) {
        alert(r.error || "保存失败");
        return;
      }
      await reloadPlatforms();
      alert("已保存 " + id);
    });
  });
}

async function reloadPlatforms() {
  const d = await api("/api/platforms");
  state.defaults = d.defaults || {};
  fillPlatformSelects(d.platforms || []);
  fillDefaultsForm(state.defaults);
}

function bind() {
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));

  $("#btnCrawl").addEventListener("click", async () => {
    const platforms = selectedPlatforms();
    $("#btnCrawl").disabled = true;
    setStatus($("#crawlStatus"), "已提交…");
    try {
      const d = await api("/api/crawl", { method: "POST", body: JSON.stringify({ platforms }) });
      if (!d.success) {
        setStatus($("#crawlStatus"), d.error || "启动失败", "error");
        return;
      }
      await pollJob(d.job_id);
    } catch (e) {
      setStatus($("#crawlStatus"), String(e), "error");
    } finally {
      $("#btnCrawl").disabled = false;
    }
  });

  $("#btnLoadBatch").addEventListener("click", loadBatch);
  $("#onlyCand")?.addEventListener("change", renderBatchCards);
  $("#btnLoadCand").addEventListener("click", loadCandidates);
  $("#btnLoadArch").addEventListener("click", loadArchive);

  $("#btnSaveDefaults").addEventListener("click", async () => {
    const body = {
      crawl_interval_min: Number($("#defInterval").value || 60),
      candidate: {
        min_likes: Number($("#defLikes").value || 0),
        min_comments: Number($("#defComments").value || 0),
        min_score: Number($("#defScore").value || 0),
        require: $("#defRequire").value || "all",
      },
    };
    const r = await api("/api/config/defaults", { method: "POST", body: JSON.stringify(body) });
    if (!r.success) {
      alert(r.error || "保存失败");
      return;
    }
    await reloadPlatforms();
    alert("默认配置已保存");
  });
}

async function boot() {
  bind();
  await refreshHealth();
  await reloadPlatforms();
  await loadBatch();
  setInterval(refreshHealth, 15000);
}

boot();

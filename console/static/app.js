const $ = (sel) => document.querySelector(sel);

const state = {
  lastCreate: { title: "", content: "", path: "" },
};

function setStatus(el, text, kind) {
  if (!el) return;
  el.textContent = text || "";
  el.style.color =
    kind === "error" ? "var(--danger)" : kind === "ok" ? "var(--ok)" : "var(--muted)";
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok && data && !data.error) {
    data.error = `HTTP ${res.status}`;
  }
  return data;
}

function renderItems(container, items) {
  if (!items || !items.length) {
    container.innerHTML = `<div class="item"><h3>暂无数据</h3><p class="snippet">换个关键词，或先执行一次抓取。</p></div>`;
    return;
  }
  container.innerHTML = items
    .map((it) => {
      const stars = Number(it.star || 0);
      const useful = it.isUseful ? "有用" : "";
      const snippet = (it.content || it.raw || "").slice(0, 220);
      return `
        <article class="item">
          <h3>${escapeHtml(it.title || "(无标题)")}</h3>
          <div class="meta">
            <span>${escapeHtml(it.platform_name || it.platform_id || "")}</span>
            <span>${escapeHtml(it.fetched_at || "")}</span>
            ${useful ? `<span>${useful}</span>` : ""}
            ${stars ? `<span>★ ${stars}</span>` : ""}
            ${it.href ? `<a href="${escapeAttr(it.href)}" target="_blank" rel="noreferrer">打开</a>` : ""}
            <button class="btn ghost" data-use-topic="${escapeAttr(it.title || "")}">用作创作主题</button>
          </div>
          ${snippet ? `<p class="snippet">${escapeHtml(snippet)}</p>` : ""}
        </article>`;
    })
    .join("");

  container.querySelectorAll("[data-use-topic]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const topic = btn.getAttribute("data-use-topic") || "";
      $("#createTopic").value = topic;
      switchTab("create");
    });
  });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/'/g, "&#39;");
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((tab) => {
    const on = tab.dataset.tab === name;
    tab.classList.toggle("active", on);
    tab.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll(".panel").forEach((panel) => {
    const on = panel.id === `panel-${name}`;
    panel.classList.toggle("active", on);
    panel.hidden = !on;
  });
}

async function refreshHealth() {
  try {
    const data = await api("/api/health");
    $("#healthDot").className = "dot " + (data.ok ? "ok" : "bad");
    $("#healthText").textContent = data.ok
      ? `在线 · ${data.time || ""}`
      : "服务异常";
  } catch (e) {
    $("#healthDot").className = "dot bad";
    $("#healthText").textContent = "无法连接后端";
  }
}

async function loadPosts(keyword, platform, target) {
  const qs = new URLSearchParams();
  if (keyword) qs.set("keyword", keyword);
  if (platform) qs.set("platform", platform);
  qs.set("limit", "80");
  const data = await api(`/api/posts?${qs.toString()}`);
  if (!data.success) {
    setStatus(target === "history" ? $("#historyMeta") : $("#crawlStatus"), data.error || "加载失败", "error");
    return;
  }
  if (target === "history") {
    setStatus(
      $("#historyMeta"),
      `缓存生成于 ${data.generated_at || "-"} · 共 ${data.total} 条`,
      "ok"
    );
    renderItems($("#historyList"), data.items);
  } else {
    setStatus($("#crawlStatus"), `匹配 ${data.total} 条`, "ok");
    renderItems($("#newsList"), data.items);
  }
}

async function pollJob(jobId) {
  for (let i = 0; i < 180; i++) {
    const data = await api(`/api/jobs/${jobId}`);
    const job = data.job || {};
    setStatus($("#crawlStatus"), job.message || job.status || "运行中…");
    if (job.plan && job.plan.twitter_queries) {
      const box = $("#expandPreview");
      const body = $("#expandPreviewBody");
      if (box && body) {
        box.hidden = false;
        body.textContent = JSON.stringify(
          {
            provider: (job.expansion && job.expansion.provider) || "",
            seeds: job.plan.seeds,
            twitter_queries: job.plan.twitter_queries,
            reddit_queries: job.plan.reddit_queries,
            telegram_queries: job.plan.telegram_queries,
          },
          null,
          2
        );
      }
    }
    if (job.status === "done") {
      setStatus($("#crawlStatus"), job.message || "完成", "ok");
      await loadPosts($("#newsKeyword").value.trim(), "", "news");
      await loadTasks();
      return;
    }
    if (job.status === "error") {
      setStatus($("#crawlStatus"), job.message || "抓取失败", "error");
      await loadTasks();
      return;
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  setStatus($("#crawlStatus"), "等待超时，请稍后在历史缓存中查看", "error");
}

function selectedPlatforms() {
  const plats = [];
  if ($("#platX")?.checked) plats.push("x-cdp");
  if ($("#platReddit")?.checked) plats.push("reddit");
  if ($("#platTelegram")?.checked) plats.push("telegram");
  return plats.length ? plats : ["x-cdp"];
}

async function loadTasks() {
  const data = await api("/api/crawl/tasks");
  const box = $("#taskList");
  const queue = $("#taskPanel");
  if (!box) return;
  const items = (data.items || []).filter((t) => t.enabled || t.running);
  const showTaskUi = !!$("#crawlScheduled")?.checked || items.length > 0;
  if (queue) queue.hidden = !showTaskUi;
  const opts = $("#taskScheduleOpts");
  if (opts) opts.hidden = !$("#crawlScheduled")?.checked;

  if (!items.length) {
    box.innerHTML = showTaskUi
      ? `<div class="item"><h3>暂无运行中的周期任务</h3><p class="snippet">勾选「添加为周期任务」后点开始抓取即可创建。</p></div>`
      : "";
    return;
  }
  box.innerHTML = items
    .map((t) => {
      const enabled = t.enabled ? "运行中" : "已停止";
      const plats = (t.platforms || []).join(", ");
      return `
        <article class="item">
          <h3>${escapeHtml(t.keyword || "")}</h3>
          <div class="meta">
            <span>${enabled}${t.running ? " · 执行中" : ""}</span>
            <span>每 ${t.interval_min}±${t.jitter_min} 分</span>
            <span>已跑 ${t.run_count || 0} 次</span>
            <span>${escapeHtml(plats)}</span>
            ${t.next_run_at ? `<span>下次 ${escapeHtml(t.next_run_at)}</span>` : ""}
            ${t.enabled ? `<button class="btn ghost" data-stop-task="${escapeAttr(t.id)}">停止</button>` : ""}
          </div>
          <p class="snippet">${escapeHtml(t.last_message || "")}</p>
        </article>`;
    })
    .join("");
  box.querySelectorAll("[data-stop-task]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-stop-task");
      await api(`/api/crawl/tasks/${id}`, { method: "DELETE" });
      await loadTasks();
    });
  });
}

function syncTaskUi() {
  const scheduled = !!$("#crawlScheduled")?.checked;
  const opts = $("#taskScheduleOpts");
  if (opts) opts.hidden = !scheduled;
  loadTasks();
}

async function loadPublishPlatforms() {
  const data = await api("/api/platforms/publish");
  const sel = $("#publishPlatform");
  sel.innerHTML = "";
  (data.platforms || []).forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = `${p.name} (${p.id})${p.enabled ? "" : " · 未启用"}`;
    sel.appendChild(opt);
  });
  if (!sel.options.length) {
    const opt = document.createElement("option");
    opt.value = "typecho";
    opt.textContent = "typecho";
    sel.appendChild(opt);
  }
}

async function loadArticles() {
  const data = await api("/api/articles");
  const sel = $("#articleSelect");
  const current = sel.value;
  sel.innerHTML = `<option value="">选择本地文章…</option>`;
  (data.items || []).forEach((it) => {
    const opt = document.createElement("option");
    opt.value = it.path;
    opt.textContent = `${it.title} · ${it.mtime}`;
    sel.appendChild(opt);
  });
  if (current) sel.value = current;
}

function bind() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  $("#btnFilterNews").addEventListener("click", () => {
    loadPosts($("#newsKeyword").value.trim(), "", "news");
  });

  $("#btnExpand")?.addEventListener("click", async () => {
    const keyword = $("#newsKeyword").value.trim();
    if (!keyword) {
      setStatus($("#crawlStatus"), "请先填写主题关键词", "error");
      return;
    }
    if ($("#crawlExpand")) $("#crawlExpand").checked = true;
    setStatus($("#crawlStatus"), "正在用本地 AI 衍生搜索词…");
    try {
      const data = await api("/api/keywords/expand", {
        method: "POST",
        body: JSON.stringify({ keyword }),
      });
      const box = $("#expandPreview");
      const body = $("#expandPreviewBody");
      box.hidden = false;
      body.textContent = JSON.stringify(data, null, 2);
      setStatus(
        $("#crawlStatus"),
        data.success ? `衍生完成（${data.provider || "ai"}），可点「开始抓取」` : data.error || "衍生失败",
        data.success ? "ok" : "error"
      );
    } catch (e) {
      setStatus($("#crawlStatus"), String(e), "error");
    }
  });

  $("#crawlScheduled")?.addEventListener("change", syncTaskUi);

  $("#btnCrawl").addEventListener("click", async () => {
    const keyword = $("#newsKeyword").value.trim();
    const scheduled = !!$("#crawlScheduled")?.checked;
    const expand = !!$("#crawlExpand")?.checked;
    const platforms = selectedPlatforms();
    $("#btnCrawl").disabled = true;
    setStatus($("#crawlStatus"), scheduled ? "已创建周期任务…" : "已提交抓取任务…");
    try {
      const payload = {
        keyword,
        expand,
        platforms,
        scheduled,
        interval_min: Number($("#crawlInterval")?.value || 30),
        jitter_min: Number($("#crawlJitter")?.value || 10),
        run_now: true,
      };
      const data = await api("/api/crawl", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!data.success) {
        setStatus($("#crawlStatus"), data.error || "启动失败", "error");
        return;
      }
      await loadTasks();
      if (data.job_id) {
        await pollJob(data.job_id);
      } else if (data.task?.last_job_id) {
        await pollJob(data.task.last_job_id);
      } else {
        setStatus($("#crawlStatus"), "周期任务已启动", "ok");
      }
    } catch (e) {
      setStatus($("#crawlStatus"), String(e), "error");
    } finally {
      $("#btnCrawl").disabled = false;
    }
  });

  $("#btnLoadHistory").addEventListener("click", () => {
    loadPosts($("#historyKeyword").value.trim(), $("#historyPlatform").value.trim(), "history");
  });

  $("#btnCreate").addEventListener("click", async () => {
    const topic = $("#createTopic").value.trim();
    if (!topic) {
      setStatus($("#createStatus"), "请填写主题", "error");
      return;
    }
    $("#btnCreate").disabled = true;
    setStatus($("#createStatus"), "正在生成，可能需要数十秒…");
    try {
      const data = await api("/api/create", {
        method: "POST",
        body: JSON.stringify({
          topic,
          prompt: $("#createPrompt").value.trim(),
          style: $("#createStyle").value.trim() || "专业",
          words: Number($("#createWords").value || 2000),
        }),
      });
      if (!data.success) {
        setStatus($("#createStatus"), data.error || "生成失败", "error");
        return;
      }
      state.lastCreate = {
        title: topic,
        content: data.content || "",
        path: data.saved_path || "",
      };
      $("#createTitlePreview").textContent = topic;
      $("#createContentPreview").textContent = data.content || "";
      setStatus(
        $("#createStatus"),
        data.saved_path ? `已保存：${data.saved_path}` : "生成成功",
        "ok"
      );
      await loadArticles();
    } catch (e) {
      setStatus($("#createStatus"), String(e), "error");
    } finally {
      $("#btnCreate").disabled = false;
    }
  });

  $("#btnUseForPublish").addEventListener("click", () => {
    if (!state.lastCreate.content) {
      setStatus($("#createStatus"), "请先生成文章", "error");
      return;
    }
    $("#publishTitle").value = state.lastCreate.title;
    $("#publishContent").value = state.lastCreate.content;
    switchTab("publish");
  });

  $("#btnLoadArticles").addEventListener("click", loadArticles);

  $("#articleSelect").addEventListener("change", async () => {
    const path = $("#articleSelect").value;
    if (!path) return;
    const data = await api(`/api/article?path=${encodeURIComponent(path)}`);
    if (!data.success) {
      setStatus($("#publishStatus"), data.error || "读取失败", "error");
      return;
    }
    $("#publishTitle").value = data.title || "";
    $("#publishContent").value = data.content || "";
    setStatus($("#publishStatus"), `已载入 ${path}`, "ok");
  });

  $("#btnPublish").addEventListener("click", async () => {
    $("#btnPublish").disabled = true;
    setStatus($("#publishStatus"), "正在发布…");
    $("#publishResult").textContent = "";
    try {
      const data = await api("/api/publish", {
        method: "POST",
        body: JSON.stringify({
          title: $("#publishTitle").value.trim(),
          content: $("#publishContent").value.trim(),
          tags: $("#publishTags").value.trim(),
          platforms: [$("#publishPlatform").value].filter(Boolean),
          use_cdp: $("#useCdp").checked,
          debugger_url: $("#debuggerUrl").value.trim(),
          file: $("#articleSelect").value || undefined,
        }),
      });
      $("#publishResult").textContent = JSON.stringify(data, null, 2);
      setStatus(
        $("#publishStatus"),
        data.success ? "发布完成" : data.error || "发布失败",
        data.success ? "ok" : "error"
      );
    } catch (e) {
      setStatus($("#publishStatus"), String(e), "error");
    } finally {
      $("#btnPublish").disabled = false;
    }
  });
}

async function boot() {
  bind();
  syncTaskUi();
  await refreshHealth();
  await loadPublishPlatforms();
  await loadArticles();
  await loadPosts("", "", "history");
  setInterval(refreshHealth, 15000);
  setInterval(loadTasks, 20000);
}

boot();

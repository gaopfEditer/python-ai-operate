/**
 * 批量清理进度浮层
 */
/* global XApi */

const BatchOverlay = (() => {
  const ID = 'x-toolkit-batch-overlay';
  let stopFlag = false;

  function ensure() {
    let el = document.getElementById(ID);
    if (el) return el;
    el = document.createElement('div');
    el.id = ID;
    el.className = 'x-toolkit-overlay hidden';
    el.innerHTML = `
      <div class="x-toolkit-overlay-card">
        <div class="x-toolkit-head">
          <strong>批量清理</strong>
          <button type="button" class="x-toolkit-close" id="x-toolkit-batch-stop">停止</button>
        </div>
        <div id="x-toolkit-batch-log" class="x-toolkit-log"></div>
        <div id="x-toolkit-batch-bar" class="x-toolkit-bar"><div></div></div>
      </div>
    `;
    document.body.appendChild(el);
    el.querySelector('#x-toolkit-batch-stop').addEventListener('click', () => {
      stopFlag = true;
      log('用户请求停止…');
    });
    return el;
  }

  function log(line) {
    const box = document.getElementById('x-toolkit-batch-log');
    if (!box) return;
    box.textContent = (box.textContent ? box.textContent + '\n' : '') + line;
    box.scrollTop = box.scrollHeight;
  }

  function setProgress(cur, total) {
    const bar = document.querySelector('#x-toolkit-batch-bar > div');
    if (!bar) return;
    const pct = total ? Math.round((cur / total) * 100) : 0;
    bar.style.width = `${pct}%`;
  }

  function show() {
    ensure().classList.remove('hidden');
    document.getElementById('x-toolkit-batch-log').textContent = '';
    setProgress(0, 1);
    stopFlag = false;
  }

  function hide() {
    const el = document.getElementById(ID);
    if (el) el.classList.add('hidden');
  }

  function shouldStop() {
    return stopFlag;
  }

  async function runScan(options) {
    show();
    log('捕获 API 凭据…');
    XApi.mergeCreds(options.creds || {});
    const profile = await XApi.getSelfProfile();
    log(`当前用户 @${profile.screenName} (${profile.userId})`);
    log(`日期 ${options.startDate} ~ ${options.endDate}`);
    const items = await XApi.collectForCleanup({
      userId: profile.userId,
      startDate: options.startDate,
      endDate: options.endDate,
      types: options.types,
      onProgress: (msg) => log(msg),
    });
    log(`扫描完成：${items.length} 条待处理`);
    return { profile, items };
  }

  async function runDelete(items, delayMs) {
    if (!items.length) {
      log('无待删除项');
      return { ok: 0, fail: 0 };
    }
    log(`开始执行（间隔 ${delayMs}ms）…`);
    const res = await XApi.runCleanup(items, {
      delayMs,
      shouldStop,
      onItem: ({ index, total, item, phase, error }) => {
        setProgress(index, total);
        if (phase === 'running') {
          log(`[${index}/${total}] ${item.action} ${item.kind} ${item.text.slice(0, 40)}…`);
        } else if (phase === 'error') {
          log(`  ✗ ${error}`);
        }
      },
    });
    log(`完成：成功 ${res.ok} · 失败 ${res.fail}`);
    return res;
  }

  return { show, hide, log, runScan, runDelete, shouldStop };
})();

if (typeof window !== 'undefined') window.BatchOverlay = BatchOverlay;

# coding=utf-8
"""X Grok 网页文生图（CDP + Selenium），流程对齐 gemini_web_automation.generate_image_with_gemini_web。"""

from __future__ import annotations

import os
import sys
import time
import uuid
from typing import Any, Dict, List

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def generate_image_with_grok_web(
    prompt: str,
    *,
    out_dir: str,
    tag: str = "tti",
    keep_browser_open: bool = False,
) -> Dict[str, Any]:
    """在 https://x.com/i/grok 发送提示词并抓取回复中的图片。"""
    p = (prompt or "").strip()
    if not p:
        return {"ok": False, "error": "prompt 为空", "images": []}

    os.makedirs(out_dir, exist_ok=True)
    gen_prompt = (
        "请直接生成一张图片（必须输出图像，不要只给文字描述）。"
        "画面内容如下：\n\n"
        f"{p}"
    )

    driver = None
    saved: List[str] = []
    try:
        sys.path.insert(0, str(_auto_deal_eth_root()))
        from browser_automation import init_browser, navigate_in_last_tab
        from gemini_web_automation import _download_gemini_image

        from corpus.cdp_web_image import open_engine_tab

        driver = init_browser()
        debugger = (
            os.environ.get("CDP_DEBUGGER_URL")
            or os.environ.get("BROWSER_DEBUGGER_URL")
            or ""
        )
        open_engine_tab(driver, debugger, "grok")
        grok_url = os.getenv("GROK_WEB_URL", "https://x.com/i/grok").strip()
        print(f"  [grok-tti] 打开 Grok: {grok_url}", file=sys.stderr)
        navigate_in_last_tab(driver, grok_url)
        wait_open = float(os.getenv("GROK_WEB_TTI_OPEN_WAIT", "6"))
        time.sleep(wait_open)

        text_input = None
        for sel in (
            "div[contenteditable='true'][data-testid]",
            "div[contenteditable='true']",
            "textarea",
            "[data-testid='tweetTextarea_0']",
            "[aria-label*='Ask']",
            "[aria-label*='Grok']",
            "[placeholder*='Ask']",
        ):
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    try:
                        if not el.is_displayed():
                            continue
                        r = el.rect or {}
                        if (r.get("width") or 0) < 40:
                            continue
                        text_input = el
                        break
                    except Exception:
                        continue
                if text_input:
                    break
            except Exception:
                continue

        if text_input is None:
            return {
                "ok": False,
                "error": "未找到 Grok 输入框（请确认已登录 X 且打开 x.com/i/grok）",
                "images": [],
            }

        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", text_input)
            text_input.click()
        except Exception:
            pass

        try:
            driver.execute_script(
                """
                var el = arguments[0];
                var v = arguments[1] || '';
                if (el && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT')) {
                  el.value = v;
                } else if (el && el.isContentEditable) {
                  el.innerText = v;
                } else {
                  try { el.value = v; } catch (e) {}
                  try { el.innerText = v; } catch (e) {}
                }
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                """,
                text_input,
                gen_prompt,
            )
            text_input.send_keys(" ")
        except Exception:
            try:
                text_input.clear()
            except Exception:
                pass
            text_input.send_keys(gen_prompt)

        sent = False
        for sel in (
            "button[data-testid='grok-send-button']",
            "button[data-testid='sendButton']",
            "button[aria-label='Send']",
            "button[aria-label*='发送']",
            "button[type='submit']",
        ):
            try:
                btn = driver.find_element(By.CSS_SELECTOR, sel)
                if btn.is_displayed():
                    try:
                        btn.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", btn)
                    sent = True
                    break
            except Exception:
                continue
        if not sent:
            text_input.send_keys(Keys.RETURN)
        print("  [grok-tti] 已发送文生图请求", file=sys.stderr)

        max_wait = int(os.getenv("GROK_WEB_TTI_WAIT", "120"))
        min_w = int(os.getenv("GROK_WEB_TTI_MIN_WIDTH", "180"))
        deadline = time.time() + max_wait
        last_srcs: set[str] = set()

        def _collect_candidate_imgs():
            js = """
            const minW = arguments[0];
            const out = [];
            const imgs = Array.from(document.querySelectorAll('img'));
            for (const img of imgs) {
              try {
                const r = img.getBoundingClientRect();
                const w = Math.max(img.naturalWidth || 0, r.width || 0);
                const h = Math.max(img.naturalHeight || 0, r.height || 0);
                const src = img.currentSrc || img.src || '';
                if (!src || src.startsWith('data:image/svg')) continue;
                if (w < minW || h < minW * 0.45) continue;
                if (/profile_images|emoji|favicon/i.test(src) && w < 96) continue;
                out.push({src, w, h});
              } catch (e) {}
            }
            return out;
            """
            try:
                return driver.execute_script(js, min_w) or []
            except Exception:
                return []

        while time.time() < deadline:
            cands = _collect_candidate_imgs()
            cands = sorted(cands, key=lambda x: (x.get("w") or 0) * (x.get("h") or 0), reverse=True)
            new_srcs = [c["src"] for c in cands[:4] if c.get("src") and c["src"] not in last_srcs]
            if new_srcs:
                time.sleep(2.5)
                cands = _collect_candidate_imgs()
                cands = sorted(
                    cands, key=lambda x: (x.get("w") or 0) * (x.get("h") or 0), reverse=True
                )
                for i, c in enumerate(cands[:3]):
                    src = c.get("src") or ""
                    if not src or src in last_srcs:
                        continue
                    path = _download_gemini_image(driver, src, out_dir, tag=tag, index=i)
                    if path:
                        saved.append(path)
                        last_srcs.add(src)
                if saved:
                    break
            time.sleep(1.5)

        if not saved:
            fallback = os.path.join(out_dir, f"{tag}_{uuid.uuid4().hex[:8]}_page.png")
            try:
                driver.save_screenshot(fallback)
                if os.path.isfile(fallback) and os.path.getsize(fallback) > 64:
                    saved.append(fallback)
                    return {
                        "ok": False,
                        "error": "未抓到生成图，已保存整页截图供排查（Grok 是否支持出图？）",
                        "images": saved,
                        "method": "grok_web_tti_fallback_screenshot",
                    }
            except Exception:
                pass
            return {"ok": False, "error": "超时未检测到生成图片", "images": [], "method": "grok_web_tti"}

        return {
            "ok": True,
            "images": saved,
            "count": len(saved),
            "method": "grok_web_tti",
            "tag": tag,
        }
    except Exception as e:
        print(f"[ERROR] Grok 文生图失败: {e}", file=sys.stderr)
        return {"ok": False, "error": str(e), "images": saved, "method": "grok_web_tti"}
    finally:
        if driver is not None and not keep_browser_open:
            try:
                driver.quit()
            except Exception:
                pass


def _auto_deal_eth_root():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    import os as _os

    return Path(_os.environ.get("AUTO_DEAL_ETH_ROOT", root.parent / "auto-deal-eth"))

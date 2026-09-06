# coding=utf-8
"""X / Twitter CDP 发布：文本 + 图片 + 视频（需 Chrome 已登录）。"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Sequence

from public.platforms.cdp_common import (
    connect_cdp,
    human_pause,
    normalize_media_paths,
    open_url_new_tab,
    sanitize_typed_text,
    split_media,
    type_text_human,
    typed_text_is_valid,
    upload_files,
    wait_landed,
)

logger = logging.getLogger(__name__)

COMPOSE_URL = "https://x.com/compose/post"
HOME_URL = "https://x.com/home"


class XPublisher:
    def __init__(
        self,
        debugger_url: str = "127.0.0.1:9222",
        compose_url: str = COMPOSE_URL,
        close_driver: bool = False,
    ):
        self.debugger_url = debugger_url
        self.compose_url = compose_url
        self.close_driver = close_driver
        self.driver = None

    def publish(
        self,
        text: str = "",
        media_paths: Optional[Sequence[str]] = None,
        *,
        submit: bool = True,
        title: str = "",
    ) -> Dict:
        body = sanitize_typed_text((text or "").strip())
        if title and title.strip():
            # 社交帖：标题并入正文首行（若尚未包含）
            t = sanitize_typed_text(title.strip())
            if t and t not in body:
                body = f"{t}\n\n{body}".strip() if body else t

        media = normalize_media_paths(media_paths)
        images, videos = split_media(media)
        if not body and not media:
            return {"success": False, "error": "正文与媒体不能同时为空", "platform": "x"}

        steps: List[str] = []
        own = self.driver is None
        try:
            if own:
                self.driver = connect_cdp(self.debugger_url)
            driver = self.driver
            open_url_new_tab(driver, self.compose_url)
            href = wait_landed(
                driver, hosts=("x.com", "twitter.com"), timeout=18.0
            )
            logger.info("X 当前页 %s", href or "(空)")
            if "x.com" not in href.lower() and "twitter.com" not in href.lower():
                return {
                    "success": False,
                    "error": f"X 没有打开，当前是 {href or '未知页面'}",
                    "steps": steps,
                    "platform": "x",
                }
            steps.append("compose")
            human_pause(1.0, 1.8)

            editor = self._wait_editor(driver, timeout=25)
            if editor is None:
                # 回退首页再试
                open_url_new_tab(driver, HOME_URL)
                human_pause(1.0, 1.6)
                self._click_home_compose(driver)
                editor = self._wait_editor(driver, timeout=20)
            if editor is None:
                return {
                    "success": False,
                    "error": "未找到推文编辑框，请确认已登录 X",
                    "steps": steps,
                    "platform": "x",
                }
            steps.append("editor")

            if body:
                self._fill_text(driver, editor, body)
                steps.append("text")
                human_pause(0.4, 0.9)

            # 先图后视频（X 通常同一条帖里图/视频有限制，尽量都传）
            if images:
                self._ensure_media_input(driver)
                n = upload_files(driver, images, prefer="image", settle_s=3.0)
                steps.append(f"images:{n}")
                human_pause(1.0, 2.0)
            if videos:
                self._ensure_media_input(driver)
                n = upload_files(driver, videos, prefer="video", settle_s=5.0)
                steps.append(f"videos:{n}")
                # 视频处理较慢
                self._wait_media_ready(driver, timeout=90)
                human_pause(1.5, 2.5)

            if not submit:
                return {
                    "success": True,
                    "submitted": False,
                    "steps": steps + ["dry_run"],
                    "platform": "x",
                    "platform_name": "X / Twitter",
                }

            if not self._click_tweet(driver):
                return {
                    "success": False,
                    "error": "未找到或无法点击发帖按钮",
                    "steps": steps,
                    "platform": "x",
                }
            steps.append("submit")
            logger.info("X 已点击发帖，正在确认是否发出…")
            ok, url, reason = self._wait_tweet_confirmed(driver, body=body)
            if not ok:
                err = f"已点击发帖但推文未发出：{reason}"
                logger.warning("%s", err)
                return {
                    "success": False,
                    "submitted": False,
                    "error": err,
                    "steps": steps + ["submit_unconfirmed"],
                    "platform": "x",
                    "platform_name": "X / Twitter",
                }
            logger.info("X 已确认发出（%s）%s", reason, f" {url}" if url else "")
            return {
                "success": True,
                "submitted": True,
                "url": url,
                "steps": steps + ["confirmed"],
                "platform": "x",
                "platform_name": "X / Twitter",
                "media_count": len(media),
            }
        except Exception as e:
            logger.exception("X 发布失败")
            return {"success": False, "error": str(e), "steps": steps, "platform": "x"}
        finally:
            if own and self.close_driver and self.driver is not None:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None

    def _wait_editor(self, driver, timeout: float = 20):
        from selenium.webdriver.common.by import By

        deadline = time.time() + timeout
        selectors = [
            '[data-testid="tweetTextarea_0"] [contenteditable="true"]',
            'div[role="textbox"][data-testid^="tweetTextarea"] [contenteditable="true"]',
            'div.public-DraftEditor-content[contenteditable="true"]',
            'div[contenteditable="true"][role="textbox"]',
        ]
        while time.time() < deadline:
            for sel in selectors:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                except Exception:
                    els = []
                for el in els:
                    try:
                        if el.is_displayed():
                            return el
                    except Exception:
                        continue
            time.sleep(0.25)
        return None

    def _click_home_compose(self, driver) -> bool:
        from selenium.webdriver.common.by import By

        for sel in (
            'a[href="/compose/post"]',
            'a[data-testid="SideNav_NewTweet_Button"]',
            '[data-testid="SideNav_NewTweet_Button"]',
        ):
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, sel):
                    if el.is_displayed():
                        el.click()
                        return True
            except Exception:
                continue
        return False

    def _fill_text(self, driver, editor, text: str) -> None:
        text = sanitize_typed_text(text)
        if not text:
            return
        type_text_human(driver, editor, text, clear_first=True)
        try:
            got = str(
                driver.execute_script(
                    "const el=arguments[0]; return String((el && (el.innerText||el.textContent))||'');",
                    editor,
                )
                or ""
            )
        except Exception:
            got = ""
        if not typed_text_is_valid(got, text):
            raise RuntimeError(f"X 正文写入异常（乱码或垃圾），已中止: {(got or '')[:40]!r}")

    def _ensure_media_input(self, driver) -> None:
        """若尚无 file input，点媒体按钮唤出。"""
        from selenium.webdriver.common.by import By

        if driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]'):
            return
        for sel in (
            '[data-testid="fileInput"]',
            'button[aria-label*="Media"]',
            'button[aria-label*="媒体"]',
            'div[data-testid="toolBar"] button',
        ):
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, sel):
                    if el.tag_name.lower() == "input":
                        continue
                    if el.is_displayed():
                        el.click()
                        human_pause(0.3, 0.6)
                        if driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]'):
                            return
            except Exception:
                continue

    def _wait_media_ready(self, driver, timeout: float = 60) -> None:
        """等待上传进度消失 / 可发帖。"""
        from selenium.webdriver.common.by import By

        deadline = time.time() + timeout
        while time.time() < deadline:
            busy = False
            for sel in (
                '[role="progressbar"]',
                '[data-testid="progressBar"]',
                'div[aria-valuenow]',
            ):
                try:
                    for el in driver.find_elements(By.CSS_SELECTOR, sel):
                        if el.is_displayed():
                            busy = True
                            break
                except Exception:
                    pass
                if busy:
                    break
            btn = self._tweet_button(driver)
            if btn is not None and not busy:
                disabled = (btn.get_attribute("aria-disabled") or "").lower()
                if disabled not in ("true", "1"):
                    return
            time.sleep(0.5)

    def _tweet_button(self, driver):
        from selenium.webdriver.common.by import By

        for sel in (
            '[data-testid="tweetButton"]',
            '[data-testid="tweetButtonInline"]',
        ):
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, sel):
                    if el.is_displayed():
                        return el
            except Exception:
                continue
        return None

    def _click_tweet(self, driver) -> bool:
        btn = self._tweet_button(driver)
        if btn is None:
            return False
        try:
            disabled = (btn.get_attribute("aria-disabled") or "").lower()
            if disabled in ("true", "1"):
                # 再等媒体
                self._wait_media_ready(driver, timeout=45)
                btn = self._tweet_button(driver)
                if btn is None:
                    return False
            driver.execute_script("arguments[0].click();", btn)
            logger.info("X 已点击发帖按钮（尚未确认发出）")
            return True
        except Exception:
            try:
                btn.click()
                return True
            except Exception:
                return False

    def _tweet_compose_state(self, driver) -> dict:
        try:
            st = driver.execute_script(
                r"""
                const box = document.querySelector('[data-testid="tweetTextarea_0"] [contenteditable="true"]')
                  || document.querySelector('div[role="textbox"][data-testid^="tweetTextarea"] [contenteditable="true"]')
                  || document.querySelector('div.public-DraftEditor-content[contenteditable="true"]');
                function vis(el) {
                  if (!el || !el.getBoundingClientRect) return false;
                  const r = el.getBoundingClientRect();
                  if (r.width < 4 || r.height < 4) return false;
                  const st = window.getComputedStyle(el);
                  if (st.display === 'none' || st.visibility === 'hidden') return false;
                  return true;
                }
                const t = box ? String(box.innerText || '').replace(/\u200b/g, '').trim() : '';
                const toasts = [];
                for (const el of document.querySelectorAll('[data-testid="toast"], [role="alert"], [data-testid="confirmationSheetDialog"]')) {
                  const x = (el.innerText || '').trim().replace(/\s+/g, ' ');
                  if (x && x.length < 80) toasts.push(x);
                }
                return {
                  href: String(location.href || ''),
                  hasEditor: vis(box),
                  editorLen: t.length,
                  toasts: toasts.slice(0, 4)
                };
                """
            )
            return st if isinstance(st, dict) else {}
        except Exception:
            return {}

    def _wait_tweet_confirmed(self, driver, *, body: str, timeout: float = 14.0) -> tuple:
        had_body = len((body or "").strip()) >= 16
        deadline = time.time() + max(6.0, timeout)
        last: dict = {}
        closed_since = None
        while time.time() < deadline:
            last = self._tweet_compose_state(driver)
            href = str(last.get("href") or "")
            href_n = href.split("?")[0]
            if "/status/" in href_n:
                return True, href_n, "出现推文链接"
            toasts = " ".join(str(t) for t in (last.get("toasts") or []))
            tl = toasts.lower()
            if any(
                w in toasts
                for w in ("已发送", "已发布", "Your post was sent", "Your Tweet was sent")
            ) or "was sent" in tl:
                return True, href_n if "/status/" in href_n else "", f"成功提示「{toasts[:40]}」"
            if any(w in toasts for w in ("未能发送", "Couldn't send", "Try again")):
                return False, "", toasts[:80] or "页面提示发送失败"

            has_editor = bool(last.get("hasEditor"))
            editor_len = int(last.get("editorLen") or 0)
            still_compose = "/compose/" in href.lower()
            if has_editor and (had_body and editor_len >= 16):
                closed_since = None
            elif not has_editor and not still_compose:
                if closed_since is None:
                    closed_since = time.time()
                elif time.time() - closed_since >= 1.5:
                    return True, href_n if "/status/" in href_n else "", "编辑区已关闭"
            time.sleep(0.4)

        href = str(last.get("href") or "").split("?")[0]
        if "/status/" in href:
            return True, href, "出现推文链接"
        has_editor = bool(last.get("hasEditor"))
        editor_len = int(last.get("editorLen") or 0)
        if had_body and has_editor and editor_len >= 16:
            return False, "", f"编辑区还在（{editor_len} 字），点击没有发出去"
        if has_editor or "/compose/" in href.lower():
            return False, "", "发帖框还开着，推文未发出"
        if closed_since is not None:
            return True, "", "编辑区已关闭"
        return False, "", "点击后未出现推文链接或成功提示"


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
    upload_files,
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
            human_pause(2.0, 3.5)

            url = ""
            try:
                url = (driver.current_url or "").split("?")[0]
            except Exception:
                pass
            return {
                "success": True,
                "submitted": True,
                "url": url if "/status/" in url else "",
                "steps": steps,
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
            '[data-testid="tweetTextarea_0"]',
            'div[role="textbox"][data-testid^="tweetTextarea"]',
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
        type_text_human(driver, editor, text, min_delay=0.035, max_delay=0.12)

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
            return True
        except Exception:
            try:
                btn.click()
                return True
            except Exception:
                return False

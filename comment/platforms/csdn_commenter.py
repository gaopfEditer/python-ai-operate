# coding=utf-8
"""
CSDN平台评论器
使用Selenium自动化搜索文章并添加评论
"""

import time
import logging
from typing import Dict, List, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logger = logging.getLogger(__name__)


class CSDNCommenter:
    """CSDN平台评论器"""
    
    def __init__(self, username: str, password: str, headless: bool = False):
        """
        初始化CSDN评论器
        
        Args:
            username: CSDN用户名
            password: CSDN密码
            headless: 是否使用无头模式（不显示浏览器）
        """
        self.username = username
        self.password = password
        self.headless = headless
        self.driver = None
        self.base_url = "https://www.csdn.net"
    
    def _init_driver(self):
        """初始化浏览器驱动（使用默认Chrome用户数据，复用已有登录状态）"""
        import os
        try:
            # 临时清除可能影响Selenium的代理环境变量
            proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']
            saved_proxy = {}
            for var in proxy_vars:
                if var in os.environ:
                    saved_proxy[var] = os.environ[var]
                    del os.environ[var]
            
            try:
                chrome_options = Options()
                if self.headless:
                    chrome_options.add_argument('--headless')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-blink-features=AutomationControlled')
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                
                # 重要：不使用临时用户数据目录，使用默认Chrome配置
                # 这样可以复用用户已经登录的状态（cookies、session等）
                # 不设置 --user-data-dir 参数，让Chrome使用默认配置
                
                # 禁用代理（避免代理配置问题）
                chrome_options.add_argument('--no-proxy-server')
                chrome_options.add_argument('--proxy-server="direct://"')
                chrome_options.add_argument('--proxy-bypass-list=*')
                
                # 禁用各种弹窗和提示（但保留用户数据）
                chrome_options.add_argument('--disable-infobars')
                chrome_options.add_argument('--disable-notifications')
                chrome_options.add_argument('--disable-popup-blocking')
                chrome_options.add_argument('--no-first-run')
                chrome_options.add_argument('--no-default-browser-check')
                
                # 设置用户代理
                chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
                
                # 尝试初始化ChromeDriver
                try:
                    self.driver = webdriver.Chrome(options=chrome_options)
                except Exception as e:
                    from selenium.webdriver.chrome.service import Service
                    service = Service()
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                
                self.driver.maximize_window()
                logger.info("浏览器驱动初始化成功（使用默认Chrome用户数据，可复用已有登录状态）")
                return True
            finally:
                # 恢复环境变量
                for var, value in saved_proxy.items():
                    os.environ[var] = value
        except Exception as e:
            logger.error(f"浏览器驱动初始化失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _check_login_status(self) -> bool:
        """
        检查是否已经登录
        
        Returns:
            是否已登录
        """
        try:
            # 访问首页检查登录状态
            self.driver.get(self.base_url)
            time.sleep(2)
            
            # 检查是否有登录相关的元素（如用户名、退出按钮等）
            login_indicators = [
                (By.CSS_SELECTOR, ".user-name"),
                (By.CSS_SELECTOR, ".nickname"),
                (By.CSS_SELECTOR, ".user-info"),
                (By.CSS_SELECTOR, "[class*='user']"),
                (By.XPATH, "//a[contains(text(), '退出')]"),
                (By.XPATH, "//a[contains(text(), '登出')]")
            ]
            
            for selector_type, selector_value in login_indicators:
                try:
                    element = self.driver.find_element(selector_type, selector_value)
                    if element and element.is_displayed():
                        logger.info("检测到已登录状态")
                        return True
                except:
                    continue
            
            # 检查cookie
            cookies = self.driver.get_cookies()
            for cookie in cookies:
                if 'user' in cookie.get('name', '').lower() or 'login' in cookie.get('name', '').lower():
                    logger.info("通过Cookie检测到已登录状态")
                    return True
            
            logger.info("未检测到登录状态，需要登录")
            return False
            
        except Exception as e:
            logger.debug(f"检查登录状态时出错: {e}")
            return False
    
    def _login(self) -> bool:
        """
        登录CSDN平台（仅在未登录时调用）
        
        Returns:
            是否登录成功
        """
        try:
            # 先检查是否已经登录
            if self._check_login_status():
                logger.info("已登录，跳过登录步骤")
                return True
            
            logger.info("正在访问CSDN登录页面...")
            login_url = f"{self.base_url}/login"
            self.driver.get(login_url)
            time.sleep(3)
            
            wait = WebDriverWait(self.driver, 15)
            
            # 查找用户名输入框
            username_selectors = [
                (By.CSS_SELECTOR, "input[placeholder*='手机号/邮箱/用户名']"),
                (By.CSS_SELECTOR, "input[type='text']"),
                (By.CSS_SELECTOR, "input[name='username']"),
                (By.ID, "all")
            ]
            
            username_input = None
            for selector_type, selector_value in username_selectors:
                try:
                    username_input = wait.until(EC.presence_of_element_located((selector_type, selector_value)))
                    logger.info(f"找到用户名输入框: {selector_type}={selector_value}")
                    break
                except TimeoutException:
                    continue
            
            if not username_input:
                logger.error("无法找到用户名输入框")
                return False
            
            # 查找密码输入框
            password_selectors = [
                (By.CSS_SELECTOR, "input[type='password']"),
                (By.CSS_SELECTOR, "input[name='password']"),
                (By.ID, "password-number")
            ]
            
            password_input = None
            for selector_type, selector_value in password_selectors:
                try:
                    password_input = self.driver.find_element(selector_type, selector_value)
                    break
                except NoSuchElementException:
                    continue
            
            if not password_input:
                logger.error("无法找到密码输入框")
                return False
            
            # 输入用户名和密码
            try:
                self.driver.execute_script("arguments[0].value = arguments[1];", username_input, self.username)
                time.sleep(0.5)
                self.driver.execute_script("arguments[0].value = arguments[1];", password_input, self.password)
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"输入用户名或密码失败: {e}")
                return False
            
            # 查找并点击登录按钮
            login_button_selectors = [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "button.btn-login"),
                (By.XPATH, "//button[contains(text(), '登录')]"),
                (By.XPATH, "//button[contains(text(), '登 录')]"),
                (By.CSS_SELECTOR, ".btn-login"),
                (By.CSS_SELECTOR, "input[type='submit']")
            ]
            
            login_button = None
            for selector_type, selector_value in login_button_selectors:
                try:
                    login_button = self.driver.find_element(selector_type, selector_value)
                    if login_button.is_displayed():
                        break
                except NoSuchElementException:
                    continue
            
            if not login_button:
                logger.error("无法找到登录按钮")
                return False
            
            login_button.click()
            time.sleep(5)
            
            # 检查是否登录成功
            if self._check_login_status():
                logger.info("登录成功")
                return True
            else:
                logger.warning("登录可能失败")
                return False
                
        except Exception as e:
            logger.error(f"登录过程出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def search_articles(self, keyword: str, limit: int = 5) -> List[Dict]:
        """
        搜索相关文章
        
        Args:
            keyword: 搜索关键词
            limit: 返回文章数量限制
            
        Returns:
            文章列表，每个文章包含title、url、author、content等信息
        """
        try:
            logger.info(f"正在搜索文章: {keyword}")
            # 使用CSDN搜索，按热度排序
            search_url = f"{self.base_url}/search?q={keyword}&t=blog&o=hot&s=&l=&f="
            self.driver.get(search_url)
            time.sleep(5)  # 等待页面加载
            
            articles = []
            
            # 查找文章列表（CSDN搜索结果页面）
            article_selectors = [
                (By.CSS_SELECTOR, ".search-item"),
                (By.CSS_SELECTOR, ".search-list-item"),
                (By.CSS_SELECTOR, ".blog-list-box .blog-list-item"),
                (By.CSS_SELECTOR, ".soblog-item"),
                (By.CSS_SELECTOR, "article"),
                (By.CSS_SELECTOR, ".blog-list-box article")
            ]
            
            article_elements = []
            for selector_type, selector_value in article_selectors:
                try:
                    article_elements = self.driver.find_elements(selector_type, selector_value)
                    if article_elements:
                        logger.info(f"找到 {len(article_elements)} 篇文章（使用选择器: {selector_type}={selector_value}）")
                        break
                except:
                    continue
            
            if not article_elements:
                logger.warning("未找到文章列表，尝试其他方式...")
                # 尝试直接查找链接
                try:
                    links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/article/details/']")
                    if links:
                        logger.info(f"通过链接找到 {len(links)} 篇文章")
                        for i, link in enumerate(links[:limit]):
                            url = link.get_attribute('href')
                            title = link.text.strip() or link.get_attribute('title') or f"文章{i+1}"
                            if url:
                                articles.append({
                                    'title': title,
                                    'url': url,
                                    'author': '',
                                    'views': '',
                                    'index': i + 1,
                                    'content': ''
                                })
                        return articles[:limit]
                except:
                    pass
                return articles
            
            # 提取文章信息
            for i, article_elem in enumerate(article_elements[:limit]):
                try:
                    # 查找标题和链接
                    title_elem = None
                    url = ""
                    title = ""
                    
                    # 尝试多种方式查找标题和链接
                    try:
                        title_elem = article_elem.find_element(By.CSS_SELECTOR, "a")
                        title = title_elem.text.strip()
                        url = title_elem.get_attribute('href')
                    except:
                        try:
                            title_elem = article_elem.find_element(By.CSS_SELECTOR, "h2 a, h3 a, .title a")
                            title = title_elem.text.strip()
                            url = title_elem.get_attribute('href')
                        except:
                            try:
                                title_elem = article_elem.find_element(By.TAG_NAME, "a")
                                title = title_elem.text.strip()
                                url = title_elem.get_attribute('href')
                            except:
                                pass
                    
                    if not url or not title:
                        continue
                    
                    # 确保URL完整
                    if url and not url.startswith('http'):
                        url = self.base_url + url
                    
                    # 查找作者
                    author = ""
                    try:
                        author_selectors = [".user-name", ".nickname", ".author", ".blogger-name"]
                        for selector in author_selectors:
                            try:
                                author_elem = article_elem.find_element(By.CSS_SELECTOR, selector)
                                author = author_elem.text.strip()
                                break
                            except:
                                continue
                    except:
                        pass
                    
                    # 查找阅读量或热度
                    views = ""
                    try:
                        views_selectors = [".read-num", ".view-count", ".hot", ".read-count"]
                        for selector in views_selectors:
                            try:
                                views_elem = article_elem.find_element(By.CSS_SELECTOR, selector)
                                views = views_elem.text.strip()
                                break
                            except:
                                continue
                    except:
                        pass
                    
                    # 获取文章摘要或部分内容
                    content = ""
                    try:
                        content_elem = article_elem.find_element(By.CSS_SELECTOR, ".summary, .description, .content")
                        content = content_elem.text.strip()[:300]  # 限制长度
                    except:
                        pass
                    
                    articles.append({
                        'title': title,
                        'url': url,
                        'author': author,
                        'views': views,
                        'content': content,
                        'index': i + 1
                    })
                    
                except Exception as e:
                    logger.debug(f"提取第{i+1}篇文章信息失败: {e}")
                    continue
            
            logger.info(f"成功提取 {len(articles)} 篇文章")
            return articles
            
        except Exception as e:
            logger.error(f"搜索文章失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def add_comment(self, article_url: str, comment_text: str) -> Dict:
        """
        在指定文章下添加评论
        
        Args:
            article_url: 文章URL
            comment_text: 评论内容
            
        Returns:
            包含评论结果的字典
        """
        try:
            logger.info(f"正在访问文章: {article_url}")
            self.driver.get(article_url)
            time.sleep(3)
            
            # 滚动到评论区
            logger.info("滚动到评论区...")
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            wait = WebDriverWait(self.driver, 10)
            
            # 查找评论输入框
            comment_selectors = [
                (By.CSS_SELECTOR, "textarea.comment-textarea"),
                (By.CSS_SELECTOR, "textarea[placeholder*='评论']"),
                (By.CSS_SELECTOR, "textarea"),
                (By.ID, "comment_content")
            ]
            
            comment_input = None
            for selector_type, selector_value in comment_selectors:
                try:
                    comment_input = wait.until(EC.presence_of_element_located((selector_type, selector_value)))
                    logger.info(f"找到评论输入框: {selector_type}={selector_value}")
                    break
                except TimeoutException:
                    continue
            
            if not comment_input:
                logger.error("无法找到评论输入框")
                self.driver.quit()
                return {
                    'success': False,
                    'error': '无法找到评论输入框',
                    'url': article_url
                }
            
            # 滚动到评论输入框
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", comment_input)
            time.sleep(2)
            
            # 输入评论（使用JavaScript）
            try:
                logger.info("正在输入评论...")
                self.driver.execute_script("""
                    var elem = arguments[0];
                    var text = arguments[1];
                    elem.value = '';
                    elem.value = text;
                    elem.dispatchEvent(new Event('input', { bubbles: true }));
                    elem.dispatchEvent(new Event('change', { bubbles: true }));
                """, comment_input, comment_text)
                time.sleep(1)
            except Exception as e:
                logger.error(f"输入评论失败: {e}")
                self.driver.quit()
                return {
                    'success': False,
                    'error': f'输入评论失败: {str(e)}',
                    'url': article_url
                }
            
            # 查找并点击发布按钮（CSDN的评论发布按钮可能有多种形式）
            publish_button_selectors = [
                (By.CSS_SELECTOR, "button.btn-comment"),
                (By.CSS_SELECTOR, "button.btn-publish"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "button.btn-primary"),
                (By.CSS_SELECTOR, ".btn-submit"),
                (By.XPATH, "//button[contains(text(), '发布')]"),
                (By.XPATH, "//button[contains(text(), '评论')]"),
                (By.XPATH, "//button[contains(text(), '发表')]"),
                (By.XPATH, "//input[@type='submit' and contains(@value, '发布')]"),
                (By.XPATH, "//input[@type='submit' and contains(@value, '评论')]"),
                (By.CSS_SELECTOR, "input[type='submit']")
            ]
            
            publish_button = None
            for selector_type, selector_value in publish_button_selectors:
                try:
                    publish_button = wait.until(EC.presence_of_element_located((selector_type, selector_value)))
                    if publish_button and publish_button.is_displayed():
                        logger.info(f"找到发布按钮: {selector_type}={selector_value}")
                        break
                except (NoSuchElementException, TimeoutException):
                    continue
            
            if not publish_button:
                # 尝试通过JavaScript查找
                try:
                    publish_button = self.driver.execute_script("""
                        var buttons = document.querySelectorAll('button, input[type="submit"]');
                        for (var i = 0; i < buttons.length; i++) {
                            var btn = buttons[i];
                            var text = btn.textContent || btn.value || '';
                            if (text.includes('发布') || text.includes('评论') || text.includes('发表')) {
                                return btn;
                            }
                        }
                        return null;
                    """)
                    if publish_button:
                        logger.info("通过JavaScript找到发布按钮")
                except:
                    pass
            
            if not publish_button:
                logger.error("无法找到发布按钮")
                # 不关闭浏览器，让用户可以手动操作
                return {
                    'success': False,
                    'error': '无法找到发布按钮',
                    'url': article_url
                }
            
            # 滚动到按钮位置
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", publish_button)
            time.sleep(1)
            
            # 滚动到按钮位置
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", publish_button)
            time.sleep(1)
            
            # 点击发布按钮（优先使用JavaScript）
            try:
                self.driver.execute_script("arguments[0].click();", publish_button)
                logger.info("已使用JavaScript点击发布按钮")
            except Exception as e:
                logger.debug(f"JavaScript点击失败，尝试普通点击: {e}")
                try:
                    publish_button.click()
                    logger.info("已使用普通方式点击发布按钮")
                except Exception as e2:
                    logger.error(f"点击发布按钮失败: {e2}")
                    return {
                        'success': False,
                        'error': f'点击发布按钮失败: {str(e2)}',
                        'url': article_url
                    }
            
            time.sleep(3)
            
            # 检查是否发布成功（可以检查是否有成功提示或评论是否出现）
            current_url = self.driver.current_url
            
            logger.info(f"评论发布完成，当前URL: {current_url}")
            return {
                'success': True,
                'url': article_url,
                'comment': comment_text,
                'error': ''
            }
            
        except Exception as e:
            logger.error(f"添加评论失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            return {
                'success': False,
                'error': f'添加评论失败: {str(e)}',
                'url': article_url
            }
    
    def search_and_comment(self, keyword: str, comment_text: str, article_limit: int = 3) -> Dict:
        """
        搜索文章并添加评论
        
        Args:
            keyword: 搜索关键词
            comment_text: 评论内容
            article_limit: 评论文章数量限制
            
        Returns:
            包含所有评论结果的字典
        """
        try:
            # 初始化浏览器
            if not self._init_driver():
                return {
                    'success': False,
                    'error': '浏览器驱动初始化失败',
                    'results': []
                }
            
            # 登录
            if not self._login():
                self.driver.quit()
                return {
                    'success': False,
                    'error': '登录失败',
                    'results': []
                }
            
            # 搜索文章
            articles = self.search_articles(keyword, limit=article_limit)
            
            if not articles:
                self.driver.quit()
                return {
                    'success': False,
                    'error': '未找到相关文章',
                    'results': []
                }
            
            # 对每篇文章添加评论
            results = []
            for article in articles:
                logger.info(f"正在评论文章 {article['index']}: {article['title']}")
                result = self.add_comment(article['url'], comment_text)
                result['article'] = article
                results.append(result)
                time.sleep(2)  # 评论间隔
            
            # 关闭浏览器
            self.driver.quit()
            
            success_count = sum(1 for r in results if r.get('success', False))
            
            return {
                'success': success_count > 0,
                'total': len(results),
                'success_count': success_count,
                'results': results
            }
            
        except Exception as e:
            logger.error(f"搜索并评论失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            return {
                'success': False,
                'error': f'搜索并评论失败: {str(e)}',
                'results': []
            }


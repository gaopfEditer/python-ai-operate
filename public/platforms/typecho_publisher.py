# coding=utf-8
"""
Typecho平台发布器
使用Selenium自动化发布文章到Typecho平台
"""

import time
import logging
from typing import Dict, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logger = logging.getLogger(__name__)


class TypechoPublisher:
    """Typecho平台发布器"""
    
    def __init__(self, login_url: str, write_url: str, username: str, password: str, headless: bool = False):
        """
        初始化Typecho发布器
        
        Args:
            login_url: 登录页面URL
            write_url: 写文章页面URL
            username: 用户名
            password: 密码
            headless: 是否使用无头模式（不显示浏览器）
        """
        self.login_url = login_url
        self.write_url = write_url
        self.username = username
        self.password = password
        self.headless = headless
        self.driver = None
    
    def _init_driver(self):
        """初始化浏览器驱动"""
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
                
                # 不使用临时用户数据目录，使用默认Chrome配置
                # 这样可以避免"偏好设置文件已损坏"的弹窗
                # 注意：不设置--user-data-dir参数，让Chrome使用默认配置
                
                # 禁用各种弹窗和提示（但保留用户数据）
                chrome_options.add_argument('--disable-infobars')  # 禁用信息栏
                chrome_options.add_argument('--disable-notifications')  # 禁用通知
                chrome_options.add_argument('--disable-popup-blocking')  # 禁用弹窗阻止
                chrome_options.add_argument('--no-first-run')  # 跳过首次运行设置
                chrome_options.add_argument('--no-default-browser-check')  # 不检查默认浏览器
                
                # 禁用代理（避免代理配置问题）
                chrome_options.add_argument('--no-proxy-server')
                chrome_options.add_argument('--proxy-server="direct://"')
                chrome_options.add_argument('--proxy-bypass-list=*')
                
                # 设置用户代理，模拟真实浏览器
                chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
                
                # 尝试初始化ChromeDriver
                try:
                    self.driver = webdriver.Chrome(options=chrome_options)
                except Exception as e:
                    # 如果直接初始化失败，尝试使用 webdriver-manager（如果已安装）
                    try:
                        from selenium.webdriver.chrome.service import Service
                        try:
                            from webdriver_manager.chrome import ChromeDriverManager
                            service = Service(ChromeDriverManager().install())
                            logger.info("使用 webdriver-manager 自动下载 ChromeDriver")
                            self.driver = webdriver.Chrome(service=service, options=chrome_options)
                        except ImportError:
                            # webdriver-manager 未安装，尝试使用默认 Service
                            logger.info("webdriver-manager 未安装，尝试使用默认 Service")
                            service = Service()
                            self.driver = webdriver.Chrome(service=service, options=chrome_options)
                    except Exception as e2:
                        logger.error(f"尝试使用Service初始化也失败: {e2}")
                        raise e
                
                self.driver.maximize_window()
                logger.info("浏览器驱动初始化成功")
                return True
            finally:
                # 恢复环境变量
                for var, value in saved_proxy.items():
                    os.environ[var] = value
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            
            # 提供更详细的错误信息
            detailed_error = f"浏览器驱动初始化失败 ({error_type}): {error_msg}"
            
            # 根据错误类型提供解决建议
            suggestions = []
            if "chromedriver" in error_msg.lower() or "driver" in error_msg.lower():
                suggestions.append("请确保已安装 ChromeDriver，且版本与 Chrome 浏览器匹配")
                suggestions.append("推荐解决方案: pip install webdriver-manager (会自动管理 ChromeDriver)")
                suggestions.append("或者手动下载 ChromeDriver: https://chromedriver.chromium.org/")
            if "chrome" in error_msg.lower() and ("not found" in error_msg.lower() or "path" in error_msg.lower()):
                suggestions.append("请确保已安装 Google Chrome 浏览器")
                suggestions.append("Chrome 浏览器下载: https://www.google.com/chrome/")
            if "permission" in error_msg.lower() or "access" in error_msg.lower():
                suggestions.append("请检查文件权限，确保有权限访问 Chrome 和 ChromeDriver")
            if not suggestions:
                suggestions.append("请检查 Chrome 浏览器和 ChromeDriver 是否正确安装")
                suggestions.append("可以尝试运行: pip install webdriver-manager")
            
            logger.error(detailed_error)
            if suggestions:
                logger.error("可能的解决方案:")
                for suggestion in suggestions:
                    logger.error(f"  - {suggestion}")
            
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    def _login(self) -> bool:
        """
        登录Typecho平台
        
        Returns:
            是否登录成功
        """
        try:
            logger.info(f"正在访问登录页面: {self.login_url}")
            
            # 检查窗口是否打开
            try:
                _ = self.driver.window_handles
            except Exception:
                logger.error("浏览器窗口未打开")
                return False
            
            self.driver.get(self.login_url)
            time.sleep(4)  # 增加等待时间，等待页面完全加载
            
            # 再次检查窗口是否仍然打开
            try:
                current_url = self.driver.current_url
                logger.info(f"页面加载完成，当前URL: {current_url}")
            except Exception as e:
                logger.error(f"浏览器窗口已关闭: {e}")
                return False
            
            # 等待页面加载
            wait = WebDriverWait(self.driver, 3)  # 增加超时时间
            
            # 查找用户名输入框（可能是name="user"或id="user"）
            username_selectors = [
                (By.NAME, "user"),
                (By.ID, "user"),
                (By.CSS_SELECTOR, "input[name='user']"),
                (By.CSS_SELECTOR, "input[type='text']")
            ]
            
            # 等待页面稳定
            time.sleep(2)
            
            username_input = None
            for selector_type, selector_value in username_selectors:
                try:
                    # 检查窗口是否仍然打开
                    try:
                        handles = self.driver.window_handles
                        if not handles:
                            logger.error("浏览器窗口已关闭")
                            return False
                    except Exception as e:
                        logger.error(f"检查窗口状态失败: {e}")
                        return False
                    
                    # 使用更宽松的等待条件
                    username_input = wait.until(EC.presence_of_element_located((selector_type, selector_value)))
                    # 确保元素可见和可交互
                    wait.until(EC.element_to_be_clickable((selector_type, selector_value)))
                    logger.info(f"找到用户名输入框: {selector_type}={selector_value}")
                    break
                except TimeoutException:
                    logger.debug(f"选择器 {selector_type}={selector_value} 超时，尝试下一个")
                    continue
                except Exception as e:
                    logger.debug(f"尝试选择器 {selector_type}={selector_value} 失败: {e}")
                    # 检查窗口是否关闭
                    try:
                        _ = self.driver.window_handles
                    except:
                        logger.error("浏览器窗口在查找元素时关闭")
                        return False
                    continue
            
            if not username_input:
                logger.error("无法找到用户名输入框")
                # 尝试截图或获取页面源码用于调试
                try:
                    page_source = self.driver.page_source[:500]
                    logger.debug(f"页面源码片段: {page_source}")
                except:
                    pass
                return False
            
            # 查找密码输入框
            password_selectors = [
                (By.NAME, "pass"),
                (By.ID, "pass"),
                (By.CSS_SELECTOR, "input[name='pass']"),
                (By.CSS_SELECTOR, "input[type='password']")
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
                username_input.clear()
                username_input.send_keys(self.username)
                time.sleep(1)
                
                password_input.clear()
                password_input.send_keys(self.password)
                time.sleep(1)
            except Exception as e:
                logger.error(f"输入用户名或密码失败: {e}")
                return False
            
            # 查找并点击登录按钮
            login_button_selectors = [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
                (By.CSS_SELECTOR, "button"),
                (By.XPATH, "//button[contains(text(), '登录')]"),
                (By.XPATH, "//input[@type='submit']")
            ]
            
            login_button = None
            for selector_type, selector_value in login_button_selectors:
                try:
                    login_button = self.driver.find_element(selector_type, selector_value)
                    break
                except NoSuchElementException:
                    continue
            
            if not login_button:
                logger.error("无法找到登录按钮")
                return False
            
            login_button.click()
            time.sleep(5)  # 增加等待时间，等待页面跳转
            
            # 检查窗口是否仍然打开
            try:
                current_url = self.driver.current_url
            except Exception:
                logger.error("浏览器窗口在登录后关闭")
                return False
            
            # 检查是否登录成功（检查是否跳转到管理页面或写文章页面）
            if "admin" in current_url or "write" in current_url or current_url != self.login_url:
                logger.info(f"登录成功，当前URL: {current_url}")
                return True
            else:
                logger.warning(f"登录可能失败，当前URL: {current_url}")
                # 尝试检查是否有错误信息
                try:
                    error_elements = self.driver.find_elements(By.CSS_SELECTOR, ".error, .alert, .warning, .message")
                    if error_elements:
                        for elem in error_elements:
                            error_text = elem.text
                            if error_text:
                                logger.error(f"登录错误: {error_text}")
                except Exception as e:
                    logger.debug(f"检查错误信息时出错: {e}")
                return False
                
        except Exception as e:
            logger.error(f"登录过程出错: {e}")
            return False
    
    def publish(self, title: str, content: str, tags: Optional[str] = None, category: Optional[str] = None) -> Dict:
        """
        发布文章
        
        Args:
            title: 文章标题
            content: 文章内容
            tags: 标签（可选，逗号分隔）
            category: 分类（可选）
            
        Returns:
            包含发布结果的字典
        """
        try:
            # 初始化浏览器
            if not self._init_driver():
                return {
                    'success': False,
                    'error': '浏览器驱动初始化失败',
                    'url': ''
                }
            
            # 登录
            if not self._login():
                self.driver.quit()
                return {
                    'success': False,
                    'error': '登录失败',
                    'url': ''
                }
            
            # 访问写文章页面
            logger.info(f"正在访问写文章页面: {self.write_url}")
            self.driver.get(self.write_url)
            time.sleep(5)  # 增加等待时间
            
            wait = WebDriverWait(self.driver, 20)
            
            # 查找标题输入框
            title_selectors = [
                (By.NAME, "title"),
                (By.ID, "title"),
                (By.CSS_SELECTOR, "input[name='title']"),
                (By.CSS_SELECTOR, "input[type='text'][name='title']")
            ]
            
            title_input = None
            for selector_type, selector_value in title_selectors:
                try:
                    title_input = wait.until(EC.presence_of_element_located((selector_type, selector_value)))
                    logger.info(f"找到标题输入框: {selector_type}={selector_value}")
                    break
                except TimeoutException:
                    continue
                except Exception as e:
                    logger.debug(f"查找标题输入框失败: {e}")
                    continue
            
            if not title_input:
                self.driver.quit()
                return {
                    'success': False,
                    'error': '无法找到标题输入框',
                    'url': ''
                }
            
            # 输入标题（完全使用JavaScript，避免元素交互问题）
            try:
                logger.info("正在输入标题...")
                # 滚动到元素位置
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", title_input)
                time.sleep(1)
                # 使用JavaScript设置值，完全避免交互问题
                self.driver.execute_script("""
                    var elem = arguments[0];
                    var value = arguments[1];
                    elem.value = '';
                    elem.value = value;
                    elem.dispatchEvent(new Event('input', { bubbles: true }));
                    elem.dispatchEvent(new Event('change', { bubbles: true }));
                """, title_input, title)
                logger.info(f"标题已输入: {title}")
                time.sleep(1)
            except Exception as e:
                logger.error(f"输入标题失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                self.driver.quit()
                return {
                    'success': False,
                    'error': f'输入标题失败: {str(e)}',
                    'url': ''
                }
            
            # 查找内容编辑器（可能是textarea或iframe中的编辑器）
            content_input = None
            
            # 先尝试直接找textarea
            content_selectors = [
                (By.NAME, "text"),
                (By.ID, "text"),
                (By.CSS_SELECTOR, "textarea[name='text']"),
                (By.CSS_SELECTOR, "textarea")
            ]
            
            for selector_type, selector_value in content_selectors:
                try:
                    content_input = self.driver.find_element(selector_type, selector_value)
                    break
                except NoSuchElementException:
                    continue
            
            # 如果没找到textarea，可能是富文本编辑器（iframe）
            if not content_input:
                try:
                    # 尝试切换到iframe
                    iframe = self.driver.find_element(By.TAG_NAME, "iframe")
                    self.driver.switch_to.frame(iframe)
                    # 在iframe中查找编辑器
                    content_input = self.driver.find_element(By.TAG_NAME, "body")
                except:
                    pass
            
            if not content_input:
                self.driver.quit()
                return {
                    'success': False,
                    'error': '无法找到内容编辑器',
                    'url': ''
                }
            
            # 输入内容（完全使用JavaScript，避免元素交互问题）
            try:
                logger.info("正在输入文章内容...")
                if content_input.tag_name == 'body':
                    # 富文本编辑器，使用JavaScript设置内容
                    self.driver.execute_script("""
                        var elem = arguments[0];
                        var content = arguments[1];
                        elem.click();
                        elem.innerHTML = content;
                        elem.dispatchEvent(new Event('input', { bubbles: true }));
                        elem.dispatchEvent(new Event('change', { bubbles: true }));
                    """, content_input, content)
                else:
                    # 普通textarea，完全使用JavaScript
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", content_input)
                    time.sleep(1)
                    self.driver.execute_script("""
                        var elem = arguments[0];
                        var content = arguments[1];
                        elem.value = '';
                        elem.value = content;
                        elem.dispatchEvent(new Event('input', { bubbles: true }));
                        elem.dispatchEvent(new Event('change', { bubbles: true }));
                    """, content_input, content)
                
                logger.info("文章内容已输入")
                time.sleep(2)
            except Exception as e:
                logger.error(f"输入内容失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                self.driver.quit()
                return {
                    'success': False,
                    'error': f'输入内容失败: {str(e)}',
                    'url': ''
                }
            
            # 如果是在iframe中，切换回主页面
            try:
                self.driver.switch_to.default_content()
            except:
                pass
            
            # 输入标签（如果有）- 使用JavaScript避免交互问题
            if tags:
                logger.info("正在输入标签...")
                tag_selectors = [
                    (By.NAME, "tags"),
                    (By.ID, "tags"),
                    (By.CSS_SELECTOR, "input[name='tags']")
                ]
                
                tag_input = None
                for selector_type, selector_value in tag_selectors:
                    try:
                        tag_input = self.driver.find_element(selector_type, selector_value)
                        break
                    except NoSuchElementException:
                        continue
                
                if tag_input:
                    try:
                        # 使用JavaScript设置标签
                        self.driver.execute_script("""
                            var elem = arguments[0];
                            var value = arguments[1];
                            elem.value = '';
                            elem.value = value;
                            elem.dispatchEvent(new Event('input', { bubbles: true }));
                            elem.dispatchEvent(new Event('change', { bubbles: true }));
                        """, tag_input, tags)
                        logger.info(f"标签已输入: {tags}")
                        time.sleep(1)
                    except Exception as e:
                        logger.debug(f"输入标签失败: {e}")
            
            # 输入完内容后，必须先滚动到页面底部，确保发布按钮可见
            logger.info("滚动到页面底部，准备点击发布按钮...")
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)  # 等待滚动完成，确保页面完全加载
            
            # 查找并点击发布按钮（优先使用ID选择器）
            publish_button_selectors = [
                (By.ID, "btn-submit"),  # Typecho的发布按钮ID
                (By.CSS_SELECTOR, "button#btn-submit"),
                (By.CSS_SELECTOR, "button.btn.primary#btn-submit"),
                (By.CSS_SELECTOR, "button[type='submit'][id='btn-submit']"),
                (By.XPATH, "//button[@id='btn-submit']"),
                (By.XPATH, "//button[@id='btn-submit' and contains(text(), '发布')]"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//button[contains(text(), '发布')]"),
                (By.XPATH, "//button[contains(text(), '发布文章')]")
            ]
            
            publish_button = None
            for selector_type, selector_value in publish_button_selectors:
                try:
                    publish_button = wait.until(EC.presence_of_element_located((selector_type, selector_value)))
                    logger.info(f"找到发布按钮: {selector_type}={selector_value}")
                    # 滚动到按钮位置，确保完全可见
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", publish_button)
                    time.sleep(2)  # 等待滚动完成
                    # 等待按钮可点击
                    wait.until(EC.element_to_be_clickable((selector_type, selector_value)))
                    break
                except (NoSuchElementException, TimeoutException) as e:
                    logger.debug(f"选择器 {selector_type}={selector_value} 失败: {e}")
                    continue
            
            if not publish_button:
                # 尝试获取页面源码用于调试
                try:
                    page_source = self.driver.page_source
                    if 'btn-submit' in page_source:
                        logger.error("页面中存在btn-submit，但无法找到元素")
                    else:
                        logger.error("页面中不存在btn-submit")
                except:
                    pass
                self.driver.quit()
                return {
                    'success': False,
                    'error': '无法找到发布按钮',
                    'url': ''
                }
            
            # 点击发布按钮（使用JavaScript点击，更可靠）
            try:
                logger.info("正在点击发布按钮...")
                # 先尝试JavaScript点击
                self.driver.execute_script("arguments[0].click();", publish_button)
                logger.info("已使用JavaScript点击发布按钮")
            except Exception as e:
                logger.debug(f"JavaScript点击失败，尝试普通点击: {e}")
                try:
                    publish_button.click()
                    logger.info("已使用普通方式点击发布按钮")
                except Exception as e2:
                    logger.error(f"普通点击也失败: {e2}")
                    # 最后尝试：直接提交表单
                    try:
                        self.driver.execute_script("document.querySelector('form').submit();")
                        logger.info("已使用表单提交方式")
                    except Exception as e3:
                        logger.error(f"表单提交也失败: {e3}")
                        self.driver.quit()
                        return {
                            'success': False,
                            'error': f'点击发布按钮失败: {str(e3)}',
                            'url': ''
                        }
            
            time.sleep(5)  # 增加等待时间，等待发布完成
            
            # 获取发布后的URL（如果成功发布，通常会跳转到文章页面）
            published_url = self.driver.current_url
            
            # 关闭浏览器
            self.driver.quit()
            
            logger.info(f"文章发布成功: {published_url}")
            return {
                'success': True,
                'url': published_url,
                'title': title,
                'error': ''
            }
            
        except Exception as e:
            logger.error(f"发布过程出错: {e}")
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            
            return {
                'success': False,
                'error': f'发布失败: {str(e)}',
                'url': ''
            }


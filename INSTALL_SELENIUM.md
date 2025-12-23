# 安装Selenium依赖（使用uv）

## 使用uv安装

由于项目使用 `uv` 作为包管理工具，请使用以下命令安装依赖：

```bash
# 添加selenium依赖
uv add selenium

# 或者同步所有依赖（包括新添加的selenium）
uv sync
```

## 验证安装

```bash
# 检查selenium是否已安装
uv run python -c "import selenium; print(selenium.__version__)"
```

## ChromeDriver安装

除了Python包，还需要安装ChromeDriver：

### Windows

1. 下载ChromeDriver：
   - 访问：https://chromedriver.chromium.org/downloads
   - 或使用：https://googlechromelabs.github.io/chrome-for-testing/
   - 下载与你的Chrome浏览器版本匹配的ChromeDriver

2. 解压并添加到PATH：
   - 解压 `chromedriver.exe`
   - 将 `chromedriver.exe` 所在目录添加到系统PATH
   - 或放在项目根目录下

3. 验证安装：
   ```bash
   chromedriver --version
   ```

### macOS

```bash
# 使用Homebrew安装
brew install chromedriver

# 或手动下载并添加到PATH
```

### Linux

```bash
# Ubuntu/Debian
sudo apt-get install chromium-chromedriver

# 或手动下载并添加到PATH
```

## 使用uv运行

安装依赖后，使用uv运行脚本：

```bash
# 运行发布脚本
uv run python publish.py --file output/articles/article.md

# 运行示例脚本
uv run python example_publish.py
```

## 注意事项

1. **ChromeDriver版本**：确保ChromeDriver版本与Chrome浏览器版本匹配
2. **PATH配置**：确保ChromeDriver在系统PATH中，或使用绝对路径
3. **权限问题**：Linux/macOS可能需要给ChromeDriver执行权限：`chmod +x chromedriver`

## 故障排查

### 问题1：找不到ChromeDriver

**解决方案**：
- 检查ChromeDriver是否在PATH中
- 或在代码中指定ChromeDriver路径：
  ```python
  from selenium.webdriver.chrome.service import Service
  service = Service('/path/to/chromedriver')
  driver = webdriver.Chrome(service=service, options=options)
  ```

### 问题2：版本不匹配

**解决方案**：
- 检查Chrome浏览器版本：`chrome://version/`
- 下载对应版本的ChromeDriver
- 或使用Chrome for Testing：https://googlechromelabs.github.io/chrome-for-testing/








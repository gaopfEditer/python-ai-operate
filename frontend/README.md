# 经济指标日历

使用 FullCalendar 显示重要经济数据发布时间的日历应用。

## 功能特点

- 📅 显示主要经济指标的发布时间
- 🎨 不同颜色分类显示不同类型的经济指标
- ⏰ 自动转换美东时间到北京时间（考虑夏令时/冬令时）
- 📱 响应式设计，支持移动端
- 🔍 点击事件查看详细信息

## 包含的经济指标

1. **美联储利率决议（FOMC）** - 每年8次
2. **鲍威尔新闻发布会** - 紧随FOMC后
3. **非农就业数据（NFP）** - 每月第一个周五
4. **美国CPI** - 每月1次
5. **PPI（生产者物价指数）** - 每月1次
6. **ISM制造业PMI** - 每月第一个工作日
7. **ISM非制造业PMI** - 每月第三个工作日
8. **零售销售** - 每月第2个周五
9. **初请失业金人数** - 每周四

## 安装和运行

```bash
# 安装依赖
npm install

# 配置 API 密钥（可选，但推荐）
# 复制 .env.example 为 .env 并填入您的 TradingEconomics API 密钥
cp .env.example .env
# 编辑 .env 文件，填入您的 API 密钥

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 预览生产版本
npm run preview
```

## API 配置

为了获取准确的经济指标发布时间，建议配置 TradingEconomics API：

1. **获取 API 密钥**：
   - 访问 [TradingEconomics API](https://tradingeconomics.com/api/)
   - 注册账户并获取 API 密钥
   - API 密钥格式：`your_key:your_secret`

2. **配置环境变量**：
   ```bash
   # 在 frontend 目录下创建 .env 文件
   VITE_TRADING_ECONOMICS_API_KEY=your_key:your_secret
   ```

3. **数据来源**：
   - ✅ **有 API 密钥**：使用 TradingEconomics API 获取实际公布日期（推荐）
   - ⚠️ **无 API 密钥**：使用算法计算的日期（可能不够准确）

## 数据准确性

- **使用 API**：日期来自 TradingEconomics，为实际公布日期，每小时自动更新
- **不使用 API**：日期基于公布的规律算法计算，可能与实际日期有差异

## 技术栈

- React 18
- FullCalendar 6
- Vite

## 浏览器支持

现代浏览器（Chrome, Firefox, Safari, Edge）


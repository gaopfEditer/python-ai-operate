# AllNews Monitor 设计说明

独立目录 `allnews_mornitor/`，入口对标 `python console.py`：

```bash
# 先启动带远程调试的 Chrome（可与主站共用）
# 再启动本服务
python allnews_mornitor.py
# 默认 http://127.0.0.1:8790/
```

## 目标链路

```
CDP 抓取多平台热门流
  → 候选池（candidates.json）
  → 自动归档：点赞 & 评论 ≥ 滚动中位数（可配）
  → 手动归档：人工精选
  → 要素分析（hook/emotion/structure…）
  → 结合最新热点创作（后续）
```

## 平台

| id | 名称 | 策略 |
|----|------|------|
| xiaohongshu | 小红书 | CDP 探索流 |
| twitter | X | CDP 热门/高赞搜索 |
| zhihu | 知乎 | CDP 热榜 |
| sspai | 少数派 | CDP + 公开 API 兜底 |
| huxiu | 虎嗅 | CDP 首页 |
| kr36 | 36氪 | CDP 首页/热榜 |

配置见 `allnews_mornitor/config.yaml`。

## 头部流量判定

`archive.mode`:

- `both`（默认）：`likes >= median_likes` **且** `comments >= median_comments`
- `likes`：仅点赞过线
- `score`：综合分（赞/评/藏/转/阅加权）过线

中位数来自「滚动窗口样本 + 本批」，按平台隔离，见 `output/allnews_mornitor/platform_stats.json`。

## 数据落盘

```
output/allnews_mornitor/
  candidates.json      # 候选池
  archive.json         # 自动+手动归档素材
  platform_stats.json  # 中位数样本
```

## 目录结构

```
allnews_mornitor/
  app.py           # HTTP 控制台
  config.yaml
  models.py / store.py / archive.py
  cdp_browser.py   # 独立 tab，不顶当前页
  pipeline.py
  analyze.py       # 要素分析（Ollama 优先）
  platforms/       # 各站适配器
  static/          # 控制台前端
allnews_mornitor.py
```

## 后续

1. 细化各站选择器（登录态 / 反爬）
2. 批量要素分析 + 要素组合模板
3. 与主站 `console` 创作模块对接热点

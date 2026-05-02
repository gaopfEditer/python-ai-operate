# 平台操作提示词文件夹

## 说明
此文件夹包含各个平台的特定爬虫提示词文件，每个平台有独立的抓取规则和配置。

## 平台文件命名规范
- 微博：weibo_prompt.txt
- 知乎：zhihu_prompt.txt
- 小红书：xiaohongshu_prompt.txt
- 抖音：douyin_prompt.txt
- 百度热搜：baidu_prompt.txt
- 其他平台：{platform_name}_prompt.txt

## 平台提示词文件结构
每个平台提示词文件应包含：
1. 平台URL和API信息
2. 抓取规则（选择器、XPath等）
3. 反爬虫应对策略
4. 数据字段映射
5. 请求频率限制
6. 特殊处理逻辑

## 使用方式
在爬虫执行时，根据目标平台加载对应的提示词文件，使用其中的规则进行数据抓取。


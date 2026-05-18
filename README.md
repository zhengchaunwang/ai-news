# AI 资讯聚合

每日自动抓取 36氪、量子位、IT之家 AI 频道资讯，生成静态页面。

🔗 访问地址: [zhengchaunwang.github.io/ai-news](https://zhengchaunwang.github.io/ai-news/)

## 数据来源

| 来源 | 方式 |
|---|---|
| 36氪 AI | HTML 内嵌 JSON 解析 |
| 量子位 | RSS Feed |
| IT之家 | HTML 爬取 |

## 更新机制

- 每天 UTC 2:00（北京时间 10:00）自动更新
- 支持手动触发（GitHub Actions → Run workflow）

## 本地运行

```bash
pip install -r scraper/requirements.txt
python scraper/scrape_news.py
# 用浏览器打开 docs/index.html
```

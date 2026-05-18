#!/usr/bin/env python3
"""
AI 资讯聚合爬虫 - 每日自动抓取 36氪/量子位/IT之家 AI 资讯
输出: docs/data.json (供前端页面消费)
"""

import json
import re
import time
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import feedparser

# === 配置 ===
OUTPUT_DIR = Path(__file__).parent.parent / "docs"
OUTPUT_JSON = OUTPUT_DIR / "data.json"
DAYS_TO_KEEP = 14
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": USER_AGENT}

# 分类关键词映射
TAG_KEYWORDS = {
    "model": ["大模型", "LLM", "GPT", "Claude", "Gemini", "Llama", "开源模型", "模型发布",
              "DeepSeek", "Kimi", "通义", "文心", "智谱", "GLM", "Mistral", "参数量",
              "V4", "V5", "Pro", "Flash", "Sora", "视频生成", "图像生成", "文生图"],
    "research": ["研究", "论文", "Paper", "arxiv", "ICLR", "NeurIPS", "CVPR", "ICML",
                 "AAAI", "ACL", "EMNLP", "具身智能", "机器人", "多模态", "评估",
                 "评测", "基准", "Benchmark", "算法", "训练", "推理", "架构"],
    "business": ["融资", "IPO", "上市", "营收", "估值", "并购", "独角兽", "商业化",
                 "开源", "发布", "上线", "合作", "战略", "芯片", "GPU", "算力",
                 "Cursor", "Copilot", "编程", "办公", "生产力", "硬件"],
    "policy": ["政策", "监管", "法案", "合规", "安全", "隐私", "伦理", "就业",
               "替代", "立法", "FDA", "认证", "标准", "法规"]
}


def classify_tags(title: str, desc: str) -> list:
    """根据标题和摘要自动分类"""
    text = f"{title} {desc}".lower()
    tags = []
    for tag, keywords in TAG_KEYWORDS.items():
        if any(kw.lower() in text for kw in keywords):
            tags.append(tag)
    # 至少给一个标签
    if not tags:
        tags.append("business")
    return tags[:3]  # 最多3个标签


def is_china_related(title: str, desc: str) -> bool:
    """判断是否国内资讯"""
    cn_keywords = ["中国", "国内", "百度", "阿里", "腾讯", "华为", "小米", "字节", "快手",
                   "美团", "京东", "蚂蚁", "面壁", "月之暗面", "Kimi", "DeepSeek",
                   "智谱", "商汤", "旷视", "地平线", "小马智行", "蔚来", "理想",
                   "小鹏", "比亚迪", "讯飞", "360", "联通", "移动", "电信",
                   "清华", "北大", "上交", "浙大", "中科院", "深圳", "上海",
                   "北京", "杭州", "成都", "开源", "国产"]
    text = f"{title} {desc}"
    return any(kw in text for kw in cn_keywords)


def make_id(title: str) -> str:
    """生成唯一ID"""
    return hashlib.md5(title.encode()).hexdigest()[:12]


# === 36氪 爬虫 ===
def scrape_36kr() -> list:
    """从36氪 AI频道抓取，数据在 window.initialState 中"""
    articles = []
    try:
        url = "https://36kr.com/information/AI"
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()

        # 提取 window.initialState JSON（用括号平衡法解析，因为JSON内可能含分号）
        start_match = re.search(r'window\.initialState\s*=\s*\{', resp.text)
        if not start_match:
            print("[36kr] 未找到 initialState 数据")
            return articles

        # 从 { 开始用括号平衡找到完整 JSON
        json_start = resp.text.index('{', start_match.start())
        depth = 0
        json_end = json_start
        for i in range(json_start, min(json_start + 200000, len(resp.text))):
            if resp.text[i] == '{':
                depth += 1
            elif resp.text[i] == '}':
                depth -= 1
            if depth == 0:
                json_end = i + 1
                break

        data = json.loads(resp.text[json_start:json_end])
        item_list = data.get("information", {}).get("informationList", {}).get("itemList", [])

        cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_TO_KEEP)

        for item in item_list[:30]:  # 取前30条
            mat = item.get("templateMaterial", {})
            title = mat.get("widgetTitle", "").strip()
            if not title:
                continue

            # 处理日期
            publish_ts = mat.get("publishTime", 0)
            if publish_ts:
                pub_date = datetime.fromtimestamp(publish_ts / 1000, tz=timezone.utc)
            else:
                continue

            if pub_date < cutoff:
                continue

            summary = mat.get("summary", "").strip()
            item_id = mat.get("itemId", "")
            image = mat.get("widgetImage", "")

            desc = summary if summary else title[:60]
            tags = classify_tags(title, desc)
            if is_china_related(title, desc) and "cn" not in tags:
                tags.append("cn")

            articles.append({
                "id": make_id(title),
                "title": title,
                "desc": desc,
                "source": "36氪",
                "date": pub_date.strftime("%Y-%m-%d"),
                "dateLabel": f"{pub_date.month}月{pub_date.day}日",
                "tags": tags,
                "url": f"https://36kr.com/p/{item_id}",
                "image": image,
                "color": "#2563eb"
            })

        print(f"[36kr] 抓取 {len(articles)} 条")

    except Exception as e:
        print(f"[36kr] 抓取失败: {e}")

    return articles


# === 量子位 爬虫 ===
def scrape_qbitai() -> list:
    """从量子位 RSS Feed 抓取"""
    articles = []
    try:
        feed_url = "https://www.qbitai.com/feed"
        resp = requests.get(feed_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()

        feed = feedparser.parse(resp.text)
        cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_TO_KEEP)

        for entry in feed.entries[:40]:
            title = entry.get("title", "").strip()
            if not title:
                continue

            # 解析日期
            published = entry.get("published_parsed")
            if published:
                pub_date = datetime(*published[:6], tzinfo=timezone.utc)
            else:
                continue

            if pub_date < cutoff:
                continue

            link = entry.get("link", "")
            summary = entry.get("summary", "").strip()
            # 清理 HTML 标签
            if summary:
                soup = BeautifulSoup(summary, "html.parser")
                summary = soup.get_text().strip()[:200]

            desc = summary if summary else title[:60]
            tags = classify_tags(title, desc)
            if is_china_related(title, desc) and "cn" not in tags:
                tags.append("cn")

            # 获取图片
            image = ""
            if entry.get("media_content"):
                image = entry.media_content[0].get("url", "")
            elif summary and "<img" in summary:
                img_match = re.search(r'src=["\']([^"\']+)["\']', summary)
                if img_match:
                    image = img_match.group(1)

            articles.append({
                "id": make_id(title),
                "title": title,
                "desc": desc,
                "source": "量子位",
                "date": pub_date.strftime("%Y-%m-%d"),
                "dateLabel": f"{pub_date.month}月{pub_date.day}日",
                "tags": tags,
                "url": link,
                "image": image,
                "color": "#7c3aed"
            })

        print(f"[qbitai] 抓取 {len(articles)} 条")

    except Exception as e:
        print(f"[qbitai] 抓取失败: {e}")

    return articles


# === IT之家 AI 爬虫 ===
def scrape_ithome() -> list:
    """从IT之家 RSS 抓取，过滤 AI 相关文章"""
    articles = []
    try:
        feed_url = "https://www.ithome.com/rss/"
        resp = requests.get(feed_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()

        feed = feedparser.parse(resp.text)
        cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_TO_KEEP)

        # AI 相关关键词
        ai_keywords = ["AI", "人工智能", "大模型", "LLM", "GPT", "Claude", "Gemini",
                       "DeepSeek", "芯片", "GPU", "算力", "机器人", "自动驾驶",
                       "OpenAI", "谷歌", "英伟达", "微软", "Anthropic", "具身",
                       "机器学习", "深度学习", "神经网络", "AIGC", "Copilot",
                       "Kimi", "通义", "文心", "智谱", "Sora", "脑机接口"]

        for entry in feed.entries[:60]:
            title = entry.get("title", "").strip()
            if not title:
                continue

            # 过滤：标题或摘要包含 AI 关键词
            summary = entry.get("summary", "")
            soup_clean = BeautifulSoup(summary, "html.parser") if summary else None
            desc_text = soup_clean.get_text().strip()[:200] if soup_clean else ""
            full_text = f"{title} {desc_text}"

            is_ai = any(kw.lower() in full_text.lower() for kw in ai_keywords)
            if not is_ai:
                continue

            # 解析日期
            published = entry.get("published_parsed")
            if published:
                pub_date = datetime(*published[:6], tzinfo=timezone.utc)
            else:
                continue

            if pub_date < cutoff:
                continue

            link = entry.get("link", "")
            desc = desc_text if desc_text else title[:60]

            tags = classify_tags(title, desc)
            if is_china_related(title, desc) and "cn" not in tags:
                tags.append("cn")

            # 图片
            image = ""
            if summary and "<img" in summary:
                img_match = re.search(r'src=["\']([^"\']+)["\']', summary)
                if img_match:
                    image = img_match.group(1)

            articles.append({
                "id": make_id(title),
                "title": title,
                "desc": desc,
                "source": "IT之家",
                "date": pub_date.strftime("%Y-%m-%d"),
                "dateLabel": f"{pub_date.month}月{pub_date.day}日",
                "tags": tags,
                "url": link,
                "image": image,
                "color": "#d97706"
            })

        print(f"[ithome] 抓取 {len(articles)} 条")

    except Exception as e:
        print(f"[ithome] 抓取失败: {e}")

    return articles


# === 数据整理 ===
def merge_and_deduplicate(all_articles: list) -> list:
    """去重 + 按日期分组 + 限制条数"""
    seen = set()
    unique = []
    for article in all_articles:
        # 用标题前50字符去重（同一新闻可能被多个源报道，标题会有差异）
        key = article["title"][:50]
        if key not in seen:
            seen.add(key)
            unique.append(article)

    # 按日期分组
    date_groups = {}
    for article in unique:
        d = article["date"]
        if d not in date_groups:
            date_groups[d] = {
                "date": d,
                "dateLabel": article["dateLabel"],
                "id": f"d{d[-2:]}",
                "items": []
            }
        date_groups[d]["items"].append(article)

    # 排序：日期降序，每天最多8条
    result = []
    for date in sorted(date_groups.keys(), reverse=True):
        group = date_groups[date]
        group["items"] = group["items"][:8]
        result.append(group)

    return result


def main():
    print(f"=== AI 资讯爬虫开始 {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")

    # 依次抓取，间隔1秒
    all_articles = []

    articles_36kr = scrape_36kr()
    all_articles.extend(articles_36kr)
    time.sleep(1)

    articles_qbitai = scrape_qbitai()
    all_articles.extend(articles_qbitai)
    time.sleep(1)

    articles_ithome = scrape_ithome()
    all_articles.extend(articles_ithome)

    print(f"\n总计抓取 {len(all_articles)} 条")

    # 合并去重
    news_data = merge_and_deduplicate(all_articles)
    total = sum(len(g["items"]) for g in news_data)
    print(f"去重后 {total} 条，{len(news_data)} 天")

    # 来源统计
    sources_data = [
        {"name": "36氪 AI", "url": "36kr.com", "fullUrl": "https://36kr.com/information/AI", "desc": "科技创新商业媒体", "region": "cn"},
        {"name": "量子位", "url": "qbitai.com", "fullUrl": "https://www.qbitai.com", "desc": "关注前沿科技，专注于AI和量子计算领域", "region": "cn"},
        {"name": "IT之家", "url": "ithome.com", "fullUrl": "https://www.ithome.com/tag/AI", "desc": "IT资讯门户AI频道", "region": "cn"},
    ]

    # 保存（先读取旧数据，合并后写入）
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    old_data = {}
    if OUTPUT_JSON.exists():
        try:
            with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
                old = json.load(f)
                for day in old.get("newsData", []):
                    old_data[day["date"]] = day["items"]
        except Exception:
            pass

    # 合并：新数据覆盖同日旧数据
    new_data_by_date = {}
    for day in news_data:
        new_data_by_date[day["date"]] = day["items"]

    # 保留旧数据中不在新数据里的日期
    for date, items in old_data.items():
        if date not in new_data_by_date:
            new_data_by_date[date] = items

    # 过滤掉超过14天的数据
    cutoff_str = (datetime.now(timezone.utc) - timedelta(days=DAYS_TO_KEEP)).strftime("%Y-%m-%d")
    new_data_by_date = {d: items for d, items in new_data_by_date.items() if d >= cutoff_str}

    # 重新组织
    final_news = []
    for date in sorted(new_data_by_date.keys(), reverse=True):
        dt = datetime.strptime(date, "%Y-%m-%d")
        final_news.append({
            "date": date,
            "dateLabel": f"{dt.month}月{dt.day}日",
            "id": f"d{date[-2:]}",
            "items": new_data_by_date[date][:10]  # 每天最多10条
        })

    total = sum(len(g["items"]) for g in final_news)
    print(f"合并后 {total} 条，{len(final_news)} 天")

    output = {
        "newsData": final_news,
        "sourcesData": sources_data,
        "updateTime": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"),
        "totalNews": total
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"已保存到 {OUTPUT_JSON}")
    print("=== 爬虫完成 ===")


if __name__ == "__main__":
    main()

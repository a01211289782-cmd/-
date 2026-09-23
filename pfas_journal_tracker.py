#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PFAS 文献追踪脚本 —— 锁定高影响因子期刊

数据源（均为官方免费 API）：
  1. Crossref API  - 按期刊 ISSN 精确锁定，覆盖全部目标期刊（含 Nature/Science 子刊）
  2. PubMed        - 按期刊标准缩写限定，作为 EST/EI/EP/EHP/JHM 这类环境健康期刊的补充校验

注意：
  - JOURNALS 列表里的 ISSN 请务必核对一遍，尤其是你重点关心的 Nature/Science 子刊，
    以官方期刊主页公示的 ISSN 为准，我这里列的是常见环境相关子刊，你可以自行增删。
  - PUBMED_ABBREV 为空的期刊（大部分 Nature/Science 子刊）不会走 PubMed 校验，
    完全依赖 Crossref，这是因为它们不是生物医学期刊，PubMed 通常不收录。
"""

import requests
import json
import os
import hashlib
import time
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.header import Header

# ==================== 配置：目标期刊 ====================
# name: 显示名称 | issn: 用于 Crossref 精确过滤 | pubmed_abbrev: PubMed 标准缩写（NLM Title Abbreviation），没有则填 None

JOURNALS = [
    # ---- 环境健康类核心期刊 ----
    {"name": "Environmental Science & Technology (EST)", "issn": "0013-936X", "pubmed_abbrev": "Environ Sci Technol"},
    {"name": "Environmental Science & Technology Letters", "issn": "2328-8930", "pubmed_abbrev": "Environ Sci Technol Lett"},
    {"name": "Environment International (EI)", "issn": "0160-4120", "pubmed_abbrev": "Environ Int"},
    {"name": "Environmental Pollution (EP)", "issn": "0269-7491", "pubmed_abbrev": "Environ Pollut"},
    {"name": "Environmental Health Perspectives (EHP)", "issn": "0091-6765", "pubmed_abbrev": "Environ Health Perspect"},
    {"name": "Journal of Hazardous Materials (JHM)", "issn": "0304-3894", "pubmed_abbrev": "J Hazard Mater"},
    {"name": "Water Research", "issn": "0043-1354", "pubmed_abbrev": "Water Res"},
    {"name": "Chemosphere", "issn": "0045-6535", "pubmed_abbrev": "Chemosphere"},

    # ---- Nature 主刊及主力子刊 ----
    {"name": "Nature", "issn": "0028-0836", "pubmed_abbrev": None},
    {"name": "Nature Water", "issn": "2731-6084", "pubmed_abbrev": None},
    {"name": "Nature Sustainability", "issn": "2398-9629", "pubmed_abbrev": None},
    {"name": "Nature Communications", "issn": "2041-1723", "pubmed_abbrev": "Nat Commun"},
    {"name": "Nature Chemistry", "issn": "1755-4330", "pubmed_abbrev": "Nat Chem"},
    {"name": "Nature Materials", "issn": "1476-1122", "pubmed_abbrev": "Nat Mater"},
    {"name": "Nature Nanotechnology", "issn": "1748-3387", "pubmed_abbrev": "Nat Nanotechnol"},
    {"name": "Nature Geoscience", "issn": "1752-0894", "pubmed_abbrev": None},
    {"name": "Nature Catalysis", "issn": "2520-1158", "pubmed_abbrev": None},
    {"name": "Nature Energy", "issn": "2058-7546", "pubmed_abbrev": None},
    {"name": "Nature Climate Change", "issn": "1758-678X", "pubmed_abbrev": None},
    {"name": "Nature Food", "issn": "2662-1355", "pubmed_abbrev": None},
    {"name": "Nature Reviews Earth & Environment", "issn": "2662-138X", "pubmed_abbrev": None},
    {"name": "Nature Reviews Materials", "issn": "2058-8437", "pubmed_abbrev": None},
    {"name": "Nature Reviews Chemistry", "issn": "2397-3358", "pubmed_abbrev": None},

    # ---- Science 主刊及子刊 ----
    {"name": "Science", "issn": "0036-8075", "pubmed_abbrev": "Science"},
    {"name": "Science Advances", "issn": "2375-2548", "pubmed_abbrev": "Sci Adv"},

    # ---- 材料/化学类顶刊 ----
    {"name": "PNAS", "issn": "0027-8424", "pubmed_abbrev": "Proc Natl Acad Sci U S A"},
    {"name": "Angewandte Chemie International Edition", "issn": "1433-7851", "pubmed_abbrev": "Angew Chem Int Ed Engl"},
    {"name": "Journal of the American Chemical Society (JACS)", "issn": "0002-7863", "pubmed_abbrev": "J Am Chem Soc"},
    {"name": "ACS Applied Materials & Interfaces", "issn": "1944-8244", "pubmed_abbrev": "ACS Appl Mater Interfaces"},
    {"name": "Advanced Materials", "issn": "0935-9648", "pubmed_abbrev": "Adv Mater"},
    {"name": "Advanced Functional Materials (AFM)", "issn": "1616-301X", "pubmed_abbrev": "Adv Funct Mater"},
]

# ==================== 配置：PFAS 关键词 ====================
# 用于 Crossref 检索串 + 客户端标题二次过滤

PFAS_KEYWORDS = [
    "PFAS", "PFOA", "PFOS", "PFHxS", "PFNA", "GenX",
    "per- and polyfluoroalkyl", "perfluoroalkyl", "polyfluoroalkyl",
    "perfluorooctanoic", "perfluorooctane sulfonate", "fluorotelomer",
    "per-and polyfluoroalkyl",  # 无空格变体，部分文献写法不同
]

# 只保留最近 N 天内发表/更新的论文
RECENT_DAYS = 7

# 每个期刊单次最多抓取的候选条数（未经关键词过滤前）
MAX_CANDIDATES_PER_JOURNAL = 30

# Crossref 礼貌池：填你的真实邮箱能获得更快更稳定的响应（官方推荐做法，非必需）
CROSSREF_MAILTO = os.getenv("CROSSREF_MAILTO", "example@example.com")

# 邮件配置（与 monitor.py 共用同一套环境变量）
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "true").lower() not in ("false", "0", "no")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SENDER = os.getenv("SENDER_EMAIL", "")
PASSWORD = os.getenv("EMAIL_PASSWORD", "")
RECEIVER = os.getenv("RECEIVER_EMAIL", "")

HISTORY_FILE = "pfas_history.json"
HISTORY_MAX = 1000

session = requests.Session()
session.headers.update({
    "User-Agent": f"PFASTracker/1.0 (mailto:{CROSSREF_MAILTO})"
})


# ==================== 历史记录（去重） ====================

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"seen_keys": [], "last_check": None}


def save_history(history):
    history.setdefault("seen_keys", [])
    history["seen_keys"] = history["seen_keys"][-HISTORY_MAX:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def make_dedup_key(source, identifier):
    return hashlib.md5(f"{source}|{identifier}".encode("utf-8")).hexdigest()


# ==================== PFAS 关键词匹配 ====================

def is_pfas_relevant(title, abstract=""):
    text = f"{title} {abstract}".lower()
    return any(kw.lower() in text for kw in PFAS_KEYWORDS)


# ==================== 数据源 1：Crossref（按期刊 ISSN 精确锁定） ====================

def fetch_crossref_journal(journal):
    """
    Crossref API 文档: https://api.crossref.org/swagger-ui/index.html
    用 filter=issn:xxx 精确锁定期刊，query.bibliographic 用 PFAS 关键词做初筛，
    再用 is_pfas_relevant 对标题做客户端二次确认，避免漏判/误判。
    """
    results = []
    cutoff = datetime.utcnow() - timedelta(days=RECENT_DAYS)
    try:
        url = "https://api.crossref.org/works"
        params = {
            "filter": f"issn:{journal['issn']}",
            "query.bibliographic": "PFAS perfluoroalkyl polyfluoroalkyl",
            "sort": "published",
            "order": "desc",
            "rows": MAX_CANDIDATES_PER_JOURNAL,
            "mailto": CROSSREF_MAILTO,
        }
        resp = session.get(url, params=params, timeout=20)
        if resp.status_code != 200:
            print(f"  [Crossref:{journal['name']}] HTTP {resp.status_code}")
            return results

        items = resp.json().get("message", {}).get("items", [])
        matched = 0
        for item in items:
            title_list = item.get("title", [])
            if not title_list:
                continue
            title = title_list[0]

            if not is_pfas_relevant(title):
                continue

            date_parts = (
                item.get("published", {}).get("date-parts")
                or item.get("published-print", {}).get("date-parts")
                or item.get("published-online", {}).get("date-parts")
            )
            if not date_parts or not date_parts[0]:
                continue
            try:
                p = date_parts[0]
                pub_date = datetime(p[0], p[1] if len(p) > 1 else 1, p[2] if len(p) > 2 else 1)
            except Exception:
                continue
            if pub_date < cutoff:
                continue

            authors = []
            for a in item.get("author", [])[:6]:
                name = f"{a.get('given','')} {a.get('family','')}".strip()
                if name:
                    authors.append(name)

            doi = item.get("DOI", "")
            doi_url = f"https://doi.org/{doi}" if doi else item.get("URL", "")

            dedup_key = make_dedup_key("crossref", doi or doi_url)
            results.append({
                "source": journal["name"],
                "title": title,
                "authors": ", ".join(authors),
                "url": doi_url,
                "date": pub_date.strftime("%Y-%m-%d"),
                "dedup_key": dedup_key,
            })
            matched += 1
        print(f"  [Crossref:{journal['name']}] 候选 {len(items)} 篇，PFAS匹配 {matched} 篇（近{RECENT_DAYS}天）")
        time.sleep(1)
    except Exception as e:
        print(f"  [Crossref:{journal['name']}] 失败: {str(e)[:100]}")
    return results


# ==================== 数据源 2：PubMed（期刊 + 关键词联合限定，作为补充校验） ====================

def fetch_pubmed():
    """
    PubMed E-utilities 文档: https://www.ncbi.nlm.nih.gov/books/NBK25501/
    只对配置了 pubmed_abbrev 的期刊生效（主要是 EST/EI/EP/EHP/JHM 等生物医学类期刊）。
    """
    results = []
    api_key = os.getenv("NCBI_API_KEY", "")
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    journal_filters = [j["pubmed_abbrev"] for j in JOURNALS if j["pubmed_abbrev"]]
    if not journal_filters:
        return results

    keyword_term = " OR ".join(f'"{kw}"[tiab]' for kw in PFAS_KEYWORDS)
    journal_term = " OR ".join(f'"{ab}"[Journal]' for ab in journal_filters)
    term = f"({keyword_term}) AND ({journal_term})"

    try:
        search_params = {
            "db": "pubmed",
            "term": term,
            "retmax": 100,
            "sort": "date",
            "retmode": "json",
            "datetype": "pdat",
            "reldate": RECENT_DAYS,
        }
        if api_key:
            search_params["api_key"] = api_key

        resp = session.get(f"{base}/esearch.fcgi", params=search_params, timeout=20)
        if resp.status_code != 200:
            print(f"  [PubMed] esearch HTTP {resp.status_code}")
            return results
        id_list = resp.json().get("esearchresult", {}).get("idlist", [])
        if not id_list:
            print(f"  [PubMed] 匹配 0 篇（近{RECENT_DAYS}天）")
            return results

        time.sleep(0.4 if not api_key else 0.11)

        summary_params = {"db": "pubmed", "id": ",".join(id_list), "retmode": "json"}
        if api_key:
            summary_params["api_key"] = api_key

        resp = session.get(f"{base}/esummary.fcgi", params=summary_params, timeout=20)
        if resp.status_code != 200:
            print(f"  [PubMed] esummary HTTP {resp.status_code}")
            return results

        data = resp.json().get("result", {})
        for pmid in id_list:
            item = data.get(pmid)
            if not item:
                continue
            title = item.get("title", "")
            authors = [a.get("name", "") for a in item.get("authors", [])]
            pub_date = item.get("pubdate", "")
            source_journal = item.get("fulljournalname", "PubMed")
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

            dedup_key = make_dedup_key("pubmed", pmid)
            results.append({
                "source": source_journal,
                "title": title,
                "authors": ", ".join(authors[:6]),
                "url": url,
                "date": pub_date,
                "dedup_key": dedup_key,
            })
        print(f"  [PubMed] 匹配 {len(results)} 篇（近{RECENT_DAYS}天，覆盖 {len(journal_filters)} 本期刊）")
    except Exception as e:
        print(f"  [PubMed] 失败: {str(e)[:100]}")
    return results


# ==================== 邮件通知 ====================

def send_email(subject, content):
    if not EMAIL_ENABLED:
        print("邮件未启用，仅打印：")
        print(f"  主题: {subject}")
        print(f"  内容:\n{content}")
        return
    if not all([SENDER, PASSWORD, RECEIVER]):
        print("邮件配置不完整，仅打印：")
        print(f"  主题: {subject}")
        print(f"  内容:\n{content}")
        return

    msg = MIMEText(content, "plain", "utf-8")
    msg["From"] = Header(SENDER)
    msg["To"] = Header(RECEIVER)
    msg["Subject"] = Header(subject, "utf-8")
    try:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30)
        server.login(SENDER, PASSWORD)
        server.sendmail(SENDER, [RECEIVER], msg.as_string())
        server.quit()
        print("✅ 邮件发送成功")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")


# ==================== 主流程 ====================

def run_tracker():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始 PFAS 文献追踪...")
    history = load_history()
    all_papers = []

    print("正在按期刊查询 Crossref...")
    for journal in JOURNALS:
        all_papers.extend(fetch_crossref_journal(journal))

    print("正在查询 PubMed（补充校验）...")
    all_papers.extend(fetch_pubmed())

    # 去重
    seen_keys = set(history.get("seen_keys", []))
    new_papers = []
    for p in all_papers:
        key = p["dedup_key"]
        if key not in seen_keys:
            seen_keys.add(key)
            history["seen_keys"].append(key)
            new_papers.append(p)

    # 按日期倒序排列
    new_papers.sort(key=lambda p: p.get("date", ""), reverse=True)

    history["last_check"] = datetime.now().isoformat()
    save_history(history)

    if new_papers:
        print(f"🎉 发现 {len(new_papers)} 篇新的 PFAS 相关论文！")
        lines = [f"追踪时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"]
        for i, p in enumerate(new_papers, 1):
            lines.append(
                f"{i}. 【{p['source']}】{p['title']}\n"
                f"   作者: {p['authors'] or '未知'}\n"
                f"   日期: {p['date'] or '未知'}\n"
                f"   链接: {p['url']}\n"
            )
        content = "\n".join(lines)
        send_email(f"【PFAS文献追踪】发现 {len(new_papers)} 篇新论文", content)
    else:
        print("未发现新论文。")

    print("追踪结束。")


if __name__ == "__main__":
    run_tracker()

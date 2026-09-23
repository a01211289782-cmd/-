#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PFAS 文献追踪脚本 —— 锁定高影响因子期刊
功能：
1. Crossref：按期刊检索最近 7 天论文
2. PubMed：补充检索 PFAS 相关论文
3. 标题二次过滤 PFAS 相关性
4. DOI > PMID > 标题进行统一去重
5. 使用历史文件避免重复发送
6. 发送新论文邮件
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


# ============================================================
# 1. 目标期刊
# ============================================================

JOURNALS = [
    {"name": "Environmental Science & Technology (EST)", "issn": "0013-936X", "pubmed_abbrev": "Environ Sci Technol"},
    {"name": "Environmental Science & Technology Letters", "issn": "2328-8930", "pubmed_abbrev": "Environ Sci Technol Lett"},
    {"name": "Environment International (EI)", "issn": "0160-4120", "pubmed_abbrev": "Environ Int"},
    {"name": "Environmental Pollution (EP)", "issn": "0269-7491", "pubmed_abbrev": "Environ Pollut"},
    {"name": "Environmental Health Perspectives (EHP)", "issn": "0091-6765", "pubmed_abbrev": "Environ Health Perspect"},
    {"name": "Journal of Hazardous Materials (JHM)", "issn": "0304-3894", "pubmed_abbrev": "J Hazard Mater"},
    {"name": "Water Research", "issn": "0043-1354", "pubmed_abbrev": "Water Res"},
    {"name": "Chemosphere", "issn": "0045-6535", "pubmed_abbrev": "Chemosphere"},

    {"name": "Nature", "issn": "0028-0836", "pubmed_abbrev": "Nature"},
    {"name": "Nature Water", "issn": "2731-6084", "pubmed_abbrev": None},
    {"name": "Nature Sustainability", "issn": "2398-9629", "pubmed_abbrev": None},
    {"name": "Nature Communications", "issn": "2041-1723", "pubmed_abbrev": "Nat Commun"},
    {"name": "Nature Chemistry", "issn": "1755-4330", "pubmed_abbrev": "Nat Chem"},
    {"name": "Nature Materials", "issn": "1476-1122", "pubmed_abbrev": "Nat Mater"},
    {"name": "Nature Nanotechnology", "issn": "1748-3387", "pubmed_abbrev": "Nat Nanotechnol"},
    {"name": "Nature Geoscience", "issn": "1752-0894", "pubmed_abbrev": "Nat Geosci"},
    {"name": "Nature Catalysis", "issn": "2520-1158", "pubmed_abbrev": None},
    {"name": "Nature Energy", "issn": "2058-7546", "pubmed_abbrev": None},
    {"name": "Nature Climate Change", "issn": "1758-678X", "pubmed_abbrev": "Nat Clim Chang"},
    {"name": "Nature Food", "issn": "2662-1355", "pubmed_abbrev": None},
    {"name": "Nature Reviews Earth & Environment", "issn": "2662-138X", "pubmed_abbrev": None},
    {"name": "Nature Reviews Materials", "issn": "2050-8437", "pubmed_abbrev": None},
    {"name": "Nature Reviews Chemistry", "issn": "2397-3358", "pubmed_abbrev": None},

    {"name": "Science", "issn": "0036-8075", "pubmed_abbrev": "Science"},
    {"name": "Science Advances", "issn": "2375-2548", "pubmed_abbrev": "Sci Adv"},
    {"name": "PNAS", "issn": "0027-8424", "pubmed_abbrev": "Proc Natl Acad Sci U S A"},
    {"name": "Angewandte Chemie International Edition", "issn": "1433-7851", "pubmed_abbrev": "Angew Chem Int Ed Engl"},
    {"name": "JACS", "issn": "0002-7863", "pubmed_abbrev": "J Am Chem Soc"},
    {"name": "ACS Applied Materials & Interfaces", "issn": "1944-8244", "pubmed_abbrev": "ACS Appl Mater Interfaces"},
    {"name": "Advanced Materials", "issn": "0935-9648", "pubmed_abbrev": "Adv Mater"},
    {"name": "Advanced Functional Materials", "issn": "1616-301X", "pubmed_abbrev": "Adv Funct Mater"},
    {"name": "Chemical Reviews", "issn": "0009-2665", "pubmed_abbrev": "Chem Rev"},
    {"name": "Chem (Cell Press)", "issn": "2451-9294", "pubmed_abbrev": None},
    {"name": "Matter (Cell Press)", "issn": "2590-2385", "pubmed_abbrev": None},
    {"name": "Green Chemistry", "issn": "1463-9262", "pubmed_abbrev": "Green Chem"},
    {"name": "ACS Catalysis", "issn": "2155-5435", "pubmed_abbrev": "ACS Catal"},
    {"name": "Applied Catalysis B: Environmental", "issn": "0926-3373", "pubmed_abbrev": "Appl Catal B Environ"},
    {"name": "Small", "issn": "1613-6810", "pubmed_abbrev": "Small"},
    {"name": "Advanced Science", "issn": "2198-3844", "pubmed_abbrev": "Adv Sci (Weinh)"},
    {"name": "Journal of Materials Chemistry A", "issn": "2050-7488", "pubmed_abbrev": "J Mater Chem A"},
    {"name": "The Lancet Planetary Health", "issn": "2542-5196", "pubmed_abbrev": "Lancet Planet Health"},
    {"name": "The Lancet Public Health", "issn": "2468-2667", "pubmed_abbrev": "Lancet Public Health"},
    {"name": "The Lancet", "issn": "0140-6736", "pubmed_abbrev": "Lancet"},
    {"name": "The Lancet Global Health", "issn": "2214-109X", "pubmed_abbrev": "Lancet Glob Health"},
    {"name": "eClinicalMedicine", "issn": "2589-5370", "pubmed_abbrev": "EClinicalMedicine"},
    {"name": "ACS ES&T Water", "issn": "2690-0637", "pubmed_abbrev": None},
    {"name": "ACS ES&T Engineering", "issn": "2690-0645", "pubmed_abbrev": None},
    {"name": "Water Research X", "issn": "2589-9147", "pubmed_abbrev": None},
    {"name": "Environmental Science: Nano", "issn": "2051-8153", "pubmed_abbrev": "Environ Sci Nano"},
    {"name": "Environmental Science: Processes & Impacts", "issn": "2050-7887", "pubmed_abbrev": "Environ Sci Process Impacts"},
    {"name": "Journal of Environmental Management", "issn": "0301-4797", "pubmed_abbrev": "J Environ Manage"},
    {"name": "Ecotoxicology and Environmental Safety", "issn": "0147-6513", "pubmed_abbrev": "Ecotoxicol Environ Saf"},
    {"name": "Critical Reviews in Environmental Science and Technology", "issn": "1064-3389", "pubmed_abbrev": "Crit Rev Environ Sci Technol"},
    {"name": "npj Clean Water", "issn": "2059-7037", "pubmed_abbrev": None},
]


# ============================================================
# 2. PFAS 关键词
# ============================================================

PFAS_KEYWORDS = [
    "PFAS", "perfluoro", "polyfluoro", "PFOA", "PFOS",
    "PFHxS", "PFNA", "PFHxA", "PFBS", "PFBA",
    "GenX", "HFPO-DA", "fluorotelomer", "fluorotelomer"
]


# ============================================================
# 3. 参数
# ============================================================

RECENT_DAYS = 7
MAX_CANDIDATES_PER_JOURNAL = 30

CROSSREF_MAILTO = os.getenv("CROSSREF_MAILTO", "example@example.com")

EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "true").lower() == "true"

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SENDER = os.getenv("SENDER", "")
PASSWORD = os.getenv("PASSWORD", "")
RECEIVER = os.getenv("RECEIVER", "")

HISTORY_FILE = "pfas_history.json"
HISTORY_MAX = 1000


session = requests.Session()
session.headers.update({
    "User-Agent": f"PFASTracker/1.0 (mailto:{CROSSREF_MAILTO})"
})


# ============================================================
# 4. 历史记录
# ============================================================

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {"seen_keys": [], "last_check": None}

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"seen_keys": [], "last_check": None}


def save_history(history):
    history["seen_keys"] = history.get("seen_keys", [])[-HISTORY_MAX:]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


# ============================================================
# 5. 统一去重
# ============================================================

def make_dedup_key(doi="", pmid="", title=""):
    if doi:
        identifier = f"doi:{doi.lower().strip()}"
    elif pmid:
        identifier = f"pmid:{pmid.strip()}"
    else:
        identifier = f"title:{title.lower().strip()}"

    return hashlib.md5(identifier.encode("utf-8")).hexdigest()


# ============================================================
# 6. PFAS 标题过滤
# ============================================================

def is_pfas_relevant(title, abstract=""):
    text = f"{title} {abstract}".lower()
    return any(keyword.lower() in text for keyword in PFAS_KEYWORDS)


# ============================================================
# 7. Crossref 检索
# ============================================================

def fetch_crossref_journal(journal):
    results = []

    url = "https://api.crossref.org/journals/{}/works".format(journal["issn"])

    cutoff = datetime.utcnow() - timedelta(days=RECENT_DAYS)

    params = {
        "filter": f"from-pub-date:{cutoff.strftime('%Y-%m-%d')}",
        "query.bibliographic": "PFAS perfluoro polyfluoro PFOA PFOS",
        "rows": MAX_CANDIDATES_PER_JOURNAL,
        "sort": "published",
        "order": "desc",
        "mailto": CROSSREF_MAILTO
    }

    try:
        response = session.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        for item in data.get("message", {}).get("items", []):
            title_list = item.get("title", [])
            title = title_list[0].strip() if title_list else ""

            if not title or not is_pfas_relevant(title):
                continue

            doi = item.get("DOI", "").strip()
            doi_url = f"https://doi.org/{doi}" if doi else item.get("URL", "")

            published_parts = item.get("published", {}).get("date-parts", [[]])
            published = ""

            if published_parts and published_parts[0]:
                published = "-".join(str(x) for x in published_parts[0])

            dedup_key = make_dedup_key(doi=doi, title=title)

            results.append({
                "title": title,
                "doi": doi,
                "url": doi_url,
                "journal": journal["name"],
                "published": published,
                "source": "Crossref",
                "dedup_key": dedup_key
            })

        print(f"  {journal['name']}: {len(results)} 篇")

    except Exception as e:
        print(f"  {journal['name']}: Crossref 检索失败 - {e}")

    return results


# ============================================================
# 8. PubMed 检索
# ============================================================

def fetch_pubmed():
    results = []

    query = "(" + " OR ".join(f'"{k}"[Title/Abstract]' for k in PFAS_KEYWORDS) + ")"

    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": 200,
        "datetype": "pdat",
        "reldate": RECENT_DAYS
    }

    try:
        response = session.get(search_url, params=params, timeout=30)
        response.raise_for_status()

        pmids = response.json().get("esearchresult", {}).get("idlist", [])

        if not pmids:
            print("  PubMed: 0 篇")
            return results

        fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

        fetch_params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "json"
        }

        response = session.get(fetch_url, params=fetch_params, timeout=30)
        response.raise_for_status()

        data = response.json().get("result", {})

        for pmid in pmids:
            article = data.get(pmid, {})

            title = article.get("title", "").strip()

            if not title or not is_pfas_relevant(title):
                continue

            doi = ""

            for article_id in article.get("articleids", []):
                if article_id.get("idtype") == "doi":
                    doi = article_id.get("value", "").strip()
                    break

            journal = article.get("fulljournalname", "") or article.get("source", "")

            published = article.get("pubdate", "")

            dedup_key = make_dedup_key(
                doi=doi,
                pmid=pmid,
                title=title
            )

            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

            results.append({
                "title": title,
                "doi": doi,
                "url": url,
                "journal": journal,
                "published": published,
                "source": "PubMed",
                "pmid": pmid,
                "dedup_key": dedup_key
            })

        print(f"  PubMed: {len(results)} 篇")

    except Exception as e:
        print(f"  PubMed: 检索失败 - {e}")

    return results


# ============================================================
# 9. 邮件
# ============================================================

def send_email(subject, content):
    if not EMAIL_ENABLED:
        print("邮件发送已关闭。")
        return

    if not SENDER or not PASSWORD or not RECEIVER:
        print("邮件参数不完整，跳过发送。")
        return

    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = SENDER
    msg["To"] = RECEIVER

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SENDER, PASSWORD)
            server.sendmail(SENDER, [RECEIVER], msg.as_string())

        print("邮件发送成功。")

    except Exception as e:
        print(f"邮件发送失败：{e}")


# ============================================================
# 10. 主程序
# ============================================================

def run_tracker():

    print("=" * 60)
    print("PFAS 文献追踪开始")
    print("=" * 60)

    history = load_history()

    all_papers = []

    print("\n开始 Crossref 检索：")

    for journal in JOURNALS:
        all_papers.extend(fetch_crossref_journal(journal))
        time.sleep(0.2)

    print("\n开始 PubMed 检索：")

    pubmed_papers = fetch_pubmed()
    all_papers.extend(pubmed_papers)

    crossref_count = len(all_papers) - len(pubmed_papers)
    pubmed_count = len(pubmed_papers)

    # --------------------------------------------------------
    # 跨来源去重
    # --------------------------------------------------------

    unique_papers = []
    unique_keys = set()
    cross_source_duplicates = 0

    for paper in all_papers:
        key = paper["dedup_key"]

        if key in unique_keys:
            cross_source_duplicates += 1
            continue

        unique_keys.add(key)
        unique_papers.append(paper)

    # --------------------------------------------------------
    # 历史去重
    # --------------------------------------------------------

    seen_keys = set(history.get("seen_keys", []))

    new_papers = []
    history_existing = 0

    for paper in unique_papers:
        key = paper["dedup_key"]

        if key in seen_keys:
            history_existing += 1
        else:
            seen_keys.add(key)
            history["seen_keys"].append(key)
            new_papers.append(paper)

    # --------------------------------------------------------
    # 排序
    # --------------------------------------------------------

    new_papers.sort(
        key=lambda x: x.get("published", ""),
        reverse=True
    )

    history["last_check"] = datetime.now().isoformat()

    save_history(history)

    # --------------------------------------------------------
    # 统计
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print(f"Crossref 检索匹配：{crossref_count} 篇")
    print(f"PubMed 检索匹配：{pubmed_count} 篇")
    print(f"跨来源重复：{cross_source_duplicates} 篇")
    print(f"本次实际检索到：{len(unique_papers)} 篇")
    print(f"历史已有：{history_existing} 篇")
    print(f"本次新增：{len(new_papers)} 篇")
    print("=" * 60)

    # --------------------------------------------------------
    # 没有新论文
    # --------------------------------------------------------

    if not new_papers:
        print("\n本次检索到了 PFAS 文献，但没有发现新的论文。")
        return

    # --------------------------------------------------------
    # 邮件正文
    # --------------------------------------------------------

    lines = []

    lines.append("PFAS 文献追踪结果")
    lines.append("")
    lines.append(f"检索时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"本次新增：{len(new_papers)} 篇")
    lines.append("")

    for i, paper in enumerate(new_papers, 1):

        lines.append(f"{i}. {paper['title']}")
        lines.append(f"期刊：{paper['journal']}")
        lines.append(f"日期：{paper['published']}")
        lines.append(f"来源：{paper['source']}")

        if paper.get("doi"):
            lines.append(f"DOI：https://doi.org/{paper['doi']}")

        lines.append(f"链接：{paper['url']}")
        lines.append("")

    content = "\n".join(lines)

    print("\n新增论文：")

    for i, paper in enumerate(new_papers, 1):
        print(f"{i}. {paper['title']}")
        print(f"   期刊：{paper['journal']}")
        print(f"   日期：{paper['published']}")
        print(f"   来源：{paper['source']}")
        print(f"   {paper['url']}")
        print()

    send_email(
        f"PFAS 文献追踪：新增 {len(new_papers)} 篇",
        content
    )


# ============================================================
# 11. 执行
# ============================================================

if __name__ == "__main__":
    run_tracker()

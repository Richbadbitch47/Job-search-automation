import os
import json
import time
import urllib.parse
from datetime import datetime
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from jobspy import scrape_jobs

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GCP_CREDENTIALS = os.environ.get("GCP_CREDENTIALS")
GAS_WEBAPP_URL = os.environ.get("GAS_WEBAPP_URL")
SPREADSHEET_ID = "1pq8o0Suwn47YGJrSpzk_EqvGqS9vIxdwbRxeNC67QSY"

def init_google_sheet():
    creds_dict = json.loads(GCP_CREDENTIALS)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).worksheet("Internship Tracker")

def send_discord_msg(job, search_type):
    title = job.get('title', '未知岗位')
    company = job.get('company', '未知公司')
    location = job.get('location', '未知地点')
    job_url = job.get('job_url', '')
    
    type_label = "⏱️ [Part-time]" if "part-time" in search_type.lower() else "☀️ [Summer Internship]"
    
    if GAS_WEBAPP_URL:
        encoded_url = urllib.parse.quote(job_url, safe='')
        action_url = f"{GAS_WEBAPP_URL}?job_url={encoded_url}"
        links = f"🔗 [查看职位]({job_url})\n✅ [一键标记已投递]({action_url})"
    else:
        links = f"🔗 [查看职位]({job_url})"
        
    content = f"{type_label} **{title}**\n🏢 公司: {company}\n📍 地点: {location}\n{links}"
    
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": content})
        response.raise_for_status()
    except Exception as e:
        print(f"Discord通知发送失败: {e}")

def main():
    if not DISCORD_WEBHOOK_URL or not GCP_CREDENTIALS:
        print("错误: 缺少环境变量配置，请检查 GitHub Secrets！")
        return

    sheet = init_google_sheet()
    
    try:
        records = sheet.get_all_records()
        existing_urls = set(row.get('Job URL', '') for row in records if row.get('Job URL'))
    except Exception as e:
        print(f"读取表格失败: {e}")
        return
    
    # 恢复宽泛的搜索词，靠 Python 过滤
    search_queries = [
        {"type": "Part-time", "term": "part time student english hardware", "location": "Stockholm, Sweden"},
        {"type": "Part-time", "term": "working student english embedded", "location": "Stockholm, Sweden"},
        {"type": "Part-time", "term": "part time english data machine learning", "location": "Stockholm, Sweden"},
        {"type": "Part-time", "term": "part time student english energy", "location": "Stockholm, Sweden"},
        {"type": "Summer", "term": "summer intern english electrical", "location": "Stockholm, Sweden"},
        {"type": "Summer", "term": "summer intern english energy", "location": "Stockholm, Sweden"},
        {"type": "Summer", "term": "summer intern english embedded", "location": "Stockholm, Sweden"},
        {"type": "Summer", "term": "internship english machine learning", "location": "Stockholm, Sweden"}
    ]
    
    # 终极黑名单：扩充了高级全职头衔
    exclude_titles = [
        "thesis", "examensarbete", "exjobb", "master worker", "phd", "postdoc",
        "marketing", "sales", "business development", "account manager",
        "hr", "recruitment", "talent", "finance", "legal", "communications",
        "senior", "lead", "manager", "head", "director", "chief", "principal"
    ]
    
    new_rows = []
    for query in search_queries:
        print(f"正在搜索: {query['term']} in {query['location']}")
        try:
            jobs = scrape_jobs(
                site_name=["linkedin", "indeed"],
                search_term=query["term"],
                location=query["location"],
                results_wanted=10,
                hours_old=24  # 测试用 72 小时
            )
            
            if jobs.empty:
                continue
                
            for _, job in jobs.iterrows():
                job_url = job.get("job_url", "")
                title_lower = str(job.get("title", "")).lower()
                description = str(job.get("description", "")).lower()
                
                # 1. 标题黑名单拦截（学术、市场、高级管理岗）
                if any(word in title_lower for word in exclude_titles):
                    continue
                
                # 2. Part-time 专项拦截（防伪装全职）
                if query["type"] == "Part-time":
                    if "full-time" in title_lower or "full time" in title_lower or "heltid" in title_lower:
                        continue
                
                # 3. 瑞典语描述拦截
                if "svenska" in description or "swedish is required" in description or "fluent in swedish" in description:
                    continue
                    
                # 4. 去重拦截
                if not job_url or job_url in existing_urls:
                    continue
                    
                send_discord_msg(job, query["type"])
                
                today_str = datetime.now().strftime("%Y-%m-%d")
                new_rows.append([
                    today_str,
                    f"[{query['type']}] {job.get('title', '')}",
                    job.get("company", ""),
                    job.get("location", ""),
                    job_url,
                    "No",
                    "New"
                ])
                existing_urls.add(job_url)
                time.sleep(2)
        except Exception as e:
            print(f"抓取 {query['term']} 时发生错误: {e}")
            
    if new_rows:
        try:
            col_a = sheet.col_values(1)
            next_row = len(col_a) + 1
            end_row = next_row + len(new_rows) - 1
            sheet.update(values=new_rows, range_name=f"A{next_row}:G{end_row}")
            print(f"✅ 成功录入 {len(new_rows)} 个新岗位。")
        except Exception as e:
            print(f"写入表格时发生错误: {e}")
    else:
        print("🔍 过去 72 小时内没有发现符合条件的新岗位。")

if __name__ == "__main__":
    main()

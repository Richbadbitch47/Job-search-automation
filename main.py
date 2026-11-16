import os
import json
import time
from datetime import datetime
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from jobspy import scrape_jobs

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GCP_CREDENTIALS = os.environ.get("GCP_CREDENTIALS")
# 表格ID已指向你刚才生成的追踪表格
SPREADSHEET_ID = "1pq8o0Suwn47YGJrSpzk_EqvGqS9vIxdwbRxeNC67QSY"

def init_google_sheet():
    creds_dict = json.loads(GCP_CREDENTIALS)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).sheet1

def send_discord_msg(job):
    title = job.get('title', '未知岗位')
    company = job.get('company', '未知公司')
    location = job.get('location', '未知地点')
    job_url = job.get('job_url', '')
    
    content = f"**新实习岗位: {title}**\n🏢 公司: {company}\n📍 地点: {location}\n🔗 [点击申请]({job_url})"
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": content})
    except Exception as e:
        print(f"Discord通知发送失败: {e}")

def main():
    if not DISCORD_WEBHOOK_URL or not GCP_CREDENTIALS:
        print("错误: 缺少环境变量配置")
        return

    sheet = init_google_sheet()
    
    # 提取已存在的URL，防止重复发送和录入
    try:
        records = sheet.get_all_records()
        existing_urls = set(row.get('Job URL', '') for row in records if row.get('Job URL'))
    except Exception as e:
        print(f"读取表格失败，按空表处理: {e}")
        existing_urls = set()
    
    # 你可以修改这里的搜索意图和目标地点
    search_queries = [
        {"term": "embedded systems internship", "location": "Stockholm, Sweden"},
        {"term": "power electronics internship", "location": "Stockholm, Sweden"},
        {"term": "machine learning internship", "location": "Leuven, Belgium"},
        {"term": "energy internship", "location": "Remote"}
    ]
    
    new_rows = []
    for query in search_queries:
        print(f"正在搜索: {query['term']} in {query['location']}")
        try:
            jobs = scrape_jobs(
                site_name=["linkedin", "indeed", "glassdoor"],
                search_term=query["term"],
                location=query["location"],
                results_wanted=15,
                hours_old=12  # 因为每12小时运行一次，所以只看过去半天的新职位
            )
            
            if jobs.empty:
                continue
                
            for _, job in jobs.iterrows():
                job_url = job.get("job_url", "")
                if not job_url or job_url in existing_urls:
                    continue
                    
                send_discord_msg(job)
                
                today_str = datetime.now().strftime("%Y-%m-%d")
                new_rows.append([
                    today_str,
                    job.get("title", ""),
                    job.get("company", ""),
                    job.get("location", ""),
                    job_url,
                    "No",    # 默认未投递
                    "New"    # 默认Pipeline状态
                ])
                
                existing_urls.add(job_url)
                time.sleep(1.5) # 防止 Discord API 被速率限制
        except Exception as e:
            print(f"抓取 {query['term']} 时发生错误: {e}")
            
    # 批量更新至 Google Sheet
    if new_rows:
        sheet.append_rows(new_rows)
        print(f"✅ 成功录入 {len(new_rows)} 个新岗位。")
    else:
        print("🔍 过去12小时内没有发现新岗位。")

if __name__ == "__main__":
    main()

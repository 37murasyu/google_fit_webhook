import os
import datetime
import requests
from flask import Flask
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

app = Flask(__name__)

@app.route("/")
def index():
    return "Google Fit Webhook is running!"

@app.route("/wake_alert")
def wake_alert():
    print("🔔 wake_alert triggered!")
    try:
        result = run_alert()
        return result, 200
    except Exception as e:
        print("❌ error:", e)
        return "Internal Server Error", 500

def run_alert():
    print("✅ run_alert: Start")

    creds = Credentials(
        token=None,  # ここはNoneでOK。refresh_tokenで更新されます
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        scopes=[
            "https://www.googleapis.com/auth/fitness.activity.read",
            "https://www.googleapis.com/auth/fitness.sleep.read"
        ]
    )

    now = datetime.datetime.utcnow()
    start = int(now.timestamp() * 1000)
    end = int((now + datetime.timedelta(minutes=30)).timestamp() * 1000)

    fitness = build("fitness", "v1", credentials=creds)
    datasources = fitness.users().dataSources().list(userId="me").execute()

    # stepカウント用のデータソースを探す
    step_source = next(
        (s for s in datasources["dataSource"]
         if "derived:com.google.step_count.delta" in s["dataStreamId"]),
        None
    )

    if not step_source:
        raise Exception("❌ Step data source not found")

    dataset_id = f"{start}000000-{end}000000"
    steps_data = fitness.users().dataSources(). \
        datasets().get(
            userId="me",
            dataSourceId=step_source["dataStreamId"],
            datasetId=dataset_id
        ).execute()


    total_steps = 0
    for point in steps_data.get("point", []):
        total_steps += point["value"][0]["intVal"]

    print(f"🚶 Total steps: {total_steps}")

    if total_steps < 1000:
        msg = f"起床後30分以内の歩数が {total_steps} 歩です。もっと動こう！"
        requests.post(
            "https://api.pushbullet.com/v2/pushes",
            json={"type": "note", "title": "ウォーキング不足アラート", "body": msg},
            headers={"Access-Token": os.environ["PB_TOKEN"]}
        )
        print("📲 Pushbullet通知送信")
        return msg
    else:
        print("💤 十分な歩数のため通知不要")
        return f"歩数OK: {total_steps} 歩"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # RenderではPORTが自動で入る
    app.run(host="0.0.0.0", port=port)


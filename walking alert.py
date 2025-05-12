import os
import requests
from datetime import datetime, timedelta, timezone
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# --- 設定 ---
SCOPES = [
    'https://www.googleapis.com/auth/fitness.activity.read',
    'https://www.googleapis.com/auth/fitness.sleep.read'
]
PB_TOKEN = 'o.txyD655ztabTCzPEfQpKJAKMQta4mLaf'
STEP_THRESHOLD = 1000
JST = timezone(timedelta(hours=9))

# --- 認証 ---
def authenticate():
    if os.path.exists('token.json'):
        return Credentials.from_authorized_user_file('token.json', SCOPES)
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    with open("token.json", "w") as token:
        token.write(creds.to_json())
    return creds

# --- ナノ秒変換 ---
def nanoseconds(dt):
    return int(dt.timestamp() * 1e9)

# --- 起床時間を推定（最も長い睡眠の終了） ---
def estimate_wake_time(service):
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=2)
    dataset = f"{nanoseconds(start)}-{nanoseconds(now)}"

    res = service.users().dataSources().datasets().get(
        userId='me',
        dataSourceId='derived:com.google.sleep.segment:com.google.android.gms:merged',
        datasetId=dataset
    ).execute()

    sleep_data = res.get('point', [])
    valid_stages = [2, 3, 4]
    segments = [
        (
            int(p['startTimeNanos']) / 1e9,
            int(p['endTimeNanos']) / 1e9
        ) for p in sleep_data
        if p['value'][0].get('intVal') in valid_stages
    ]

    if not segments:
        return None

    # 10分以内の中断は同一睡眠として連結
    grouped = []
    buffer = []
    for s, e in sorted(segments):
        if not buffer:
            buffer = [s, e]
        elif s - buffer[1] <= 600:
            buffer[1] = max(buffer[1], e)
        else:
            grouped.append(tuple(buffer))
            buffer = [s, e]
    if buffer:
        grouped.append(tuple(buffer))

    # 最後のまとまった睡眠（30分以上）を起床と見なす
    meaningful = [g for g in grouped if g[1] - g[0] >= 1800]
    if not meaningful:
        return None

    return datetime.fromtimestamp(meaningful[-1][1], tz=timezone.utc).astimezone(JST)

# --- 歩数取得 ---
def get_steps(service, start_dt, end_dt):
    dataset = f"{nanoseconds(start_dt)}-{nanoseconds(end_dt)}"
    res = service.users().dataSources().datasets().get(
        userId='me',
        dataSourceId='derived:com.google.step_count.delta:com.google.android.gms:estimated_steps',
        datasetId=dataset
    ).execute()
    return sum(p['value'][0]['intVal'] for p in res.get('point', []))

# --- Pushbullet通知 ---
def send_pushbullet_alert(title, message):
    requests.post(
        "https://api.pushbullet.com/v2/pushes",
        headers={
            "Access-Token": PB_TOKEN,
            "Content-Type": "application/json"
        },
        json={
            "type": "note",
            "title": title,
            "body": message
        }
    )

# --- メイン処理 ---
def main():
    creds = authenticate()
    service = build('fitness', 'v1', credentials=creds)

    wake_time = estimate_wake_time(service)
    if not wake_time:
        print("❌ 起床時間が取得できませんでした")
        return

    print(f"✅ 起床時間（JST）: {wake_time.strftime('%Y-%m-%d %H:%M:%S')}")

    end_time = wake_time + timedelta(minutes=30)
    steps = get_steps(service, wake_time, end_time)
    print(f"🚶 起床後30分の歩数: {steps} 歩")

    if steps < STEP_THRESHOLD:
        print("⚠️ 歩数不足 → Pushbullet通知送信")
        send_pushbullet_alert("⚠️ 歩数アラート", f"{wake_time.strftime('%H:%M')} 起床後30分で {steps} 歩です。動きましょう！")
    else:
        print("🎉 歩数目標達成！通知は不要です")

if __name__ == "__main__":
    main()

from flask import Flask
import subprocess

app = Flask(__name__)

@app.route("/wake_alert")
def wake_alert():
    subprocess.Popen(["python", "google_fit_alert.py"])
    return "Wake alert received", 200

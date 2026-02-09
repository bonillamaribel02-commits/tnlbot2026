from flask import Flask
from threading import Thread
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot activo"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False  # 🔴 IMPORTANTE
    )

def keep_alive():
    t = Thread(target=run, daemon=True)  # 🔴 daemon=True
    t.start()
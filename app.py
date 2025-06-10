from flask import Flask, request

app = Flask(__name__)

@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_data(as_text=True)
    print("✅ Webhook受信:", body)
    return "OK", 200

@app.route("/", methods=["GET"])
def index():
    return "OK: Flask is running", 200

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

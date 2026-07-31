from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "<h1>Finanzas Familia NP</h1><p>Aplicación funcionando</p>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
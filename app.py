from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///finanzas.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class Gasto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.String(20))
    descripcion = db.Column(db.String(200))
    monto = db.Column(db.Float)
    categoria = db.Column(db.String(50))
    responsable = db.Column(db.String(50))
    medio_pago = db.Column(db.String(50))


with app.app_context():
    db.create_all()


@app.route("/")
def home():
    return "<h1>Finanzas Familia NP</h1><p>Base de datos creada</p>"

@app.route("/nuevo", methods=["GET", "POST"])
def nuevo_gasto():

    if request.method == "POST":

        gasto = Gasto(
            fecha=request.form["fecha"],
            descripcion=request.form["descripcion"],
            monto=float(request.form["monto"]),
            categoria=request.form["categoria"],
            responsable=request.form["responsable"],
            medio_pago=request.form["medio_pago"]
        )

        db.session.add(gasto)
        db.session.commit()

        return "Gasto guardado correctamente"

    return render_template("nuevo_gasto.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
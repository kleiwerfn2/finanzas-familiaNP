from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////app/data/finanzas.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

@app.template_filter('moneda')
def moneda(valor):

    if valor is None:
        return "0,00"

    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

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
    total_gastado = db.session.query(
        db.func.sum(Gasto.monto)
    ).scalar()

    if total_gastado is None:
        total_gastado = 0

    cantidad_gastos = Gasto.query.count()

    ultimos_gastos = Gasto.query.order_by(
        Gasto.id.desc()
    ).limit(5).all()


    gastos_categoria = db.session.query(
        Gasto.categoria,
    func.sum(Gasto.monto)
    ).group_by(
        Gasto.categoria
    ).order_by(
        func.sum(Gasto.monto).desc()
    ).all()

    gastos_categoria_pct = []

    for categoria, total in gastos_categoria:

        porcentaje = 0

        if total_gastado > 0:
            porcentaje = round((total / total_gastado) * 100, 1)

        gastos_categoria_pct.append(
            {
                "categoria": categoria,
                "total": total,
                "porcentaje": porcentaje
            }
        )

    gastos_responsable = db.session.query(
        Gasto.responsable,
        func.sum(Gasto.monto)
    ).group_by(
        Gasto.responsable
    ).order_by(
        func.sum(Gasto.monto).desc()
    ).all()

    gastos_medio_pago = db.session.query(
        Gasto.medio_pago,
        func.sum(Gasto.monto)
    ).group_by(
        Gasto.medio_pago
    ).order_by(
        func.sum(Gasto.monto).desc()
    ).all() 

    promedio_gasto = 0

    if cantidad_gastos > 0:
        promedio_gasto = total_gastado / cantidad_gastos

    categoria_mas_frecuente = None

    if gastos_categoria_pct:

        categoria_nombre = gastos_categoria_pct[0]["categoria"]

        cantidad_movimientos = Gasto.query.filter(
            Gasto.categoria == categoria_nombre
        ).count()

        categoria_mas_frecuente = {
            "categoria": categoria_nombre,
            "cantidad": cantidad_movimientos,
            "porcentaje": gastos_categoria_pct[0]["porcentaje"]
        }
    
    return render_template(
        "home.html",
        total_gastado=total_gastado,
        cantidad_gastos=cantidad_gastos,
        ultimos_gastos=ultimos_gastos,
        gastos_categoria=gastos_categoria,
        gastos_categoria_pct=gastos_categoria_pct,
        gastos_responsable=gastos_responsable,
        gastos_medio_pago=gastos_medio_pago,
        categoria_mas_frecuente=categoria_mas_frecuente
    )                                                  
@app.route("/nuevo", methods=["GET", "POST"])
def nuevo_gasto():

    if request.method == "POST":

        gasto = Gasto(
            fecha=request.form["fecha"],
            descripcion=request.form["descripcion"],
            monto=float(request.form["monto"] or 0),
            categoria=request.form["categoria"],
            responsable=request.form["responsable"],
            medio_pago=request.form["medio_pago"]
        )

        db.session.add(gasto)
        db.session.commit()

        return render_template(
            "gasto_guardado.html",
            ultimo_gasto=gasto
        )

    return render_template("nuevo_gasto.html")


@app.route("/gastos")
def listar_gastos():

    gastos = Gasto.query.order_by(Gasto.id.desc()).all()

    return render_template(
        "gastos.html",
        gastos=gastos
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
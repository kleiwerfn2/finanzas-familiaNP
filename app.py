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
    total_gastado = sum(
        gasto.monto
        for gasto in gastos_query.all()
    )

    if total_gastado is None:
        total_gastado = 0

    cantidad_gastos = gastos_query.count()

    ultimos_gastos = gastos_query.order_by(
        Gasto.id.desc()
    ).limit(5).all()


    gastos_categoria = gastos_query.with_entities(
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

    gastos_responsable = gastos_query.with_entities(
        Gasto.responsable,
        func.sum(Gasto.monto)
    ).group_by(
        Gasto.responsable
    ).order_by(
        func.sum(Gasto.monto).desc()
    ).all()

    gastos_medio_pago = gastos_query.with_entities(
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
    meses_disponibles = sorted(
        list(
            set(
                gasto.fecha[:7]
                for gasto in Gasto.query.all()
            )
        ),
        reverse=True
    )

    return render_template(
        "home.html",
        total_gastado=total_gastado,
        cantidad_gastos=cantidad_gastos,
        ultimos_gastos=ultimos_gastos,
        gastos_categoria=gastos_categoria,
        gastos_categoria_pct=gastos_categoria_pct,
        gastos_responsable=gastos_responsable,
        gastos_medio_pago=gastos_medio_pago,
        categoria_mas_frecuente=categoria_mas_frecuente,
        meses_disponibles=meses_disponibles,
        mes_seleccionado=mes_seleccionado,
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

@app.route("/reportes")
def reportes():

    gastos = Gasto.query.all()

    gastos_por_mes = {}

    for gasto in gastos:

        mes = gasto.fecha[:7]

        if mes not in gastos_por_mes:
            gastos_por_mes[mes] = 0

        gastos_por_mes[mes] += gasto.monto

    gastos_por_mes = sorted(
        gastos_por_mes.items(),
        reverse=True
    )

    total_mes_actual = 0
    total_mes_anterior = 0

    if len(gastos_por_mes) > 0:
        total_mes_actual = gastos_por_mes[0][1]

    if len(gastos_por_mes) > 1:
        total_mes_anterior = gastos_por_mes[1][1]

    variacion = 0

    if total_mes_anterior > 0:

        variacion = round(
            (
                (total_mes_actual - total_mes_anterior)
                / total_mes_anterior
            ) * 100,
            1
        )  
    categoria_mas_aumento = None

    if len(gastos_por_mes) >= 2:

        mes_actual = gastos_por_mes[0][0]
        mes_anterior = gastos_por_mes[1][0]

        categorias_actual = {}
        categorias_anterior = {}

        for gasto in gastos:

            mes = gasto.fecha[:7]

            if mes == mes_actual:

                categorias_actual[gasto.categoria] = (
                    categorias_actual.get(gasto.categoria, 0)
                    + gasto.monto
                )

            elif mes == mes_anterior:

                categorias_anterior[gasto.categoria] = (
                    categorias_anterior.get(gasto.categoria, 0)
                    + gasto.monto
                )

        mayor_diferencia = 0

        for categoria, total_actual in categorias_actual.items():

            total_anterior = categorias_anterior.get(
                categoria,
                0
            )

            diferencia = total_actual - total_anterior

            if diferencia > mayor_diferencia:

                porcentaje = 100

                if total_anterior > 0:
                    porcentaje = round(
                        (diferencia / total_anterior) * 100,
                        1
                    )

                mayor_diferencia = diferencia

                categoria_mas_aumento = {
                    "categoria": categoria,
                    "diferencia": diferencia,
                    "porcentaje": porcentaje
                }

    return render_template(
        "reportes.html",
        total_mes_actual=total_mes_actual,
        total_mes_anterior=total_mes_anterior,
        variacion=variacion,
        gastos_por_mes=gastos_por_mes,
        categoria_mas_aumento=categoria_mas_aumento,
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
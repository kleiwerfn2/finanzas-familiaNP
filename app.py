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

class GastoRecurrente(db.Model):

    id = db.Column(db.Integer,primary_key=True)
    descripcion = db.Column(db.String(200),nullable=False)
    categoria = db.Column(db.String(100),nullable=False)
    monto = db.Column(db.Float,nullable=False)
    responsable = db.Column(db.String(100),nullable=False)
    medio_pago = db.Column(db.String(100),nullable=False)
    dia_vencimiento = db.Column(db.Integer,nullable=False)
    activo = db.Column(db.Boolean,default=True)

with app.app_context():
    db.create_all()

@app.route("/")
def home():

    mes_seleccionado = request.args.get(
        "mes",
        "todos"
    )

    if mes_seleccionado == "todos":

        gastos_query = Gasto.query

    else:

        gastos_query = Gasto.query.filter(
            Gasto.fecha.startswith(
                mes_seleccionado
            )
        )

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

        cantidad_movimientos = gastos_query.filter(
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

    orden = request.args.get(
        "orden",
        "id"
    )

    direccion = request.args.get(
        "dir",
        "desc"
    )

    columna = getattr(
        Gasto,
        orden,
        Gasto.id
    )

    if direccion == "asc":
        query = Gasto.query.order_by(
            columna.asc()
        )
    else:
        query = Gasto.query.order_by(
            columna.desc()
        )

    pagina = request.args.get(
        "pagina",
        1,
        type=int
    )

    gastos = query.paginate(
        page=pagina,
        per_page=15,
        error_out=False
    )

    return render_template(
        "gastos.html",
        gastos=gastos,
        orden=orden,
        direccion=direccion
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
    comparativo_categorias = []

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

        todas_categorias = set(
            list(categorias_actual.keys()) +
            list(categorias_anterior.keys())
        )

        for categoria in todas_categorias:

            total_actual = categorias_actual.get(
                categoria,
                0
            )

            total_anterior = categorias_anterior.get(
                categoria,
                0
            )

            variacion_categoria = 0

            if total_anterior > 0:

                variacion_categoria = round(
                    (
                        (total_actual - total_anterior)
                        / total_anterior
                    ) * 100,
                    1
                )

            comparativo_categorias.append(
                {
                    "categoria": categoria,
                    "actual": total_actual,
                    "anterior": total_anterior,
                    "diferencia": total_actual - total_anterior,
                    "variacion": variacion_categoria
                }
            )

        comparativo_categorias.sort(
            key=lambda x: abs(x["variacion"]),
            reverse=True
        )

    return render_template(
        "reportes.html",
        total_mes_actual=total_mes_actual,
        total_mes_anterior=total_mes_anterior,
        variacion=variacion,
        gastos_por_mes=gastos_por_mes,
        categoria_mas_aumento=categoria_mas_aumento,
        comparativo_categorias=comparativo_categorias,
    )

@app.route("/recurrentes")
def listar_recurrentes():

    recurrentes = GastoRecurrente.query.order_by(
        GastoRecurrente.descripcion
    ).all()

    return render_template(
        "recurrentes.html",
        recurrentes=recurrentes
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
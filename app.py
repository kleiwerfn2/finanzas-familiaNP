from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for
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
    gasto_recurrente_id = db.Column(db.Integer, db.ForeignKey('gasto_recurrente.id'), nullable=True)
    pagado = db.Column(db.Boolean, default=False)  
    recurrente = db.relationship('GastoRecurrente', backref='gastos_generados', lazy=True)

class GastoRecurrente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descripcion = db.Column(db.String(200), nullable=False)
    categoria = db.Column(db.String(100), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    responsable = db.Column(db.String(100), nullable=False)
    medio_pago = db.Column(db.String(100), nullable=False)
    dia_vencimiento = db.Column(db.Integer, nullable=False)
    activo = db.Column(db.Boolean, default=True)

with app.app_context():
    db.create_all()

# --- FUNCIÓN AUXILIAR DRY PARA OPCIONES DE FORMULARIO ---
def obtener_opciones():
    cat_base = ["Supermercado", "Restaurante", "Alquiler", "Agua", "Luz", "Gas", "Internet", "Telefono", "Educación", "Deportes", "Transporte", "Salud", "Vacaciones", "Fondo de Retiro", "Gastos Personales"]
    resp_base = ["Joffan", "Dore"]
    medios_base = ["BBVA Master", "BBVA Visa", "Santander Visa", "Santander American", "Transferencia Galicia", "Transferencia Santander", "Transferencia BBVA", "Mercado Pago", "Efectivo"]

    cat_db = [c[0] for c in db.session.query(Gasto.categoria).distinct().all() if c[0]]
    resp_db = [r[0] for r in db.session.query(Gasto.responsable).distinct().all() if r[0]]
    medios_db = [m[0] for m in db.session.query(Gasto.medio_pago).distinct().all() if m[0]]

    return {
        "categorias": sorted(list(set(cat_base + cat_db))),
        "responsables": sorted(list(set(resp_base + resp_db))),
        "medios_pago": sorted(list(set(medios_base + medios_db)))
    }

@app.route("/")
def home():
    mes_seleccionado = request.args.get("mes", "todos")

    gastos_query = Gasto.query if mes_seleccionado == "todos" else Gasto.query.filter(Gasto.fecha.startswith(mes_seleccionado))

    total_gastado = db.session.query(func.coalesce(func.sum(Gasto.monto), 0)).filter(
        Gasto.id.in_(gastos_query.with_entities(Gasto.id))
    ).scalar()

    cantidad_gastos = gastos_query.count()
    ultimos_gastos = gastos_query.order_by(Gasto.id.desc()).limit(5).all()

    gastos_categoria = gastos_query.with_entities(
        Gasto.categoria, func.sum(Gasto.monto)
    ).group_by(Gasto.categoria).order_by(func.sum(Gasto.monto).desc()).all()

    gastos_categoria_pct = [
        {
            "categoria": cat,
            "total": tot,
            "porcentaje": round((tot / total_gastado) * 100, 1) if total_gastado > 0 else 0
        }
        for cat, tot in gastos_categoria
    ]

    cat_labels = [item["categoria"] for item in gastos_categoria_pct]
    cat_totals = [item["total"] for item in gastos_categoria_pct]

    gastos_responsable = gastos_query.with_entities(
        Gasto.responsable, func.sum(Gasto.monto)
    ).group_by(Gasto.responsable).order_by(func.sum(Gasto.monto).desc()).all()

    gastos_medio_pago = gastos_query.with_entities(
        Gasto.medio_pago, func.sum(Gasto.monto)
    ).group_by(Gasto.medio_pago).order_by(func.sum(Gasto.monto).desc()).all() 

    categoria_mas_frecuente = None
    if gastos_categoria_pct:
        cat_nom = gastos_categoria_pct[0]["categoria"]
        cant = gastos_query.filter(Gasto.categoria == cat_nom).count()
        categoria_mas_frecuente = {
            "categoria": cat_nom,
            "cantidad": cant,
            "porcentaje": gastos_categoria_pct[0]["porcentaje"]
        }

    meses_db = db.session.query(func.substr(Gasto.fecha, 1, 7)).distinct().all()
    meses_disponibles = sorted([m[0] for m in meses_db if m[0]], reverse=True)

    # Datos para el gráfico de Barras (últimos 6 meses con nombre de mes)
    nombres_meses = {
        '01':'Enero', '02':'Febrero', '03':'Marzo', '04':'Abril',
        '05':'Mayo', '06':'Junio', '07':'Julio', '08':'Agosto',
        '09':'Septiembre', '10':'Octubre', '11':'Noviembre', '12':'Diciembre'
    }

    gastos_mes_db = db.session.query(
        func.substr(Gasto.fecha, 1, 7).label("mes"),
        func.sum(Gasto.monto).label("total")
    ).group_by("mes").order_by(db.desc("mes")).limit(6).all()

    mes_labels = []
    for m in reversed(gastos_mes_db):
        if m[0]:
            num_mes = m[0][5:7]
            mes_labels.append(nombres_meses.get(num_mes, m[0]))

    mes_totals = [float(m[1]) for m in reversed(gastos_mes_db) if m[0]]

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
        cat_labels=cat_labels,
        cat_totals=cat_totals,
        mes_labels=mes_labels,
        mes_totals=mes_totals
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
        return render_template("gasto_guardado.html", ultimo_gasto=gasto)

    return render_template("nuevo_gasto.html", gasto=None, **obtener_opciones())

@app.route("/gastos")
def listar_gastos():
    orden = request.args.get("orden", "id")
    direccion = request.args.get("dir", "desc")
    columna = getattr(Gasto, orden, Gasto.id)

    query = Gasto.query.order_by(columna.asc() if direccion == "asc" else columna.desc())
    pagina = request.args.get("pagina", 1, type=int)
    gastos = query.paginate(page=pagina, per_page=15, error_out=False)

    return render_template("gastos.html", gastos=gastos, orden=orden, direccion=direccion)

@app.route("/gastos/<int:id>/editar", methods=["GET", "POST"])
def editar_gasto(id):
    gasto = Gasto.query.get_or_404(id)
    if request.method == "POST":
        gasto.fecha = request.form["fecha"]
        gasto.descripcion = request.form["descripcion"]
        gasto.monto = float(request.form["monto"] or 0)
        gasto.categoria = request.form["categoria"]
        gasto.responsable = request.form["responsable"]
        gasto.medio_pago = request.form["medio_pago"]
        db.session.commit()
        return redirect(url_for("listar_gastos"))

    return render_template("nuevo_gasto.html", gasto=gasto, **obtener_opciones())

@app.route("/gastos/<int:id>/eliminar")
def eliminar_gasto(id):
    gasto = Gasto.query.get_or_404(id)
    db.session.delete(gasto)
    db.session.commit()
    return redirect(url_for("listar_gastos"))

@app.route("/reportes")
def reportes():
    # Agrupación por mes directamente en SQLite
    gastos_db = db.session.query(
        func.substr(Gasto.fecha, 1, 7).label("mes"),
        func.sum(Gasto.monto)
    ).group_by("mes").order_by(db.desc("mes")).all()

    gastos_por_mes = [(m, float(t)) for m, t in gastos_db if m]

    total_mes_actual = gastos_por_mes[0][1] if len(gastos_por_mes) > 0 else 0
    total_mes_anterior = gastos_por_mes[1][1] if len(gastos_por_mes) > 1 else 0

    variacion = round(((total_mes_actual - total_mes_anterior) / total_mes_anterior) * 100, 1) if total_mes_anterior > 0 else 0

    categoria_mas_aumento = None
    comparativo_categorias = []

    if len(gastos_por_mes) >= 2:
        mes_act, mes_ant = gastos_por_mes[0][0], gastos_por_mes[1][0]

        cat_actual = dict(db.session.query(Gasto.categoria, func.sum(Gasto.monto)).filter(Gasto.fecha.startswith(mes_act)).group_by(Gasto.categoria).all())
        cat_anterior = dict(db.session.query(Gasto.categoria, func.sum(Gasto.monto)).filter(Gasto.fecha.startswith(mes_ant)).group_by(Gasto.categoria).all())

        mayor_dif = 0
        for cat, tot_act in cat_actual.items():
            tot_ant = cat_anterior.get(cat, 0)
            dif = tot_act - tot_ant
            if dif > mayor_dif:
                pct = round((dif / tot_ant) * 100, 1) if tot_ant > 0 else 100
                mayor_dif = dif
                categoria_mas_aumento = {"categoria": cat, "diferencia": dif, "porcentaje": pct}

        todas_cats = set(cat_actual.keys()) | set(cat_anterior.keys())
        for cat in todas_cats:
            t_act, t_ant = cat_actual.get(cat, 0), cat_anterior.get(cat, 0)
            var_cat = round(((t_act - t_ant) / t_ant) * 100, 1) if t_ant > 0 else 0
            comparativo_categorias.append({
                "categoria": cat, "actual": t_act, "anterior": t_ant, "diferencia": t_act - t_ant, "variacion": var_cat
            })

        comparativo_categorias.sort(key=lambda x: abs(x["variacion"]), reverse=True)

    return render_template(
        "reportes.html",
        total_mes_actual=total_mes_actual,
        total_mes_anterior=total_mes_anterior,
        variacion=variacion,
        gastos_por_mes=gastos_por_mes,
        categoria_mas_aumento=categoria_mas_aumento,
        comparativo_categorias=comparativo_categorias,
    )

# --- RUTAS DE GASTOS RECURRENTES ---

@app.route("/recurrentes")
def listar_recurrentes():
    mes_actual = datetime.now().strftime("%Y-%m")
    recurrentes = GastoRecurrente.query.order_by(GastoRecurrente.descripcion).all()
    gastos_mes = Gasto.query.filter(Gasto.fecha.startswith(mes_actual)).all()

    pagados_mes_ids = {g.gasto_recurrente_id: g.pagado for g in gastos_mes if g.gasto_recurrente_id}
    generados_mes_ids = {g.gasto_recurrente_id: g.id for g in gastos_mes if g.gasto_recurrente_id}

    return render_template("recurrentes.html", recurrentes=recurrentes, pagados_mes_ids=pagados_mes_ids, generados_mes_ids=generados_mes_ids)

@app.route("/recurrentes/nuevo", methods=["GET", "POST"])
def nuevo_recurrente():
    if request.method == "POST":
        nuevo = GastoRecurrente(
            descripcion=request.form["descripcion"],
            categoria=request.form["categoria"],
            monto=float(request.form["monto"] or 0),
            responsable=request.form["responsable"],
            medio_pago=request.form["medio_pago"],
            dia_vencimiento=int(request.form["dia_vencimiento"])
        )
        db.session.add(nuevo)
        db.session.commit()
        return redirect(url_for("listar_recurrentes"))

    return render_template("recurrente_form.html", recurrente=None, **obtener_opciones())

@app.route("/recurrentes/<int:id>/editar", methods=["GET", "POST"])
def editar_recurrente(id):
    recurrente = GastoRecurrente.query.get_or_404(id)
    if request.method == "POST":
        recurrente.descripcion = request.form["descripcion"]
        recurrente.categoria = request.form["categoria"]
        recurrente.monto = float(request.form["monto"] or 0)
        recurrente.responsable = request.form["responsable"]
        recurrente.medio_pago = request.form["medio_pago"]
        recurrente.dia_vencimiento = int(request.form["dia_vencimiento"])
        db.session.commit()
        return redirect(url_for("listar_recurrentes"))

    return render_template("recurrente_form.html", recurrente=recurrente, **obtener_opciones())

@app.route("/recurrentes/<int:id>/toggle")
def toggle_recurrente(id):
    recurrente = GastoRecurrente.query.get_or_404(id)
    recurrente.activo = not recurrente.activo
    db.session.commit()
    return redirect(url_for("listar_recurrentes"))

@app.route("/recurrentes/generar", methods=["POST"])
def generar_gastos_mes():
    mes_actual = datetime.now().strftime("%Y-%m")
    recurrentes_activos = GastoRecurrente.query.filter_by(activo=True).all()

    for rec in recurrentes_activos:
        dia_str = str(rec.dia_vencimiento).zfill(2)
        fecha_gasto = f"{mes_actual}-{dia_str}"

        existente = Gasto.query.filter(
            Gasto.gasto_recurrente_id == rec.id,
            Gasto.fecha.startswith(mes_actual)
        ).first()

        if not existente:
            nuevo_gasto = Gasto(
                fecha=fecha_gasto,
                descripcion=rec.descripcion,
                monto=rec.monto,
                categoria=rec.categoria,
                responsable=rec.responsable,
                medio_pago=rec.medio_pago,
                gasto_recurrente_id=rec.id
            )
            db.session.add(nuevo_gasto)

    db.session.commit()
    return redirect(url_for("listar_recurrentes"))

@app.route("/gastos/<int:id>/toggle-pago")
def toggle_pago_gasto(id):
    gasto = Gasto.query.get_or_404(id)
    gasto.pagado = not gasto.pagado
    db.session.commit()
    return redirect(request.referrer or url_for("listar_gastos"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
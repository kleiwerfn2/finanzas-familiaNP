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

# --- MODELOS DE NAVEGACIÓN Y CONFIGURACIÓN ---
class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)

class Responsable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)

class MedioPago(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)

# --- MODELOS DE GASTOS ---
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

# --- FUNCIONES AUXILIARES ---
def inicializar_opciones_base():
    if Categoria.query.count() == 0:
        for c in ["Supermercado", "Restaurante", "Servicios", "Transporte", "Gastos Personales"]:
            db.session.add(Categoria(nombre=c))
            
    if Responsable.query.count() == 0:
        for r in ["Joffan", "Dore"]:
            db.session.add(Responsable(nombre=r))
            
    if MedioPago.query.count() == 0:
        for m in ["Efectivo", "Débito", "Crédito", "Mercado Pago"]:
            db.session.add(MedioPago(nombre=m))
            
    db.session.commit()

def obtener_opciones():
    inicializar_opciones_base()
    return {
        'categorias': [c.nombre for c in Categoria.query.order_by(Categoria.nombre.asc()).all()],
        'responsables': [r.nombre for r in Responsable.query.order_by(Responsable.nombre.asc()).all()],
        'medios_pago': [m.nombre for m in MedioPago.query.order_by(MedioPago.nombre.asc()).all()]
    }

# --- RUTAS PRINCIPALES ---
@app.route("/")
def home():
    mes_seleccionado = request.args.get("mes", "todos")

    if mes_seleccionado == "todos":
        gastos_query = Gasto.query
    else:
        gastos_query = Gasto.query.filter(Gasto.fecha.startswith(mes_seleccionado))

    total_gastado = sum(gasto.monto for gasto in gastos_query.all()) or 0
    cantidad_gastos = gastos_query.count()

    ultimos_gastos = gastos_query.order_by(Gasto.id.desc()).limit(5).all()

    gastos_categoria = gastos_query.with_entities(
        Gasto.categoria, func.sum(Gasto.monto)
    ).group_by(Gasto.categoria).order_by(func.sum(Gasto.monto).desc()).all()

    gastos_categoria_pct = []
    for categoria, total in gastos_categoria:
        porcentaje = round((total / total_gastado) * 100, 1) if total_gastado > 0 else 0
        gastos_categoria_pct.append({
            "categoria": categoria,
            "total": total,
            "porcentaje": porcentaje
        })

    # Listas enviadas a home.html para los gráficos
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
        categoria_nombre = gastos_categoria_pct[0]["categoria"]
        cantidad_movimientos = gastos_query.filter(Gasto.categoria == categoria_nombre).count()
        categoria_mas_frecuente = {
            "categoria": categoria_nombre,
            "cantidad": cantidad_movimientos,
            "porcentaje": gastos_categoria_pct[0]["porcentaje"]
        }

    meses_disponibles = sorted(
        list(set(gasto.fecha[:7] for gasto in Gasto.query.all())),
        reverse=True
    )

    return render_template(
        "home.html",
        total_gastado=total_gastado,
        cantidad_gastos=cantidad_gastos,
        ultimos_gastos=ultimos_gastos,
        gastos_categoria=gastos_categoria,
        gastos_categoria_pct=gastos_categoria_pct,
        cat_labels=cat_labels,
        cat_totals=cat_totals,
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

        return render_template("gasto_guardado.html", ultimo_gasto=gasto)

    return render_template("nuevo_gasto.html", **obtener_opciones())

@app.route("/gastos")
def listar_gastos():
    orden = request.args.get("orden", "id")
    direccion = request.args.get("dir", "desc")
    columna = getattr(Gasto, orden, Gasto.id)

    query = Gasto.query.order_by(columna.asc() if direccion == "asc" else columna.desc())
    pagina = request.args.get("pagina", 1, type=int)
    gastos = query.paginate(page=pagina, per_page=15, error_out=False)

    return render_template("gastos.html", gastos=gastos, orden=orden, direccion=direccion)

@app.route("/reportes")
def reportes():
    gastos = Gasto.query.all()
    gastos_por_mes = {}

    for gasto in gastos:
        mes = gasto.fecha[:7]
        gastos_por_mes[mes] = gastos_por_mes.get(mes, 0) + gasto.monto

    gastos_por_mes = sorted(gastos_por_mes.items(), reverse=True)

    total_mes_actual = gastos_por_mes[0][1] if len(gastos_por_mes) > 0 else 0
    total_mes_anterior = gastos_por_mes[1][1] if len(gastos_por_mes) > 1 else 0

    variacion = 0
    if total_mes_anterior > 0:
        variacion = round(((total_mes_actual - total_mes_anterior) / total_mes_anterior) * 100, 1)  

    categoria_mas_aumento = None
    comparativo_categorias = []

    if len(gastos_por_mes) >= 2:
        mes_actual, mes_anterior = gastos_por_mes[0][0], gastos_por_mes[1][0]
        categorias_actual, categorias_anterior = {}, {}

        for gasto in gastos:
            mes = gasto.fecha[:7]
            if mes == mes_actual:
                categorias_actual[gasto.categoria] = categorias_actual.get(gasto.categoria, 0) + gasto.monto
            elif mes == mes_anterior:
                categorias_anterior[gasto.categoria] = categorias_anterior.get(gasto.categoria, 0) + gasto.monto

        mayor_diferencia = 0
        for categoria, total_actual in categorias_actual.items():
            total_anterior = categorias_anterior.get(categoria, 0)
            diferencia = total_actual - total_anterior

            if diferencia > mayor_diferencia:
                porcentaje = round((diferencia / total_anterior) * 100, 1) if total_anterior > 0 else 100
                mayor_diferencia = diferencia
                categoria_mas_aumento = {
                    "categoria": categoria,
                    "diferencia": diferencia,
                    "porcentaje": porcentaje
                }

        todas_categorias = set(list(categorias_actual.keys()) + list(categorias_anterior.keys()))
        for categoria in todas_categorias:
            total_actual = categorias_actual.get(categoria, 0)
            total_anterior = categorias_anterior.get(categoria, 0)
            variacion_categoria = round(((total_actual - total_anterior) / total_anterior) * 100, 1) if total_anterior > 0 else 0

            comparativo_categorias.append({
                "categoria": categoria,
                "actual": total_actual,
                "anterior": total_anterior,
                "diferencia": total_actual - total_anterior,
                "variacion": variacion_categoria
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

# --- RUTAS DE GESTIÓN DE OPCIONES ---
@app.route('/opciones', methods=['GET', 'POST'])
def gestionar_opciones():
    if request.method == 'POST':
        tipo = request.form.get('tipo')
        nombre = request.form.get('nombre', '').strip()

        if nombre:
            if tipo == 'categoria' and not Categoria.query.filter(Categoria.nombre.ilike(nombre)).first():
                db.session.add(Categoria(nombre=nombre))
            elif tipo == 'responsable' and not Responsable.query.filter(Responsable.nombre.ilike(nombre)).first():
                db.session.add(Responsable(nombre=nombre))
            elif tipo == 'medio_pago' and not MedioPago.query.filter(MedioPago.nombre.ilike(nombre)).first():
                db.session.add(MedioPago(nombre=nombre))
            
            db.session.commit()
        return redirect(url_for('gestionar_opciones'))

    return render_template('opciones.html', **obtener_opciones())

@app.route('/categorias')
def categorias_old():
    return redirect(url_for('gestionar_opciones'))

# --- RUTAS DE GASTOS RECURRENTES ---
@app.route("/recurrentes")
def listar_recurrentes():
    mes_actual = datetime.now().strftime("%Y-%m")
    recurrentes = GastoRecurrente.query.order_by(GastoRecurrente.descripcion).all()
    gastos_mes = Gasto.query.filter(Gasto.fecha.startswith(mes_actual)).all()
    
    pagados_mes_ids = {g.gasto_recurrente_id: g.pagado for g in gastos_mes if g.gasto_recurrente_id}
    generados_mes_ids = {g.gasto_recurrente_id: g.id for g in gastos_mes if g.gasto_recurrente_id}

    return render_template(
        "recurrentes.html", 
        recurrentes=recurrentes,
        pagados_mes_ids=pagados_mes_ids,
        generados_mes_ids=generados_mes_ids
    )

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
    recurrentes_activos = GastoRecurrente.query.filter(GastoRecurrente.activo == True).all()

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
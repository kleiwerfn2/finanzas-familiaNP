import os, secrets  
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_login import UserMixin, LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# Configuración de Base de Datos (Render / Supabase / Local)
db_url = os.environ.get("DATABASE_URL", "sqlite:////app/data/finanzas.db")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# --- MODELOS MULTIUSUARIO / MULTIFAMILIA ---

class Familia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    codigo_invitacion = db.Column(db.String(20), unique=True, nullable=False)

    usuarios = db.relationship('Usuario', backref='familia', lazy=True)
    gastos = db.relationship('Gasto', backref='familia', lazy=True)
    recurrentes = db.relationship('GastoRecurrente', backref='familia', lazy=True)

class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    familia_id = db.Column(db.Integer, db.ForeignKey('familia.id'), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Gasto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.String(20), index=True)
    descripcion = db.Column(db.String(200))
    monto = db.Column(db.Float)
    categoria = db.Column(db.String(50), index=True)
    responsable = db.Column(db.String(50))
    medio_pago = db.Column(db.String(50))
    gasto_recurrente_id = db.Column(db.Integer, db.ForeignKey('gasto_recurrente.id'), nullable=True, index=True)
    pagado = db.Column(db.Boolean, default=False)  
    familia_id = db.Column(db.Integer, db.ForeignKey('familia.id'), nullable=True, index=True) # nullable=True temporal para migración
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
    familia_id = db.Column(db.Integer, db.ForeignKey('familia.id'), nullable=True, index=True) # nullable=True temporal para migración

# --- MIGRACIÓN DE DATOS INICIALES (PASO 2) ---
with app.app_context():
    db.create_all()

    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    
    # 1. Asegurar columnas familia_id
    columnas_gasto = [c['name'] for c in inspector.get_columns('gasto')]
    if 'familia_id' not in columnas_gasto:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE gasto ADD COLUMN familia_id INTEGER REFERENCES familia(id)"))
            conn.commit()

    columnas_recurrente = [c['name'] for c in inspector.get_columns('gasto_recurrente')]
    if 'familia_id' not in columnas_recurrente:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE gasto_recurrente ADD COLUMN familia_id INTEGER REFERENCES familia(id)"))
            conn.commit()

    # 2. Crear Familia inicial si no existe ninguna
    familia_base = Familia.query.first()
    if not familia_base:
        codigo_unico = secrets.token_hex(4).upper()
        familia_base = Familia(nombre="Familia Principal", codigo_invitacion=codigo_unico)
        db.session.add(familia_base)
        db.session.commit()
        print(f"--> Familia creada con éxito! Código de invitación: {codigo_unico}")

    # 3. Crear Usuario inicial asociado a la familia
    usuario_base = Usuario.query.first()
    if not usuario_base:
        usuario_base = Usuario(
            nombre="Admin",
            email="admin@familia.com",
            familia_id=familia_base.id
        )
        usuario_base.set_password("admin123")  # Contraseña inicial temporal
        db.session.add(usuario_base)
        db.session.commit()
        print("--> Usuario creado con éxito! Email: admin@familia.com | Pass: admin123")

    # 4. Asignar todos los gastos huérfanos a la Familia Principal
    Gasto.query.filter(Gasto.familia_id.is_(None)).update({Gasto.familia_id: familia_base.id}, synchronize_session=False)
    GastoRecurrente.query.filter(GastoRecurrente.familia_id.is_(None)).update({GastoRecurrente.familia_id: familia_base.id}, synchronize_session=False)
    db.session.commit()

# --- FILTROS Y CONTEXT PROCESSORS ---
@app.template_filter('moneda')
def moneda(valor):
    if valor is None:
        return "$0,00"
    formatted = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"$\u00A0{formatted}"

@app.context_processor
def inject_alertas():
    try:
        hoy = date.today()
        mes_actual = hoy.strftime("%Y-%m")
        dia_actual = hoy.day

        recurrentes_activos = GastoRecurrente.query.filter_by(activo=True).all()
        
        # Optimización: Solo seleccionamos los campos necesarios de DB
        gastos_mes = db.session.query(
            Gasto.gasto_recurrente_id, Gasto.pagado, Gasto.id
        ).filter(
            Gasto.fecha.startswith(mes_actual),
            Gasto.gasto_recurrente_id.isnot(None)
        ).all()

        pagados_dict = {g[0]: g[1] for g in gastos_mes}
        generados_dict = {g[0]: g[2] for g in gastos_mes}

        alertas = []
        for rec in recurrentes_activos:
            esta_pagado = pagados_dict.get(rec.id, False)
            if not esta_pagado:
                dias_para_vencer = rec.dia_vencimiento - dia_actual
                if dias_para_vencer <= 5:
                    alertas.append({
                        "id": rec.id,
                        "descripcion": rec.descripcion,
                        "monto": rec.monto,
                        "dia_vencimiento": rec.dia_vencimiento,
                        "vencido": dias_para_vencer < 0,
                        "dias_restantes": dias_para_vencer,
                        "gasto_id": generados_dict.get(rec.id)
                    })

        alertas.sort(key=lambda x: x["dia_vencimiento"])
        return dict(alertas_vencimiento=alertas, total_alertas=len(alertas))
    except Exception:
        return dict(alertas_vencimiento=[], total_alertas=0)


# --- HELPER DE OPCIONES DE FORMULARIO ---
def obtener_opciones():
    cat_base = ["Supermercado", "Restaurante", "Alquiler", "Expensas", "Luz", "Gas", "Internet", "Telefono", "Educación", "Deportes", "Transporte", "Salud", "Vacaciones", "Fondo de Retiro", "Gastos Personales", "Cora", "Auto", "Varios", "combustible"]
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

# --- RUTAS DE AUTENTICACIÓN (PASO 3) ---

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
        
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        usuario = Usuario.query.filter_by(email=email).first()

        if usuario and usuario.check_password(password):
            login_user(usuario)
            flash("Sesión iniciada correctamente.", "success")
            return redirect(url_for("home"))

        flash("Correo electrónico o contraseña incorrectos.", "danger")

    return render_template("login.html")

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        nombre = request.form.get("nombre")
        email = request.form.get("email")
        password = request.form.get("password")
        tipo_registro = request.form.get("tipo_registro")

        if Usuario.query.filter_by(email=email).first():
            flash("El correo electrónico ya está registrado.", "warning")
            return render_template("registro.html")

        if tipo_registro == "crear":
            nombre_familia = request.form.get("nombre_familia", "Mi Familia")
            codigo = secrets.token_hex(4).upper()
            nueva_familia = Familia(nombre=nombre_familia, codigo_invitacion=codigo)
            db.session.add(nueva_familia)
            db.session.commit()
            familia_target = nueva_familia
        else:
            codigo = request.form.get("codigo_invitacion", "").strip().upper()
            familia_target = Familia.query.filter_by(codigo_invitacion=codigo).first()
            if not familia_target:
                flash("El código de invitación ingresado es inválido.", "danger")
                return render_template("registro.html")

        nuevo_usuario = Usuario(
            nombre=nombre,
            email=email,
            familia_id=familia_target.id
        )
        nuevo_usuario.set_password(password)
        db.session.add(nuevo_usuario)
        db.session.commit()

        login_user(nuevo_usuario)
        flash("¡Cuenta y familia registradas con éxito!", "success")
        return redirect(url_for("home"))

    return render_template("registro.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Has cerrado sesión.", "info")
    return redirect(url_for("login"))


# --- RUTAS PRINCIPALES ---
@app.route("/")
def home():
    mes_seleccionado = request.args.get("mes", "todos")

    gastos_query = Gasto.query if mes_seleccionado == "todos" else Gasto.query.filter(Gasto.fecha.startswith(mes_seleccionado))

    # Optimizado: Suma directa sin subconsultas innecesarias
    total_gastado = gastos_query.with_entities(func.coalesce(func.sum(Gasto.monto), 0.0)).scalar() or 0.0

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

    # --- CATEGORÍA MÁS FRECUENTE (GASTO HORMIGA) ---
    cat_frecuente_db = gastos_query.with_entities(
        Gasto.categoria,
        func.count(Gasto.id).label("frecuencia"),
        func.sum(Gasto.monto).label("monto_total")
    ).group_by(Gasto.categoria).order_by(func.count(Gasto.id).desc()).first()

    categoria_mas_frecuente = None
    if cat_frecuente_db and total_gastado > 0:
        cat_nom, cant, monto_cat = cat_frecuente_db
        monto_cat = monto_cat or 0.0
        categoria_mas_frecuente = {
            "categoria": cat_nom,
            "cantidad": cant,
            "monto": monto_cat,
            "porcentaje": round((monto_cat / total_gastado) * 100, 1)
        }

    meses_db = db.session.query(func.substr(Gasto.fecha, 1, 7)).distinct().all()
    meses_disponibles = sorted([m[0] for m in meses_db if m[0]], reverse=True)

    nombres_meses = {
        '01':'Enero', '02':'Febrero', '03':'Marzo', '04':'Abril',
        '05':'Mayo', '06':'Junio', '07':'Julio', '08':'Agosto',
        '09':'Septiembre', '10':'Octubre', '11':'Noviembre', '12':'Diciembre'
    }

    gastos_mes_db = db.session.query(
        func.substr(Gasto.fecha, 1, 7).label("mes"),
        func.sum(Gasto.monto).label("total")
    ).group_by("mes").order_by(db.desc("mes")).limit(6).all()

    mes_labels = [nombres_meses.get(m[0][5:7], m[0]) for m in reversed(gastos_mes_db) if m[0]]
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

@app.route('/gastos')
def listar_gastos():
    pagina = request.args.get('pagina', 1, type=int)
    orden = request.args.get('orden', 'fecha')
    direccion = request.args.get('dir', 'desc')

    q = request.args.get('q', '').strip()
    categoria = request.args.get('categoria', '')
    responsable = request.args.get('responsable', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')

    query = Gasto.query

    if q:
        query = query.filter(Gasto.descripcion.ilike(f'%{q}%'))
    if categoria:
        query = query.filter(Gasto.categoria == categoria)
    if responsable:
        query = query.filter(Gasto.responsable == responsable)
    if fecha_desde:
        query = query.filter(Gasto.fecha >= fecha_desde)
    if fecha_hasta:
        query = query.filter(Gasto.fecha <= fecha_hasta)

    columna_orden = getattr(Gasto, orden, Gasto.fecha)
    query = query.order_by(columna_orden.desc() if direccion == 'desc' else columna_orden.asc())

    gastos = query.paginate(page=pagina, per_page=10)
    opciones = obtener_opciones()

    return render_template(
        'gastos.html',
        gastos=gastos,
        orden=orden,
        direccion=direccion,
        categorias=opciones["categorias"],
        responsables=opciones["responsables"],
        q=q,
        categoria_sel=categoria,
        responsable_sel=responsable,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta
    )

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
    comparativo_recurrentes = []

    if len(gastos_por_mes) >= 2:
        mes_act, mes_ant = gastos_por_mes[0][0], gastos_por_mes[1][0]

        # Categorías
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

        # Optimización: Carga masiva en 2 consultas SQL agrupadas
        rec_act = dict(db.session.query(Gasto.gasto_recurrente_id, func.sum(Gasto.monto)).filter(
            Gasto.fecha.startswith(mes_act), Gasto.gasto_recurrente_id.isnot(None)
        ).group_by(Gasto.gasto_recurrente_id).all())

        rec_ant = dict(db.session.query(Gasto.gasto_recurrente_id, func.sum(Gasto.monto)).filter(
            Gasto.fecha.startswith(mes_ant), Gasto.gasto_recurrente_id.isnot(None)
        ).group_by(Gasto.gasto_recurrente_id).all())

        for rec in GastoRecurrente.query.all():
            tot_act = rec_act.get(rec.id, 0.0)
            tot_ant = rec_ant.get(rec.id, 0.0)
            dif_rec = tot_act - tot_ant
            var_rec = round((dif_rec / tot_ant) * 100, 1) if tot_ant > 0 else (100.0 if tot_act > 0 else 0.0)

            comparativo_recurrentes.append({
                "descripcion": rec.descripcion,
                "categoria": rec.categoria,
                "actual": float(tot_act),
                "anterior": float(tot_ant),
                "diferencia": float(dif_rec),
                "variacion": var_rec
            })

        comparativo_recurrentes.sort(key=lambda x: abs(x["diferencia"]), reverse=True)

    return render_template(
        "reportes.html",
        total_mes_actual=total_mes_actual,
        total_mes_anterior=total_mes_anterior,
        variacion=variacion,
        gastos_por_mes=gastos_por_mes,
        categoria_mas_aumento=categoria_mas_aumento,
        comparativo_categorias=comparativo_categorias,
        comparativo_recurrentes=comparativo_recurrentes
    )


# --- RUTAS DE RECURRENTES Y RÁPIDAS ---
@app.route("/recurrentes")
def listar_recurrentes():
    mes_actual = datetime.now().strftime("%Y-%m")
    recurrentes = GastoRecurrente.query.order_by(GastoRecurrente.descripcion).all()
    
    gastos_mes = db.session.query(Gasto.gasto_recurrente_id, Gasto.pagado, Gasto.id).filter(
        Gasto.fecha.startswith(mes_actual), Gasto.gasto_recurrente_id.isnot(None)
    ).all()

    pagados_mes_ids = {g[0]: g[1] for g in gastos_mes}
    generados_mes_ids = {g[0]: g[2] for g in gastos_mes}

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

@app.route('/rapido', methods=['GET', 'POST'])
def carga_rapida():
    if request.method == 'POST':
        nuevo_gasto = Gasto(
            fecha=request.form.get('fecha') or date.today().strftime('%Y-%m-%d'),
            descripcion=request.form.get('descripcion'),
            monto=float(request.form.get('monto', 0)),
            categoria=request.form.get('categoria'),
            responsable=request.form.get('responsable'),
            medio_pago=request.form.get('medio_pago')
        )
        db.session.add(nuevo_gasto)
        db.session.commit()
        return redirect(url_for('listar_gastos'))

    # Reutilizamos obtener_opciones()
    opciones = obtener_opciones()
    return render_template(
        'carga_rapida.html',
        fecha_hoy=date.today().strftime('%Y-%m-%d'),
        categorias=opciones["categorias"],
        responsables=opciones["responsables"],
        medios_pago=opciones["medios_pago"]
    )

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
    
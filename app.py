import os, secrets, string
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_login import UserMixin, LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "clave_secreta_super_segura_para_sesiones_y_cookies")

# --- CONFIGURACIÓN DE BASE DE DATOS ---
db_url = os.environ.get("DATABASE_URL", "sqlite:////app/data/finanzas.db")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# --- CONFIGURACIÓN DE FLASK-MAIL ---
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])

mail = Mail(app)
serializer = URLSafeTimedSerializer(app.secret_key)

login_manager = LoginManager(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

@app.context_processor
def inject_user():
    return dict(current_user=current_user)

# --- MODELOS MULTIUSUARIO / MULTIFAMILIA ---

class Familia(db.Model):
    __tablename__ = 'familia'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    codigo_invitacion = db.Column(db.String(20), unique=True, nullable=False)

    usuarios = db.relationship('Usuario', backref='familia', lazy=True)
    miembros = db.relationship('MiembroFamilia', backref='familia', lazy=True, cascade="all, delete-orphan")
    categorias = db.relationship('Categoria', backref='familia', lazy=True, cascade="all, delete-orphan")
    medios_pago = db.relationship('MedioPago', backref='familia', lazy=True, cascade="all, delete-orphan")
    gastos = db.relationship('Gasto', backref='familia', lazy=True)
    recurrentes = db.relationship('GastoRecurrente', backref='familia', lazy=True)

class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuario'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    confirmado = db.Column(db.Boolean, default=False)
    familia_id = db.Column(db.Integer, db.ForeignKey('familia.id'), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class MiembroFamilia(db.Model):
    __tablename__ = 'miembro_familia'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    familia_id = db.Column(db.Integer, db.ForeignKey('familia.id'), nullable=False)

class Categoria(db.Model):
    __tablename__ = 'categoria'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    familia_id = db.Column(db.Integer, db.ForeignKey('familia.id'), nullable=False)

class MedioPago(db.Model):
    __tablename__ = 'medio_pago'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    familia_id = db.Column(db.Integer, db.ForeignKey('familia.id'), nullable=False)

class Gasto(db.Model):
    __tablename__ = 'gasto'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.String(20), index=True)
    descripcion = db.Column(db.String(200))
    monto = db.Column(db.Float)
    categoria = db.Column(db.String(50), index=True)
    responsable = db.Column(db.String(50))
    medio_pago = db.Column(db.String(50))
    gasto_recurrente_id = db.Column(db.Integer, db.ForeignKey('gasto_recurrente.id'), nullable=True, index=True)
    pagado = db.Column(db.Boolean, default=False)  
    familia_id = db.Column(db.Integer, db.ForeignKey('familia.id'), nullable=True, index=True)
    recurrente = db.relationship('GastoRecurrente', backref='gastos_generados', lazy=True)

class GastoRecurrente(db.Model):
    __tablename__ = 'gasto_recurrente'
    id = db.Column(db.Integer, primary_key=True)
    descripcion = db.Column(db.String(200), nullable=False)
    categoria = db.Column(db.String(100), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    responsable = db.Column(db.String(100), nullable=False)
    medio_pago = db.Column(db.String(100), nullable=False)
    dia_vencimiento = db.Column(db.Integer, nullable=False)
    activo = db.Column(db.Boolean, default=True)
    familia_id = db.Column(db.Integer, db.ForeignKey('familia.id'), nullable=True, index=True)

# --- MIGRACIÓN Y DATOS INICIALES ---
with app.app_context():
    db.create_all()

    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    
    # 1. Asegurar columnas de migración
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

    columnas_usuario = [c['name'] for c in inspector.get_columns('usuario')]
    if 'confirmado' not in columnas_usuario:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE usuario ADD COLUMN confirmado BOOLEAN DEFAULT FALSE"))
            conn.commit()

    # 2. Crear Familia inicial si no existe
    familia_base = Familia.query.first()
    if not familia_base:
        codigo_unico = f"FAM-{secrets.token_hex(4).upper()}"
        familia_base = Familia(nombre="Familia Principal", codigo_invitacion=codigo_unico)
        db.session.add(familia_base)
        db.session.commit()

    # 3. Crear Usuario inicial asociado a la familia
    usuario_base = Usuario.query.first()
    if not usuario_base:
        usuario_base = Usuario(
            nombre="Admin",
            email="admin@familia.com",
            confirmado=True,
            familia_id=familia_base.id
        )
        usuario_base.set_password("admin123")
        db.session.add(usuario_base)
        db.session.commit()

    # 4. Asegurar miembros iniciales
    if not MiembroFamilia.query.filter_by(familia_id=familia_base.id).first():
        db.session.add(MiembroFamilia(nombre="Joffan", familia_id=familia_base.id))
        db.session.add(MiembroFamilia(nombre="Dore", familia_id=familia_base.id))
        db.session.commit()

    # 5. Asignar gastos huérfanos a la familia base
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
    if not current_user.is_authenticated:
        return dict(alertas_vencimiento=[], total_alertas=0)
    try:
        hoy = date.today()
        mes_actual = hoy.strftime("%Y-%m")
        dia_actual = hoy.day

        recurrentes_activos = GastoRecurrente.query.filter_by(
            activo=True,
            familia_id=current_user.familia_id
        ).all()
        
        gastos_mes = db.session.query(
            Gasto.gasto_recurrente_id, Gasto.pagado, Gasto.id
        ).filter(
            Gasto.familia_id == current_user.familia_id,
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
    if not current_user.is_authenticated:
        return {"categorias": [], "responsables": [], "medios_pago": []}

    fid = current_user.familia_id

    miembros = [m.nombre for m in MiembroFamilia.query.filter_by(familia_id=fid).order_by(MiembroFamilia.nombre).all()]
    categorias = [c.nombre for c in Categoria.query.filter_by(familia_id=fid).order_by(Categoria.nombre).all()]
    medios = [m.nombre for m in MedioPago.query.filter_by(familia_id=fid).order_by(MedioPago.nombre).all()]

    return {
        "categorias": categorias,
        "responsables": miembros if miembros else ["Sin miembros"],
        "medios_pago": medios
    }

def generar_codigo_invitacion(longitud=8):
    caracteres = string.ascii_uppercase + string.digits
    return f"FAM-{''.join(secrets.choice(caracteres) for _ in range(longitud))}"

# --- RUTAS DE AUTENTICACIÓN ---

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        usuario = Usuario.query.filter_by(email=email).first()

        if usuario and usuario.check_password(password):
            if not usuario.confirmado:
                flash('Debes confirmar tu correo electrónico antes de ingresar.', 'warning')
                return redirect(url_for('login'))
                
            login_user(usuario)
            flash("Sesión iniciada correctamente.", "success")
            return redirect(url_for("home"))

        flash("Correo electrónico o contraseña incorrectos.", "danger")

    return render_template("login.html")

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        tipo_registro = request.form.get('tipo_registro', 'crear')  # 'crear' o 'unirse'
        nombre = request.form.get('nombre', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password')

        # Verificar si el correo ya existe
        if Usuario.query.filter_by(email=email).first():
            flash('El correo electrónico ya está registrado.', 'danger')
            return redirect(url_for('registro'))

        # LÓGICA DE UNIRSE A UNA FAMILIA EXISTENTE
        if tipo_registro == 'unirse':
            codigo = request.form.get('codigo_invitacion', '').strip().upper()
            familia = Familia.query.filter_by(codigo_invitacion=codigo).first()
            
            if not familia:
                flash('El código de invitación no es válido o no existe.', 'danger')
                return redirect(url_for('registro'))

        # LÓGICA DE CREAR NUEVA FAMILIA
        else:
            familia_nombre = request.form.get('familia_nombre') or f'Familia de {nombre}'
            codigo_nuevo = generar_codigo_invitacion()
            while Familia.query.filter_by(codigo_invitacion=codigo_nuevo).first():
                codigo_nuevo = generar_codigo_invitacion()

            familia = Familia(nombre=familia_nombre, codigo_invitacion=codigo_nuevo)
            db.session.add(familia)
            db.session.flush()

            # Poblar Categorías Iniciales
            cat_base = [
                "Supermercado", "Restaurante", "Alquiler", "Expensas", "Luz", "Gas", 
                "Internet", "Telefono", "Educación", "Deportes", "Transporte", "Salud", 
                "Vacaciones", "Fondo de Retiro", "Gastos Personales", "Auto", "Varios", "Combustible"
            ]
            for cat_nombre in cat_base:
                db.session.add(Categoria(nombre=cat_nombre, familia_id=familia.id))

            # Poblar Medios de Pago Iniciales
            medios_base = [
                "BBVA Master", "BBVA Visa", "Santander Visa", "Santander American", 
                "Transferencia Galicia", "Transferencia Santander", "Transferencia BBVA", 
                "Mercado Pago", "Efectivo"
            ]
            for medio_nombre in medios_base:
                db.session.add(MedioPago(nombre=medio_nombre, familia_id=familia.id))

            # Agregar integrantes extra si fueron especificados
            miembros_input = request.form.get('miembros')
            if miembros_input:
                lista = [m.strip() for m in miembros_input.split(',') if m.strip()]
                for nombre_m in lista:
                    if nombre_m.lower() != nombre.lower():
                        db.session.add(MiembroFamilia(nombre=nombre_m, familia_id=familia.id))

        # Crear Usuario asociado a la familia (nueva o existente)
        nuevo_usuario = Usuario(
            nombre=nombre,
            email=email,
            confirmado=False,
            familia_id=familia.id
        )
        nuevo_usuario.set_password(password)
        db.session.add(nuevo_usuario)

        # Registrar al usuario como Miembro/Responsable si no figura ya
        miembro_existente = MiembroFamilia.query.filter_by(nombre=nombre, familia_id=familia.id).first()
        if not miembro_existente:
            db.session.add(MiembroFamilia(nombre=nombre, familia_id=familia.id))

        db.session.commit()

        # Enviar Correo de Confirmación
        try:
            token = serializer.dumps(email, salt='email-confirm-salt')
            confirm_url = url_for('confirmar_email', token=token, _external=True)

            msg = Message('Confirma tu cuenta - Finanzas Familiares', recipients=[email])
            msg.body = (
                f'¡Hola {nombre}!\n\n'
                f'Confirma tu registro ingresando al siguiente enlace:\n{confirm_url}\n\n'
                f'Tu código de invitación familiar es: {familia.codigo_invitacion}'
            )
            mail.send(msg)
            flash('Registro creado. Te hemos enviado un correo de confirmación a tu e-mail.', 'info')
        except Exception as e:
            # Fallback en caso de no tener configurado servidor SMTP
            nuevo_usuario.confirmado = True
            db.session.commit()
            flash('Registro exitoso. Tu cuenta ha sido activada automáticamente.', 'success')

        return redirect(url_for('login'))

    return render_template('registro.html')

@app.route('/confirmar/<token>')
def confirmar_email(token):
    try:
        email = serializer.loads(token, salt='email-confirm-salt', max_age=3600)
    except Exception:
        flash('El enlace de confirmación es inválido o ha expirado.', 'danger')
        return redirect(url_for('login'))

    usuario = Usuario.query.filter_by(email=email).first_or_404()
    if usuario.confirmado:
        flash('Tu cuenta ya está confirmada. Inicia sesión.', 'info')
    else:
        usuario.confirmado = True
        db.session.commit()
        flash('¡Cuenta activada con éxito! Ya puedes iniciar sesión.', 'success')

    return redirect(url_for('login'))

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Has cerrado sesión.", "info")
    return redirect(url_for("login"))


# --- RUTAS PRINCIPALES ---

@app.route("/")
@login_required
def home():
    mes_seleccionado = request.args.get("mes", "todos")

    query_base = Gasto.query.filter_by(familia_id=current_user.familia_id)
    gastos_query = query_base if mes_seleccionado == "todos" else query_base.filter(Gasto.fecha.startswith(mes_seleccionado))

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

    meses_db = db.session.query(func.substr(Gasto.fecha, 1, 7)).filter_by(familia_id=current_user.familia_id).distinct().all()
    meses_disponibles = sorted([m[0] for m in meses_db if m[0]], reverse=True)

    nombres_meses = {
        '01':'Enero', '02':'Febrero', '03':'Marzo', '04':'Abril',
        '05':'Mayo', '06':'Junio', '07':'Julio', '08':'Agosto',
        '09':'Septiembre', '10':'Octubre', '11':'Noviembre', '12':'Diciembre'
    }

    gastos_mes_db = db.session.query(
        func.substr(Gasto.fecha, 1, 7).label("mes"),
        func.sum(Gasto.monto).label("total")
    ).filter_by(familia_id=current_user.familia_id).group_by("mes").order_by(db.desc("mes")).limit(6).all()

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
@login_required
def nuevo_gasto():
    if request.method == "POST":
        gasto = Gasto(
            fecha=request.form["fecha"],
            descripcion=request.form["descripcion"],
            monto=float(request.form["monto"] or 0),
            categoria=request.form["categoria"],
            responsable=request.form["responsable"],
            medio_pago=request.form["medio_pago"],
            familia_id=current_user.familia_id
        )
        db.session.add(gasto)
        db.session.commit()
        return render_template("gasto_guardado.html", ultimo_gasto=gasto)

    return render_template("nuevo_gasto.html", gasto=None, **obtener_opciones())

@app.route('/gastos')
@login_required
def listar_gastos():
    pagina = request.args.get('pagina', 1, type=int)
    orden = request.args.get('orden', 'fecha')
    direccion = request.args.get('dir', 'desc')

    q = request.args.get('q', '').strip()
    categoria = request.args.get('categoria', '')
    responsable = request.args.get('responsable', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')

    query = Gasto.query.filter_by(familia_id=current_user.familia_id)

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
@login_required
def editar_gasto(id):
    gasto = Gasto.query.filter_by(id=id, familia_id=current_user.familia_id).first_or_404()
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
@login_required
def eliminar_gasto(id):
    gasto = Gasto.query.filter_by(id=id, familia_id=current_user.familia_id).first_or_404()
    db.session.delete(gasto)
    db.session.commit()
    return redirect(url_for("listar_gastos"))

@app.route("/reportes")
@login_required
def reportes():
    gastos_db = db.session.query(
        func.substr(Gasto.fecha, 1, 7).label("mes"),
        func.sum(Gasto.monto)
    ).filter_by(familia_id=current_user.familia_id).group_by("mes").order_by(db.desc("mes")).all()

    gastos_por_mes = [(m, float(t)) for m, t in gastos_db if m]

    total_mes_actual = gastos_por_mes[0][1] if len(gastos_por_mes) > 0 else 0
    total_mes_anterior = gastos_por_mes[1][1] if len(gastos_por_mes) > 1 else 0

    variacion = round(((total_mes_actual - total_mes_anterior) / total_mes_anterior) * 100, 1) if total_mes_anterior > 0 else 0

    categoria_mas_aumento = None
    comparativo_categorias = []
    comparativo_recurrentes = []

    if len(gastos_por_mes) >= 2:
        mes_act, mes_ant = gastos_por_mes[0][0], gastos_por_mes[1][0]

        cat_actual = dict(db.session.query(Gasto.categoria, func.sum(Gasto.monto)).filter(Gasto.familia_id == current_user.familia_id, Gasto.fecha.startswith(mes_act)).group_by(Gasto.categoria).all())
        cat_anterior = dict(db.session.query(Gasto.categoria, func.sum(Gasto.monto)).filter(Gasto.familia_id == current_user.familia_id, Gasto.fecha.startswith(mes_ant)).group_by(Gasto.categoria).all())

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

        rec_act = dict(db.session.query(Gasto.gasto_recurrente_id, func.sum(Gasto.monto)).filter(
            Gasto.familia_id == current_user.familia_id, Gasto.fecha.startswith(mes_act), Gasto.gasto_recurrente_id.isnot(None)
        ).group_by(Gasto.gasto_recurrente_id).all())

        rec_ant = dict(db.session.query(Gasto.gasto_recurrente_id, func.sum(Gasto.monto)).filter(
            Gasto.familia_id == current_user.familia_id, Gasto.fecha.startswith(mes_ant), Gasto.gasto_recurrente_id.isnot(None)
        ).group_by(Gasto.gasto_recurrente_id).all())

        for rec in GastoRecurrente.query.filter_by(familia_id=current_user.familia_id).all():
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
@login_required
def listar_recurrentes():
    mes_actual = datetime.now().strftime("%Y-%m")
    recurrentes = GastoRecurrente.query.filter_by(familia_id=current_user.familia_id).order_by(GastoRecurrente.descripcion).all()
    
    gastos_mes = db.session.query(Gasto.gasto_recurrente_id, Gasto.pagado, Gasto.id).filter(
        Gasto.familia_id == current_user.familia_id,
        Gasto.fecha.startswith(mes_actual),
        Gasto.gasto_recurrente_id.isnot(None)
    ).all()

    pagados_mes_ids = {g[0]: g[1] for g in gastos_mes}
    generados_mes_ids = {g[0]: g[2] for g in gastos_mes}

    return render_template("recurrentes.html", recurrentes=recurrentes, pagados_mes_ids=pagados_mes_ids, generados_mes_ids=generados_mes_ids)

@app.route("/recurrentes/nuevo", methods=["GET", "POST"])
@login_required
def nuevo_recurrente():
    if request.method == "POST":
        nuevo = GastoRecurrente(
            descripcion=request.form["descripcion"],
            categoria=request.form["categoria"],
            monto=float(request.form["monto"] or 0),
            responsable=request.form["responsable"],
            medio_pago=request.form["medio_pago"],
            dia_vencimiento=int(request.form["dia_vencimiento"]),
            familia_id=current_user.familia_id
        )
        db.session.add(nuevo)
        db.session.commit()
        return redirect(url_for("listar_recurrentes"))

    return render_template("recurrente_form.html", recurrente=None, **obtener_opciones())

@app.route("/recurrentes/<int:id>/editar", methods=["GET", "POST"])
@login_required
def editar_recurrente(id):
    recurrente = GastoRecurrente.query.filter_by(id=id, familia_id=current_user.familia_id).first_or_404()
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
@login_required
def toggle_recurrente(id):
    recurrente = GastoRecurrente.query.filter_by(id=id, familia_id=current_user.familia_id).first_or_404()
    recurrente.activo = not recurrente.activo
    db.session.commit()
    return redirect(url_for("listar_recurrentes"))

@app.route("/recurrentes/generar", methods=["POST"])
@login_required
def generar_gastos_mes():
    mes_actual = datetime.now().strftime("%Y-%m")
    recurrentes_activos = GastoRecurrente.query.filter_by(activo=True, familia_id=current_user.familia_id).all()

    for rec in recurrentes_activos:
        dia_str = str(rec.dia_vencimiento).zfill(2)
        fecha_gasto = f"{mes_actual}-{dia_str}"

        existente = Gasto.query.filter(
            Gasto.familia_id == current_user.familia_id,
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
                gasto_recurrente_id=rec.id,
                familia_id=current_user.familia_id
            )
            db.session.add(nuevo_gasto)

    db.session.commit()
    return redirect(url_for("listar_recurrentes"))

@app.route("/gastos/<int:id>/toggle-pago")
@login_required
def toggle_pago_gasto(id):
    gasto = Gasto.query.filter_by(id=id, familia_id=current_user.familia_id).first_or_404()
    gasto.pagado = not gasto.pagado
    db.session.commit()
    return redirect(request.referrer or url_for("listar_gastos"))

@app.route('/rapido', methods=['GET', 'POST'])
@login_required
def carga_rapida():
    if request.method == 'POST':
        nuevo_gasto = Gasto(
            fecha=request.form.get('fecha') or date.today().strftime('%Y-%m-%d'),
            descripcion=request.form.get('descripcion'),
            monto=float(request.form.get('monto', 0)),
            categoria=request.form.get('categoria'),
            responsable=request.form.get('responsable'),
            medio_pago=request.form.get('medio_pago'),
            familia_id=current_user.familia_id
        )
        db.session.add(nuevo_gasto)
        db.session.commit()
        return redirect(url_for('listar_gastos'))

    opciones = obtener_opciones()
    return render_template(
        'carga_rapida.html',
        fecha_hoy=date.today().strftime('%Y-%m-%d'),
        categorias=opciones["categorias"],
        responsables=opciones["responsables"],
        medios_pago=opciones["medios_pago"]
    )

@app.route('/opciones', methods=['GET', 'POST'])
@login_required
def opciones():
    fid = current_user.familia_id

    if request.method == 'POST':
        accion = request.form.get('accion')
        
        # Categorías
        if accion == 'agregar_categoria':
            nombre = request.form.get('nombre').strip()
            if nombre and not Categoria.query.filter_by(nombre=nombre, familia_id=fid).first():
                db.session.add(Categoria(nombre=nombre, familia_id=fid))
                db.session.commit()
                flash('Categoría agregada correctamente.', 'success')

        elif accion == 'eliminar_categoria':
            cat_id = request.form.get('id')
            cat = Categoria.query.filter_by(id=cat_id, familia_id=fid).first()
            if cat:
                db.session.delete(cat)
                db.session.commit()
                flash('Categoría eliminada.', 'info')

        # Medios de Pago
        elif accion == 'agregar_medio':
            nombre = request.form.get('nombre').strip()
            if nombre and not MedioPago.query.filter_by(nombre=nombre, familia_id=fid).first():
                db.session.add(MedioPago(nombre=nombre, familia_id=fid))
                db.session.commit()
                flash('Medio de pago agregado correctamente.', 'success')

        elif accion == 'eliminar_medio':
            medio_id = request.form.get('id')
            medio = MedioPago.query.filter_by(id=medio_id, familia_id=fid).first()
            if medio:
                db.session.delete(medio)
                db.session.commit()
                flash('Medio de pago eliminado.', 'info')

        # Miembros
        elif accion == 'agregar_miembro':
            nombre = request.form.get('nombre').strip()
            if nombre and not MiembroFamilia.query.filter_by(nombre=nombre, familia_id=fid).first():
                db.session.add(MiembroFamilia(nombre=nombre, familia_id=fid))
                db.session.commit()
                flash('Miembro agregado correctamente.', 'success')

        elif accion == 'eliminar_miembro':
            m_id = request.form.get('id')
            m = MiembroFamilia.query.filter_by(id=m_id, familia_id=fid).first()
            if m:
                db.session.delete(m)
                db.session.commit()
                flash('Miembro eliminado.', 'info')

        return redirect(url_for('opciones'))

    categorias = Categoria.query.filter_by(familia_id=fid).order_by(Categoria.nombre).all()
    medios_pago = MedioPago.query.filter_by(familia_id=fid).order_by(MedioPago.nombre).all()
    miembros = MiembroFamilia.query.filter_by(familia_id=fid).order_by(MiembroFamilia.nombre).all()

    return render_template(
        'opciones.html',
        categorias=categorias,
        medios_pago=medios_pago,
        miembros=miembros,
        codigo_invitacion=current_user.familia.codigo_invitacion
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
"""
Mercado Morcelle - Sistema Web (Jornal Digital de Ofertas)
Backend Flask + SQLite/Postgres + Jinja2
"""

import os
import sqlite3
import uuid
from datetime import datetime, date
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g, abort, send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import cloudinary
import cloudinary.uploader

# --------------------------------------------------------------------------
# CONFIGURAÇÃO
# --------------------------------------------------------------------------

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads", "produtos")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB

ADMIN_EMAIL_PADRAO = "admin@mercadomorcelle.com"
ADMIN_SENHA_PADRAO = "MudeEssaSenha123!"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "morcelle-troque-esta-chave-em-producao")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Banco de dados: se o Render (ou qualquer outro host) fornecer a variável de
# ambiente DATABASE_URL, usamos Postgres (dados persistem de verdade). Sem
# essa variável, cai para SQLite local (bom pra rodar no seu computador).
DATABASE_URL = os.environ.get("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras

    # O Render (e outros) às vezes fornecem a URL como "postgres://", mas o
    # psycopg2 aceita normalmente também "postgresql://" — ambos funcionam,
    # então não precisamos reescrever a URL.

# Cloudinary: usado para guardar as imagens dos produtos, já que o disco do
# Render (plano free) é apagado a cada deploy/reinício/spin-down. Configure
# estas 3 variáveis de ambiente no painel do Render (Environment):
#   CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True,
)
CLOUDINARY_CONFIGURADO = bool(
    os.environ.get("CLOUDINARY_CLOUD_NAME")
    and os.environ.get("CLOUDINARY_API_KEY")
    and os.environ.get("CLOUDINARY_API_SECRET")
)

CATEGORIAS_PADRAO = [
    "Mercearia", "Hortifruti", "Açougue", "Frios",
    "Laticínios", "Higiene", "Limpeza", "Bebidas", "Padaria", "Outros",
]


# --------------------------------------------------------------------------
# BANCO DE DADOS
# --------------------------------------------------------------------------
#
# O resto do arquivo foi escrito originalmente para SQLite (placeholders "?",
# db.execute(...).fetchone()["coluna"], cur.lastrowid, etc). Os dois wrappers
# abaixo fazem uma conexão Postgres "se comportar" da mesma forma, pra não
# precisar reescrever cada consulta do sistema uma por uma.

class _PGCursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor
        self.lastrowid = None

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchmany(self, size):
        return self._cursor.fetchmany(size)


class _PGConnectionWrapper:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, query, params=()):
        pg_query = query.replace("?", "%s")
        is_insert = pg_query.strip().upper().startswith("INSERT")
        if is_insert and "RETURNING" not in pg_query.upper():
            pg_query = pg_query.rstrip().rstrip(";") + " RETURNING id"

        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(pg_query, params)

        wrapper = _PGCursorWrapper(cur)
        if is_insert:
            try:
                row = cur.fetchone()
                if row:
                    wrapper.lastrowid = row["id"]
            except Exception:
                wrapper.lastrowid = None
        return wrapper

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def _conectar_postgres():
    conn = psycopg2.connect(DATABASE_URL)
    return _PGConnectionWrapper(conn)


def get_db():
    if "db" not in g:
        if USE_POSTGRES:
            g.db = _conectar_postgres()
        else:
            g.db = sqlite3.connect(DATABASE)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Cria o banco, tabelas, categorias e usuário administrador na primeira execução."""
    if USE_POSTGRES:
        _init_db_postgres()
    else:
        _init_db_sqlite()


def _init_db_postgres():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'admin',
            criado_em TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS categorias (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL UNIQUE,
            criado_em TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS produtos (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            descricao TEXT,
            categoria_id INTEGER,
            preco REAL NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL,
            FOREIGN KEY (categoria_id) REFERENCES categorias (id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS imagens_produto (
            id SERIAL PRIMARY KEY,
            produto_id INTEGER NOT NULL,
            arquivo TEXT NOT NULL,
            public_id TEXT,
            principal INTEGER NOT NULL DEFAULT 0,
            criado_em TEXT NOT NULL,
            FOREIGN KEY (produto_id) REFERENCES produtos (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS promocoes (
            id SERIAL PRIMARY KEY,
            produto_id INTEGER NOT NULL,
            preco_promocional REAL NOT NULL,
            percentual_desconto REAL,
            data_inicio TEXT NOT NULL,
            data_fim TEXT NOT NULL,
            ativa INTEGER NOT NULL DEFAULT 1,
            criado_em TEXT NOT NULL,
            FOREIGN KEY (produto_id) REFERENCES produtos (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER,
            acao TEXT NOT NULL,
            descricao TEXT,
            data_hora TEXT NOT NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE SET NULL
        );
        """
    )
    conn.commit()

    # Migração leve: adiciona a coluna public_id se a tabela já existia
    # (criada antes da integração com o Cloudinary).
    cur.execute(
        """SELECT column_name FROM information_schema.columns
           WHERE table_name = 'imagens_produto'"""
    )
    colunas = [r[0] for r in cur.fetchall()]
    if "public_id" not in colunas:
        cur.execute("ALTER TABLE imagens_produto ADD COLUMN public_id TEXT")
        conn.commit()

    # Verifica se já existe algum usuário (equivalente a "primeira execução"
    # no SQLite, que olhava se o arquivo do banco existia).
    cur.execute("SELECT COUNT(*) FROM usuarios")
    ja_tem_usuario = cur.fetchone()[0] > 0

    if not ja_tem_usuario:
        agora = datetime.now().isoformat(timespec="seconds")

        for nome_cat in CATEGORIAS_PADRAO:
            cur.execute(
                "INSERT INTO categorias (nome, criado_em) VALUES (%s, %s) ON CONFLICT (nome) DO NOTHING",
                (nome_cat, agora),
            )

        senha_hash = generate_password_hash(ADMIN_SENHA_PADRAO)
        cur.execute(
            """INSERT INTO usuarios (nome, email, senha_hash, tipo, criado_em)
               VALUES (%s, %s, %s, %s, %s) ON CONFLICT (email) DO NOTHING""",
            ("Administrador", ADMIN_EMAIL_PADRAO, senha_hash, "admin", agora),
        )
        conn.commit()

    conn.close()


def _init_db_sqlite():
    primeira_execucao = not os.path.exists(DATABASE)

    conn = sqlite3.connect(DATABASE)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'admin',
            criado_em TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            criado_em TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            descricao TEXT,
            categoria_id INTEGER,
            preco REAL NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL,
            FOREIGN KEY (categoria_id) REFERENCES categorias (id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS imagens_produto (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto_id INTEGER NOT NULL,
            arquivo TEXT NOT NULL,
            public_id TEXT,
            principal INTEGER NOT NULL DEFAULT 0,
            criado_em TEXT NOT NULL,
            FOREIGN KEY (produto_id) REFERENCES produtos (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS promocoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto_id INTEGER NOT NULL,
            preco_promocional REAL NOT NULL,
            percentual_desconto REAL,
            data_inicio TEXT NOT NULL,
            data_fim TEXT NOT NULL,
            ativa INTEGER NOT NULL DEFAULT 1,
            criado_em TEXT NOT NULL,
            FOREIGN KEY (produto_id) REFERENCES produtos (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            acao TEXT NOT NULL,
            descricao TEXT,
            data_hora TEXT NOT NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE SET NULL
        );
        """
    )
    conn.commit()

    # Migração leve: adiciona a coluna public_id se o banco já existia
    # (criado antes da integração com o Cloudinary).
    colunas = [c[1] for c in conn.execute("PRAGMA table_info(imagens_produto)").fetchall()]
    if "public_id" not in colunas:
        conn.execute("ALTER TABLE imagens_produto ADD COLUMN public_id TEXT")
        conn.commit()

    if primeira_execucao:
        agora = datetime.now().isoformat(timespec="seconds")

        for nome_cat in CATEGORIAS_PADRAO:
            cur.execute(
                "INSERT OR IGNORE INTO categorias (nome, criado_em) VALUES (?, ?)",
                (nome_cat, agora),
            )

        senha_hash = generate_password_hash(ADMIN_SENHA_PADRAO)
        cur.execute(
            """INSERT OR IGNORE INTO usuarios (nome, email, senha_hash, tipo, criado_em)
               VALUES (?, ?, ?, ?, ?)""",
            ("Administrador", ADMIN_EMAIL_PADRAO, senha_hash, "admin", agora),
        )
        conn.commit()

    conn.close()


# --------------------------------------------------------------------------
# AUXILIARES
# --------------------------------------------------------------------------

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.template_global()
def url_imagem(valor):
    """Converte o valor salvo em imagens_produto.arquivo numa URL exibível.

    Imagens novas já vêm como URL completa do Cloudinary (https://...).
    Isso também mantém compatibilidade com imagens antigas salvas localmente,
    caso ainda existam no disco no momento da requisição.
    """
    if not valor:
        return None
    if valor.startswith("http://") or valor.startswith("https://"):
        return valor
    return url_for("static", filename="uploads/produtos/" + valor)


def salvar_imagem(arquivo):
    """Valida e envia um arquivo de imagem para o Cloudinary.

    Retorna um dict {"url": ..., "public_id": ...} em caso de sucesso,
    ou None se o arquivo for inválido/vazio ou o envio falhar.
    """
    if not arquivo or arquivo.filename == "":
        return None
    if not allowed_file(arquivo.filename):
        return None

    if not CLOUDINARY_CONFIGURADO:
        app.logger.error(
            "Cloudinary não configurado: defina CLOUDINARY_CLOUD_NAME, "
            "CLOUDINARY_API_KEY e CLOUDINARY_API_SECRET nas variáveis de ambiente."
        )
        return None

    nome_unico = f"produto_{uuid.uuid4().hex[:10]}"
    try:
        resultado = cloudinary.uploader.upload(
            arquivo,
            folder="mercado_morcelle/produtos",
            public_id=nome_unico,
            resource_type="image",
        )
    except Exception as e:
        app.logger.error(f"Erro ao enviar imagem para o Cloudinary: {e}")
        return None

    return {"url": resultado.get("secure_url"), "public_id": resultado.get("public_id")}


def remover_arquivo_imagem(public_id):
    """Remove uma imagem do Cloudinary a partir do seu public_id."""
    if not public_id:
        return
    try:
        cloudinary.uploader.destroy(public_id, resource_type="image")
    except Exception as e:
        app.logger.error(f"Erro ao remover imagem do Cloudinary ({public_id}): {e}")


def registrar_log(acao, descricao=""):
    db = get_db()
    usuario_id = session.get("usuario_id")
    db.execute(
        "INSERT INTO logs (usuario_id, acao, descricao, data_hora) VALUES (?, ?, ?, ?)",
        (usuario_id, acao, descricao, datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("usuario_id"):
            flash("Você precisa fazer login para acessar esta página.", "erro")
            return redirect(url_for("login", proximo=request.path))
        return view(*args, **kwargs)
    return wrapped


def calcular_promocao_ativa(produto_id, db=None):
    """Retorna a linha de promoção ativa (dentro do período de datas) de um produto, ou None."""
    db = db or get_db()
    hoje = date.today().isoformat()
    promo = db.execute(
        """SELECT * FROM promocoes
           WHERE produto_id = ? AND ativa = 1
             AND data_inicio <= ? AND data_fim >= ?
           ORDER BY id DESC LIMIT 1""",
        (produto_id, hoje, hoje),
    ).fetchone()
    return promo


def montar_produto_dict(produto_row, db):
    """Monta um dicionário de produto com imagens e promoção ativa (se houver)."""
    produto = dict(produto_row)

    imagens = db.execute(
        "SELECT * FROM imagens_produto WHERE produto_id = ? ORDER BY principal DESC, id ASC",
        (produto["id"],),
    ).fetchall()
    produto["imagens"] = [dict(i) for i in imagens]
    principal = next((i for i in produto["imagens"] if i["principal"]), None)
    produto["imagem_principal"] = principal["arquivo"] if principal else (
        produto["imagens"][0]["arquivo"] if produto["imagens"] else None
    )

    categoria = None
    if produto["categoria_id"]:
        cat_row = db.execute(
            "SELECT * FROM categorias WHERE id = ?", (produto["categoria_id"],)
        ).fetchone()
        categoria = dict(cat_row) if cat_row else None
    produto["categoria"] = categoria

    promo = calcular_promocao_ativa(produto["id"], db)
    if promo:
        promo = dict(promo)
        if not promo.get("percentual_desconto"):
            if produto["preco"] > 0:
                promo["percentual_desconto"] = round(
                    (1 - (promo["preco_promocional"] / produto["preco"])) * 100, 2
                )
    produto["promocao"] = promo

    return produto


# --------------------------------------------------------------------------
# ROTAS PÚBLICAS
# --------------------------------------------------------------------------

@app.route("/")
def index():
    db = get_db()
    busca = request.args.get("q", "").strip()
    categoria_id = request.args.get("categoria", "").strip()

    categorias = db.execute("SELECT * FROM categorias ORDER BY nome ASC").fetchall()

    query = "SELECT * FROM produtos WHERE ativo = 1"
    params = []

    if busca:
        query += " AND (nome LIKE ? OR descricao LIKE ?)"
        params.extend([f"%{busca}%", f"%{busca}%"])

    if categoria_id:
        query += " AND categoria_id = ?"
        params.append(categoria_id)

    query += " ORDER BY criado_em DESC"

    produtos_rows = db.execute(query, params).fetchall()
    produtos = [montar_produto_dict(p, db) for p in produtos_rows]

    produtos_em_oferta = [p for p in produtos if p["promocao"]]

    return render_template(
        "index.html",
        produtos=produtos,
        produtos_em_oferta=produtos_em_oferta,
        categorias=categorias,
        busca=busca,
        categoria_selecionada=categoria_id,
    )


@app.route("/produto/<int:produto_id>")
def produto_detalhes(produto_id):
    db = get_db()
    produto_row = db.execute(
        "SELECT * FROM produtos WHERE id = ? AND ativo = 1", (produto_id,)
    ).fetchone()
    if not produto_row:
        abort(404)

    produto = montar_produto_dict(produto_row, db)
    return render_template("produto_detalhes.html", produto=produto)


# --------------------------------------------------------------------------
# AUTENTICAÇÃO
# --------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        db = get_db()
        usuario = db.execute(
            "SELECT * FROM usuarios WHERE email = ?", (email,)
        ).fetchone()

        if usuario and check_password_hash(usuario["senha_hash"], senha):
            session.clear()
            session["usuario_id"] = usuario["id"]
            session["usuario_nome"] = usuario["nome"]
            registrar_log("Login", f"Usuário {usuario['email']} realizou login.")
            flash("Login realizado com sucesso!", "sucesso")
            proximo = request.form.get("proximo") or url_for("admin_dashboard")
            return redirect(proximo)

        flash("E-mail ou senha incorretos.", "erro")

    proximo = request.args.get("proximo", "")
    return render_template("login.html", proximo=proximo)


@app.route("/logout")
def logout():
    registrar_log("Logout", "Usuário saiu do sistema.")
    session.clear()
    flash("Você saiu do sistema.", "sucesso")
    return redirect(url_for("index"))


# --------------------------------------------------------------------------
# ADMIN - DASHBOARD
# --------------------------------------------------------------------------

@app.route("/admin")
@login_required
def admin_dashboard():
    db = get_db()
    total_produtos = db.execute("SELECT COUNT(*) c FROM produtos").fetchone()["c"]
    produtos_ativos = db.execute("SELECT COUNT(*) c FROM produtos WHERE ativo = 1").fetchone()["c"]
    produtos_inativos = db.execute("SELECT COUNT(*) c FROM produtos WHERE ativo = 0").fetchone()["c"]
    total_categorias = db.execute("SELECT COUNT(*) c FROM categorias").fetchone()["c"]

    hoje = date.today().isoformat()
    promocoes_ativas = db.execute(
        """SELECT COUNT(*) c FROM promocoes
           WHERE ativa = 1 AND data_inicio <= ? AND data_fim >= ?""",
        (hoje, hoje),
    ).fetchone()["c"]

    ultimos_logs = db.execute(
        """SELECT logs.*, usuarios.nome as usuario_nome FROM logs
           LEFT JOIN usuarios ON usuarios.id = logs.usuario_id
           ORDER BY logs.id DESC LIMIT 8"""
    ).fetchall()

    return render_template(
        "admin/dashboard.html",
        total_produtos=total_produtos,
        produtos_ativos=produtos_ativos,
        produtos_inativos=produtos_inativos,
        total_categorias=total_categorias,
        promocoes_ativas=promocoes_ativas,
        ultimos_logs=ultimos_logs,
    )


# --------------------------------------------------------------------------
# ADMIN - PRODUTOS
# --------------------------------------------------------------------------

@app.route("/admin/produtos")
@login_required
def admin_produtos():
    db = get_db()
    produtos_rows = db.execute("SELECT * FROM produtos ORDER BY criado_em DESC").fetchall()
    produtos = [montar_produto_dict(p, db) for p in produtos_rows]
    return render_template("admin/produtos.html", produtos=produtos)


@app.route("/admin/produtos/novo", methods=["GET", "POST"])
@login_required
def admin_produto_novo():
    db = get_db()
    categorias = db.execute("SELECT * FROM categorias ORDER BY nome ASC").fetchall()

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        descricao = request.form.get("descricao", "").strip()
        categoria_id = request.form.get("categoria_id") or None
        preco_raw = request.form.get("preco", "0").replace(",", ".")
        ativo = 1 if request.form.get("ativo") == "on" else 0

        erros = []
        if not nome:
            erros.append("O nome do produto é obrigatório.")
        try:
            preco = float(preco_raw)
            if preco < 0:
                erros.append("O preço não pode ser negativo.")
        except ValueError:
            erros.append("Preço inválido.")
            preco = 0

        arquivos = request.files.getlist("imagens")
        arquivos_validos = [a for a in arquivos if a and a.filename]
        for a in arquivos_validos:
            if not allowed_file(a.filename):
                erros.append(f"Formato de imagem inválido: {a.filename}")

        if erros:
            for e in erros:
                flash(e, "erro")
            return render_template(
                "admin/produto_form.html", categorias=categorias, produto=None,
                form=request.form,
            )

        agora = datetime.now().isoformat(timespec="seconds")
        cur = db.execute(
            """INSERT INTO produtos (nome, descricao, categoria_id, preco, ativo, criado_em, atualizado_em)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (nome, descricao, categoria_id, preco, ativo, agora, agora),
        )
        produto_id = cur.lastrowid

        primeira = True
        for arquivo in arquivos_validos:
            resultado_upload = salvar_imagem(arquivo)
            if resultado_upload:
                db.execute(
                    """INSERT INTO imagens_produto (produto_id, arquivo, public_id, principal, criado_em)
                       VALUES (?, ?, ?, ?, ?)""",
                    (produto_id, resultado_upload["url"], resultado_upload["public_id"],
                     1 if primeira else 0, agora),
                )
                primeira = False
            else:
                flash(f"Não foi possível enviar a imagem '{arquivo.filename}'.", "erro")

        db.commit()
        registrar_log("Cadastro de produto", f"Produto '{nome}' cadastrado.")
        flash("Produto cadastrado com sucesso!", "sucesso")
        return redirect(url_for("admin_produtos"))

    return render_template("admin/produto_form.html", categorias=categorias, produto=None, form={})


@app.route("/admin/produtos/editar/<int:produto_id>", methods=["GET", "POST"])
@login_required
def admin_produto_editar(produto_id):
    db = get_db()
    produto_row = db.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,)).fetchone()
    if not produto_row:
        abort(404)

    categorias = db.execute("SELECT * FROM categorias ORDER BY nome ASC").fetchall()

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        descricao = request.form.get("descricao", "").strip()
        categoria_id = request.form.get("categoria_id") or None
        preco_raw = request.form.get("preco", "0").replace(",", ".")
        ativo = 1 if request.form.get("ativo") == "on" else 0

        erros = []
        if not nome:
            erros.append("O nome do produto é obrigatório.")
        try:
            preco = float(preco_raw)
            if preco < 0:
                erros.append("O preço não pode ser negativo.")
        except ValueError:
            erros.append("Preço inválido.")
            preco = produto_row["preco"]

        novos_arquivos = [a for a in request.files.getlist("imagens") if a and a.filename]
        for a in novos_arquivos:
            if not allowed_file(a.filename):
                erros.append(f"Formato de imagem inválido: {a.filename}")

        if erros:
            for e in erros:
                flash(e, "erro")
            produto_atual = montar_produto_dict(produto_row, db)
            return render_template(
                "admin/produto_form.html", categorias=categorias, produto=produto_atual,
                form=request.form,
            )

        agora = datetime.now().isoformat(timespec="seconds")
        db.execute(
            """UPDATE produtos SET nome=?, descricao=?, categoria_id=?, preco=?, ativo=?, atualizado_em=?
               WHERE id=?""",
            (nome, descricao, categoria_id, preco, ativo, agora, produto_id),
        )

        tem_imagens = db.execute(
            "SELECT COUNT(*) c FROM imagens_produto WHERE produto_id = ?", (produto_id,)
        ).fetchone()["c"]

        for arquivo in novos_arquivos:
            resultado_upload = salvar_imagem(arquivo)
            if resultado_upload:
                marcar_principal = 1 if tem_imagens == 0 else 0
                db.execute(
                    """INSERT INTO imagens_produto (produto_id, arquivo, public_id, principal, criado_em)
                       VALUES (?, ?, ?, ?, ?)""",
                    (produto_id, resultado_upload["url"], resultado_upload["public_id"],
                     marcar_principal, agora),
                )
                tem_imagens += 1
            else:
                flash(f"Não foi possível enviar a imagem '{arquivo.filename}'.", "erro")

        db.commit()
        registrar_log("Edição de produto", f"Produto '{nome}' (ID {produto_id}) atualizado.")
        flash("Produto atualizado com sucesso!", "sucesso")
        return redirect(url_for("admin_produtos"))

    produto = montar_produto_dict(produto_row, db)
    return render_template("admin/produto_form.html", categorias=categorias, produto=produto, form=None)


@app.route("/admin/produtos/excluir/<int:produto_id>", methods=["POST"])
@login_required
def admin_produto_excluir(produto_id):
    db = get_db()
    produto = db.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,)).fetchone()
    if not produto:
        abort(404)

    imagens = db.execute(
        "SELECT * FROM imagens_produto WHERE produto_id = ?", (produto_id,)
    ).fetchall()
    for img in imagens:
        remover_arquivo_imagem(img["public_id"])

    db.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))
    db.commit()

    registrar_log("Exclusão de produto", f"Produto '{produto['nome']}' (ID {produto_id}) excluído.")
    flash("Produto excluído com sucesso!", "sucesso")
    return redirect(url_for("admin_produtos"))


@app.route("/admin/produtos/ativar/<int:produto_id>", methods=["POST"])
@login_required
def admin_produto_ativar(produto_id):
    db = get_db()
    db.execute("UPDATE produtos SET ativo = 1 WHERE id = ?", (produto_id,))
    db.commit()
    registrar_log("Ativação de produto", f"Produto ID {produto_id} ativado.")
    flash("Produto ativado.", "sucesso")
    return redirect(url_for("admin_produtos"))


@app.route("/admin/produtos/desativar/<int:produto_id>", methods=["POST"])
@login_required
def admin_produto_desativar(produto_id):
    db = get_db()
    db.execute("UPDATE produtos SET ativo = 0 WHERE id = ?", (produto_id,))
    db.commit()
    registrar_log("Desativação de produto", f"Produto ID {produto_id} desativado.")
    flash("Produto desativado.", "sucesso")
    return redirect(url_for("admin_produtos"))


@app.route("/admin/produtos/imagem/excluir/<int:imagem_id>", methods=["POST"])
@login_required
def admin_imagem_excluir(imagem_id):
    db = get_db()
    imagem = db.execute("SELECT * FROM imagens_produto WHERE id = ?", (imagem_id,)).fetchone()
    if not imagem:
        abort(404)

    produto_id = imagem["produto_id"]
    era_principal = imagem["principal"]

    remover_arquivo_imagem(imagem["public_id"])
    db.execute("DELETE FROM imagens_produto WHERE id = ?", (imagem_id,))

    if era_principal:
        proxima = db.execute(
            "SELECT id FROM imagens_produto WHERE produto_id = ? ORDER BY id ASC LIMIT 1",
            (produto_id,),
        ).fetchone()
        if proxima:
            db.execute("UPDATE imagens_produto SET principal = 1 WHERE id = ?", (proxima["id"],))

    db.commit()
    registrar_log("Remoção de imagem", f"Imagem removida do produto ID {produto_id}.")
    flash("Imagem removida com sucesso!", "sucesso")
    return redirect(url_for("admin_produto_editar", produto_id=produto_id))


@app.route("/admin/produtos/imagem/principal/<int:imagem_id>", methods=["POST"])
@login_required
def admin_imagem_principal(imagem_id):
    db = get_db()
    imagem = db.execute("SELECT * FROM imagens_produto WHERE id = ?", (imagem_id,)).fetchone()
    if not imagem:
        abort(404)

    produto_id = imagem["produto_id"]
    db.execute("UPDATE imagens_produto SET principal = 0 WHERE produto_id = ?", (produto_id,))
    db.execute("UPDATE imagens_produto SET principal = 1 WHERE id = ?", (imagem_id,))
    db.commit()
    registrar_log("Alteração de imagem principal", f"Imagem principal alterada no produto ID {produto_id}.")
    flash("Imagem principal atualizada!", "sucesso")
    return redirect(url_for("admin_produto_editar", produto_id=produto_id))


# --------------------------------------------------------------------------
# ADMIN - CATEGORIAS
# --------------------------------------------------------------------------

@app.route("/admin/categorias", methods=["GET", "POST"])
@login_required
def admin_categorias():
    db = get_db()

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("O nome da categoria é obrigatório.", "erro")
        else:
            existente = db.execute("SELECT id FROM categorias WHERE nome = ?", (nome,)).fetchone()
            if existente:
                flash("Já existe uma categoria com esse nome.", "erro")
            else:
                db.execute(
                    "INSERT INTO categorias (nome, criado_em) VALUES (?, ?)",
                    (nome, datetime.now().isoformat(timespec="seconds")),
                )
                db.commit()
                registrar_log("Criação de categoria", f"Categoria '{nome}' criada.")
                flash("Categoria criada com sucesso!", "sucesso")
        return redirect(url_for("admin_categorias"))

    categorias = db.execute(
        """SELECT categorias.*,
                  (SELECT COUNT(*) FROM produtos WHERE produtos.categoria_id = categorias.id) as total_produtos
           FROM categorias ORDER BY nome ASC"""
    ).fetchall()
    return render_template("admin/categorias.html", categorias=categorias)


@app.route("/admin/categorias/editar/<int:categoria_id>", methods=["POST"])
@login_required
def admin_categoria_editar(categoria_id):
    db = get_db()
    nome = request.form.get("nome", "").strip()
    if not nome:
        flash("O nome da categoria é obrigatório.", "erro")
        return redirect(url_for("admin_categorias"))

    db.execute("UPDATE categorias SET nome = ? WHERE id = ?", (nome, categoria_id))
    db.commit()
    registrar_log("Edição de categoria", f"Categoria ID {categoria_id} renomeada para '{nome}'.")
    flash("Categoria atualizada com sucesso!", "sucesso")
    return redirect(url_for("admin_categorias"))


@app.route("/admin/categorias/excluir/<int:categoria_id>", methods=["POST"])
@login_required
def admin_categoria_excluir(categoria_id):
    db = get_db()
    categoria = db.execute("SELECT * FROM categorias WHERE id = ?", (categoria_id,)).fetchone()
    if not categoria:
        abort(404)

    db.execute("UPDATE produtos SET categoria_id = NULL WHERE categoria_id = ?", (categoria_id,))
    db.execute("DELETE FROM categorias WHERE id = ?", (categoria_id,))
    db.commit()
    registrar_log("Exclusão de categoria", f"Categoria '{categoria['nome']}' excluída.")
    flash("Categoria excluída com sucesso!", "sucesso")
    return redirect(url_for("admin_categorias"))


# --------------------------------------------------------------------------
# ADMIN - PROMOÇÕES
# --------------------------------------------------------------------------

@app.route("/admin/promocoes")
@login_required
def admin_promocoes():
    db = get_db()
    promocoes = db.execute(
        """SELECT promocoes.*, produtos.nome as produto_nome, produtos.preco as produto_preco
           FROM promocoes
           JOIN produtos ON produtos.id = promocoes.produto_id
           ORDER BY promocoes.id DESC"""
    ).fetchall()

    hoje = date.today().isoformat()
    promocoes_formatadas = []
    for p in promocoes:
        p = dict(p)
        p["esta_no_periodo"] = p["data_inicio"] <= hoje <= p["data_fim"]
        p["status_exibicao"] = "Ativa" if (p["ativa"] and p["esta_no_periodo"]) else (
            "Expirada" if p["data_fim"] < hoje else "Programada" if p["data_inicio"] > hoje else "Desativada"
        )
        promocoes_formatadas.append(p)

    return render_template("admin/promocoes.html", promocoes=promocoes_formatadas)


@app.route("/admin/promocoes/nova", methods=["GET", "POST"])
@login_required
def admin_promocao_nova():
    db = get_db()
    produtos = db.execute("SELECT * FROM produtos WHERE ativo = 1 ORDER BY nome ASC").fetchall()

    if request.method == "POST":
        produto_id = request.form.get("produto_id")
        preco_promocional_raw = request.form.get("preco_promocional", "0").replace(",", ".")
        data_inicio = request.form.get("data_inicio", "")
        data_fim = request.form.get("data_fim", "")

        erros = []
        produto = db.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,)).fetchone()
        if not produto:
            erros.append("Selecione um produto válido.")

        try:
            preco_promocional = float(preco_promocional_raw)
        except ValueError:
            erros.append("Preço promocional inválido.")
            preco_promocional = 0

        if not data_inicio or not data_fim:
            erros.append("Informe a data inicial e a data final.")
        elif data_fim < data_inicio:
            erros.append("A data final não pode ser anterior à data inicial.")

        if produto and preco_promocional >= produto["preco"]:
            erros.append("O preço promocional não pode ser maior que o preço normal.")

        if erros:
            for e in erros:
                flash(e, "erro")
            return render_template(
                "admin/promocao_form.html", produtos=produtos, promocao=None, form=request.form
            )

        percentual = round((1 - (preco_promocional / produto["preco"])) * 100, 2)
        agora = datetime.now().isoformat(timespec="seconds")

        db.execute(
            """INSERT INTO promocoes
               (produto_id, preco_promocional, percentual_desconto, data_inicio, data_fim, ativa, criado_em)
               VALUES (?, ?, ?, ?, ?, 1, ?)""",
            (produto_id, preco_promocional, percentual, data_inicio, data_fim, agora),
        )
        db.commit()
        registrar_log("Criação de promoção", f"Promoção criada para o produto '{produto['nome']}'.")
        flash("Promoção criada com sucesso!", "sucesso")
        return redirect(url_for("admin_promocoes"))

    return render_template("admin/promocao_form.html", produtos=produtos, promocao=None, form={})


@app.route("/admin/promocoes/editar/<int:promocao_id>", methods=["GET", "POST"])
@login_required
def admin_promocao_editar(promocao_id):
    db = get_db()
    promocao = db.execute("SELECT * FROM promocoes WHERE id = ?", (promocao_id,)).fetchone()
    if not promocao:
        abort(404)

    produtos = db.execute("SELECT * FROM produtos ORDER BY nome ASC").fetchall()

    if request.method == "POST":
        produto_id = request.form.get("produto_id")
        preco_promocional_raw = request.form.get("preco_promocional", "0").replace(",", ".")
        data_inicio = request.form.get("data_inicio", "")
        data_fim = request.form.get("data_fim", "")
        ativa = 1 if request.form.get("ativa") == "on" else 0

        erros = []
        produto = db.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,)).fetchone()
        if not produto:
            erros.append("Selecione um produto válido.")

        try:
            preco_promocional = float(preco_promocional_raw)
        except ValueError:
            erros.append("Preço promocional inválido.")
            preco_promocional = 0

        if not data_inicio or not data_fim:
            erros.append("Informe a data inicial e a data final.")
        elif data_fim < data_inicio:
            erros.append("A data final não pode ser anterior à data inicial.")

        if produto and preco_promocional >= produto["preco"]:
            erros.append("O preço promocional não pode ser maior que o preço normal.")

        if erros:
            for e in erros:
                flash(e, "erro")
            return render_template(
                "admin/promocao_form.html", produtos=produtos, promocao=promocao, form=request.form
            )

        percentual = round((1 - (preco_promocional / produto["preco"])) * 100, 2)

        db.execute(
            """UPDATE promocoes SET produto_id=?, preco_promocional=?, percentual_desconto=?,
               data_inicio=?, data_fim=?, ativa=? WHERE id=?""",
            (produto_id, preco_promocional, percentual, data_inicio, data_fim, ativa, promocao_id),
        )
        db.commit()
        registrar_log("Edição de promoção", f"Promoção ID {promocao_id} atualizada.")
        flash("Promoção atualizada com sucesso!", "sucesso")
        return redirect(url_for("admin_promocoes"))

    return render_template("admin/promocao_form.html", produtos=produtos, promocao=promocao, form=None)


@app.route("/admin/promocoes/excluir/<int:promocao_id>", methods=["POST"])
@login_required
def admin_promocao_excluir(promocao_id):
    db = get_db()
    promocao = db.execute("SELECT * FROM promocoes WHERE id = ?", (promocao_id,)).fetchone()
    if not promocao:
        abort(404)

    db.execute("DELETE FROM promocoes WHERE id = ?", (promocao_id,))
    db.commit()
    registrar_log("Exclusão de promoção", f"Promoção ID {promocao_id} excluída.")
    flash("Promoção excluída com sucesso!", "sucesso")
    return redirect(url_for("admin_promocoes"))


@app.route("/admin/promocoes/ativar/<int:promocao_id>", methods=["POST"])
@login_required
def admin_promocao_ativar(promocao_id):
    db = get_db()
    db.execute("UPDATE promocoes SET ativa = 1 WHERE id = ?", (promocao_id,))
    db.commit()
    registrar_log("Ativação de promoção", f"Promoção ID {promocao_id} ativada.")
    flash("Promoção ativada.", "sucesso")
    return redirect(url_for("admin_promocoes"))


@app.route("/admin/promocoes/desativar/<int:promocao_id>", methods=["POST"])
@login_required
def admin_promocao_desativar(promocao_id):
    db = get_db()
    db.execute("UPDATE promocoes SET ativa = 0 WHERE id = ?", (promocao_id,))
    db.commit()
    registrar_log("Desativação de promoção", f"Promoção ID {promocao_id} desativada.")
    flash("Promoção desativada.", "sucesso")
    return redirect(url_for("admin_promocoes"))


# --------------------------------------------------------------------------
# ADMIN - LOGS E CONFIGURAÇÕES
# --------------------------------------------------------------------------

@app.route("/admin/logs")
@login_required
def admin_logs():
    db = get_db()
    logs = db.execute(
        """SELECT logs.*, usuarios.nome as usuario_nome FROM logs
           LEFT JOIN usuarios ON usuarios.id = logs.usuario_id
           ORDER BY logs.id DESC LIMIT 300"""
    ).fetchall()
    return render_template("admin/logs.html", logs=logs)


@app.route("/admin/configuracoes", methods=["GET", "POST"])
@login_required
def admin_configuracoes():
    db = get_db()
    usuario = db.execute(
        "SELECT * FROM usuarios WHERE id = ?", (session["usuario_id"],)
    ).fetchone()

    if request.method == "POST":
        senha_atual = request.form.get("senha_atual", "")
        nova_senha = request.form.get("nova_senha", "")
        confirmar_senha = request.form.get("confirmar_senha", "")

        if not check_password_hash(usuario["senha_hash"], senha_atual):
            flash("Senha atual incorreta.", "erro")
        elif len(nova_senha) < 8:
            flash("A nova senha deve ter pelo menos 8 caracteres.", "erro")
        elif nova_senha != confirmar_senha:
            flash("A confirmação de senha não confere.", "erro")
        else:
            novo_hash = generate_password_hash(nova_senha)
            db.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (novo_hash, usuario["id"]))
            db.commit()
            registrar_log("Alteração de senha", "Administrador alterou a senha.")
            flash("Senha alterada com sucesso!", "sucesso")
        return redirect(url_for("admin_configuracoes"))

    return render_template("admin/configuracoes.html", usuario=usuario)


# --------------------------------------------------------------------------
# ARQUIVOS ESTÁTICOS ESPECIAIS (PWA)
# --------------------------------------------------------------------------

@app.route("/manifest.json")
def manifest():
    return send_from_directory(os.path.join(BASE_DIR, "static"), "manifest.json")


@app.route("/service-worker.js")
def service_worker():
    return send_from_directory(os.path.join(BASE_DIR, "static"), "service-worker.js")


# --------------------------------------------------------------------------
# ERROS
# --------------------------------------------------------------------------

@app.errorhandler(404)
def erro_404(e):
    return render_template("404.html"), 404


@app.errorhandler(413)
def erro_413(e):
    flash("Arquivo muito grande. O limite é de 5 MB por imagem.", "erro")
    return redirect(request.referrer or url_for("index"))


# --------------------------------------------------------------------------
# CONTEXTO GLOBAL DOS TEMPLATES
# --------------------------------------------------------------------------

@app.context_processor
def inject_globals():
    return {
        "ano_atual": datetime.now().year,
        "usuario_logado": session.get("usuario_nome"),
    }


# --------------------------------------------------------------------------
# EXECUÇÃO
# --------------------------------------------------------------------------

init_db()

if __name__ == "__main__":
    app.run(debug=True)

import sys
sys.path.insert(0, '/home/dreyzin31/.virtualenvs/sportsbot/lib/python3.12/site-packages')

from flask import Flask, request, render_template, jsonify
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import unicodedata

app = Flask(__name__)

# ==========================================
# NORMALIZAÇÃO
# ==========================================
def normalizar(t):
    if not t:
        return ""
    t = str(t).strip().lower()
    t = unicodedata.normalize("NFD", t)
    t = t.encode("ascii", "ignore").decode("utf-8")
    return t


# ==========================================
# DESATIVAR LIMPEZA
# ==========================================
def limpar_planilha():
    pass  # Nunca mais limpa automaticamente


# ==========================================
# CONEXÃO PLANILHA
# ==========================================
CREDENTIALS_PATH = "/home/dreyzin31/mysite/credenciais-sheets.json"
SCOPE = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]

try:
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPE)
    gc = gspread.authorize(creds)

    # 🔥 SUA PLANILHA CORRETA
    planilha = gc.open_by_key("1A3Dwg5vmWNVVI_sexq7LI-Ci1dV7D9H5opAkwaAkZuo")

    estoque_sheet = planilha.worksheet("Estoque")
    saidas_sheet = planilha.worksheet("Saídas")

    print("✅ Conectado na planilha correta!")

except Exception as e:
    print("❌ Erro:", e)
    estoque_sheet = None
    saidas_sheet = None


# ==========================================
# PÁGINAS HTML
# ==========================================
@app.route("/")
def dashboard():
    return render_template("dashboard.html")

@app.route("/estoque")
def pagina_estoque():
    return render_template("estoque.html")

@app.route("/entrada")
def pagina_entrada():
    return render_template("entrada.html")

@app.route("/saida")
def pagina_saida():
    return render_template("saida.html")

@app.route("/pesquisar")
def pagina_pesquisar():
    return render_template("pesquisar.html")

@app.route("/editar")
def pagina_editar():
    return render_template("editar.html")

@app.route("/validade")
def pagina_validade():
    return render_template("validade.html")

@app.route("/historico")
def pagina_historico():
    return render_template("historico.html")

@app.route("/nota_saida")
def pagina_nota_saida():
    return render_template("nota_saida.html")


# ==========================================
# AUTOCOMPLETE
# ==========================================
@app.route("/api/autocomplete_produtos/<texto>")
def api_autocomplete_produtos(texto):

    termo = normalizar(texto)
    dados = estoque_sheet.get_all_records()
    encontrados = []

    for d in dados:
        if termo in normalizar(d["Produto"]):
            encontrados.append(d["Produto"])

    return jsonify(list(dict.fromkeys(encontrados)))


# ==========================================
# LISTA LOTES
# ==========================================
@app.route("/api/lotes/<produto>")
def api_lotes(produto):

    produto_norm = normalizar(produto)
    dados = estoque_sheet.get_all_records()
    lotes = []

    for d in dados:
        if produto_norm in normalizar(d["Produto"]):
            lotes.append({
                "lote": d["Lote"],
                "validade": d["Validade"],
                "quantidade": int(d["Quantidade"])
            })

    return jsonify(lotes)


# ==========================================
# INFO LOTE
# ==========================================
@app.route("/api/info/<produto>/<lote>")
def api_info(produto, lote):

    produto_norm = normalizar(produto)
    dados = estoque_sheet.get_all_records()

    for d in dados:
        if produto_norm in normalizar(d["Produto"]) and str(d["Lote"]) == str(lote):
            return jsonify({
                "validade": d["Validade"],
                "quantidade": d["Quantidade"]
            })

    return jsonify({"erro": "nao encontrado"}), 404


# ==========================================
# API ESTOQUE
# ==========================================
@app.route("/api/estoque")
def api_estoque():
    return jsonify(estoque_sheet.get_all_records())


# ==========================================
# API ENTRADA
# ==========================================
@app.route("/api/entrada", methods=["POST"])
def api_entrada():

    data = request.json

    estoque_sheet.insert_row([
        data["produto"].strip(),
        data["lote"].strip(),
        data["validade"].strip(),
        int(data["quantidade"]),
        "OK",
        datetime.now().strftime("%d/%m/%Y")
    ], 2)

    return jsonify({"status": "ok"})


# ==========================================
# API SAÍDA
# ==========================================
ultima_nota = {}

@app.route("/api/saida_carrinho", methods=["POST"])
def api_saida_carrinho():

    global ultima_nota
    itens = request.json
    dados = estoque_sheet.get_all_records()

    nota_itens = []

    for item in itens:
        prod_norm = normalizar(item["produto"])
        lote = str(item["lote"])
        qtd = int(item["quantidade"])

        for idx, row in enumerate(dados):

            if prod_norm in normalizar(row["Produto"]) and str(row["Lote"]) == lote:

                linha_sheet = idx + 2
                validade = row["Validade"]

                atual = int(estoque_sheet.cell(linha_sheet, 4).value)
                novo = max(atual - qtd, 0)

                estoque_sheet.update_cell(linha_sheet, 4, novo)

                if novo == 0:
                    estoque_sheet.delete_rows(linha_sheet)

                saidas_sheet.append_row([
                    datetime.now().strftime("%d/%m/%Y"),
                    row["Produto"],
                    lote,
                    qtd,
                    "WEB"
                ])

                nota_itens.append({
                    "produto": row["Produto"],
                    "lote": lote,
                    "validade": validade,
                    "quantidade": qtd
                })

                break

    ultima_nota = {
        "data": datetime.now().strftime("%d/%m/%Y"),
        "itens": nota_itens
    }

    return jsonify({"status": "ok"})


# ==========================================
# API ULTIMA NOTA
# ==========================================
@app.route("/api/ultima_nota")
def api_ultima_nota():
    return jsonify(ultima_nota)


# ==========================================
# VALIDADES
# ==========================================
@app.route("/api/validade")
def api_validade():

    hoje = datetime.today()
    dados = estoque_sheet.get_all_records()
    resp = []

    for d in dados:
        val = d["Validade"].strip()

        if val in ("", "0000-00-00"):
            continue

        try:
            dt = datetime.strptime(val, "%Y-%m-%d")
        except:
            continue

        dias = (dt - hoje).days

        if dias <= 45:
            resp.append({
                "Produto": d["Produto"],
                "Lote": d["Lote"],
                "Validade": val,
                "DiasRestantes": dias,
                "Quantidade": d["Quantidade"]
            })

    return jsonify(sorted(resp, key=lambda x: x["DiasRestantes"]))


# ==========================================
# START
# ==========================================
if __name__ == "__main__":
    app.run()

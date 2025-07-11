# api/app.py
from flask import Flask, jsonify, request
import requests, re, os

app = Flask(__name__)

# ───────────────────────────────────────────────
# Configurações (lidas do ambiente)
# ───────────────────────────────────────────────
API_BASE  = os.getenv("IPTV_API" , "https://hiveos.space/player_api.php")
USERNAME  = os.getenv("IPTV_USER", "VenusPlay")
PASSWORD  = os.getenv("IPTV_PASS", "659225573")
PAGE_SIZE = 27

# ───────────────────────────────────────────────
# Funções utilitárias
# ───────────────────────────────────────────────
def limpar_titulo(titulo):
    return re.sub(r"\s*\(\d{4}\)$", "", (titulo or "").strip())

def url_banner(path):
    return f"https://image.tmdb.org/t/p/w1280{path}" if path and not str(path).startswith("http") else path or ""

def url_capa(path):
    return f"https://image.tmdb.org/t/p/w600_and_h900_bestv2{path}" if path and not str(path).startswith("http") else path or ""

def primeiro_genero(g):
    return (g or "").split(",")[0].strip()

def get_api_data(action):
    url = f"{API_BASE}?username={USERNAME}&password={PASSWORD}&action={action}"
    try:
        return requests.get(url, timeout=10).json()
    except Exception as e:
        return {"error": str(e)}

def clean_item(item, tipo):
    return {
        "ID":      item.get("stream_id") or item.get("series_id"),
        "Título":  limpar_titulo(item.get("name")),
        "Capa":    url_capa(item.get("stream_icon") or item.get("cover")),
        "Banner":  url_banner(item.get("backdrop_path")),
        "Ano":     item.get("year") or "",
        "Gênero":  primeiro_genero(item.get("genre")),
        "Tipo":    tipo,
        "Sinopse": item.get("plot", ""),
        "Score":   item.get("rating", ""),
        "Player":  item.get("stream_id") if tipo == "Filme" else None
    }

# ───────────────────────────────────────────────
# Endpoints
# ───────────────────────────────────────────────
@app.route("/api/Venus/Filmes")
def get_filmes():
    page = int(request.args.get("page", 1))
    data = get_api_data("get_vod_streams")
    if "error" in data:
        return jsonify(data), 500
    start, end = (page - 1) * PAGE_SIZE, page * PAGE_SIZE
    return jsonify([clean_item(i, "Filme") for i in data][start:end])

@app.route("/api/Venus/Séries")
def get_series():
    page = int(request.args.get("page", 1))
    data = get_api_data("get_series")
    if "error" in data:
        return jsonify(data), 500
    start, end = (page - 1) * PAGE_SIZE, page * PAGE_SIZE
    return jsonify([clean_item(i, "Série") for i in data][start:end])

@app.route("/api/Info/Venus/Filmes")
def info_filme():
    vid = request.args.get("id")
    if not vid:
        return jsonify({"error": "ID necessário"}), 400
    info = get_api_data(f"get_vod_info&vod_id={vid}").get("info", {})
    return jsonify({
        "ID": vid,
        "Título": limpar_titulo(info.get("title")),
        "Capa": url_capa(info.get("movie_image")),
        "Banner": url_banner(info.get("backdrop_path")),
        "Ano": info.get("year", ""),
        "Gênero": primeiro_genero(info.get("genre")),
        "Tipo": "Filme",
        "Sinopse": info.get("plot", ""),
        "Score": info.get("rating", ""),
        "Player": vid
    })

@app.route("/api/Info/Venus/Séries")
def info_serie():
    sid = request.args.get("id")
    if not sid:
        return jsonify({"error": "ID necessário"}), 400
    info = get_api_data(f"get_series_info&series_id={sid}").get("info", {})
    return jsonify({
        "ID": sid,
        "Título": limpar_titulo(info.get("name")),
        "Capa": url_capa(info.get("cover")),
        "Banner": url_banner(info.get("backdrop_path")),
        "Ano": info.get("releaseDate", ""),
        "Gênero": primeiro_genero(info.get("genre")),
        "Tipo": "Série",
        "Sinopse": info.get("plot", ""),
        "Score": info.get("rating", "")
    })

@app.route("/api/Venus/Temporada")
def get_temporadas():
    sid = request.args.get("id")
    if not sid:
        return jsonify({"error": "ID necessário"}), 400
    seasons = get_api_data(f"get_series_info&series_id={sid}").get("episodes", {})
    return jsonify([{"Titulo": f"Temporada {t}", "ID": sid, "Temporada": t} for t in seasons])

@app.route("/api/Venus/Episódio")
def get_episodios():
    sid = request.args.get("id")
    temporada = request.args.get("temporada")
    if not (sid and temporada):
        return jsonify({"error": "ID e Temporada necessários"}), 400
    eps = get_api_data(f"get_series_info&series_id={sid}").get("episodes", {}).get(temporada, [])
    return jsonify([{
        "ID": ep["id"],
        "Episodio": ep["episode_num"],
        "Titulo_EP": ep.get("title", ""),
        "Capa_EP": url_capa(ep.get("info", {}).get("movie_image")),
        "Play": ep["id"],
        "Temporada": temporada
    } for ep in eps])

@app.route("/api/Venus/Categorias")
def get_categorias():
    return jsonify(get_api_data("get_vod_categories"))

@app.route("/api/VenusPlay")
def all_conteudo():
    page = int(request.args.get("page", 1))
    filmes = get_api_data("get_vod_streams")
    series = get_api_data("get_series")
    if "error" in filmes or "error" in series:
        return jsonify({"error": "Erro ao obter dados"}), 500
    todos = [clean_item(i, "Filme") for i in filmes] + [clean_item(s, "Série") for s in series]
    todos.sort(key=lambda x: x["Título"])
    start, end = (page - 1) * PAGE_SIZE, page * PAGE_SIZE
    return jsonify(todos[start:end])

# ───────────────────────────────────────────────
# Execução local
# ───────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

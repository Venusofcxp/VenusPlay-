from flask import Flask, jsonify, request
import requests
import re
import os               # ← agora usamos variáveis de ambiente

app = Flask(__name__)

# === Configurações ===
API_BASE = "https://hiveos.space/player_api.php"
USERNAME = os.getenv("IPTV_USER", "VenusPlay")      # defina em “Environment Variables” na Vercel
PASSWORD = os.getenv("IPTV_PASS", "659225573")
PAGE_SIZE = 27

# === Funções utilitárias ===
def limpar_titulo(titulo):
    if not titulo:
        return ""
    return re.sub(r"\s*\(\d{4}\)$", "", titulo.strip())

def url_banner(path):
    if path and isinstance(path, str):
        if not path.startswith("http"):
            return f"https://image.tmdb.org/t/p/w1280{path}"
        return path
    return ""

def url_capa(path):
    if path and isinstance(path, str):
        if not path.startswith("http"):
            return f"https://image.tmdb.org/t/p/w600_and_h900_bestv2{path}"
        return path
    return ""

def primeiro_genero(genero):
    if not genero:
        return ""
    return genero.split(",")[0].strip()

def get_api_data(endpoint):
    url = f"{API_BASE}?username={USERNAME}&password={PASSWORD}&action={endpoint}"
    try:
        response = requests.get(url, timeout=10)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# === Paginados ===
def clean_item(item, tipo):
    return {
        "ID": item.get("stream_id") or item.get("series_id"),
        "Título": limpar_titulo(item.get("name")),
        "Capa": url_capa(item.get("stream_icon") or item.get("cover")),
        "Banner": url_banner(item.get("backdrop_path")),
        "Ano": item.get("year") or "",
        "Gênero": primeiro_genero(item.get("genre")),
        "Tipo": tipo,
        "Sinopse": item.get("plot", ""),
        "Score": item.get("rating", ""),
        "Player": item.get("stream_id") if tipo == "Filme" else None
    }

@app.route("/api/Venus/Filmes")
def get_filmes():
    page = int(request.args.get("page", 1))
    data = get_api_data("get_vod_streams")
    if "error" in data:
        return jsonify(data), 500
    filmes = [clean_item(i, "Filme") for i in data]
    start, end = (page - 1) * PAGE_SIZE, page * PAGE_SIZE
    return jsonify(filmes[start:end])

@app.route("/api/Venus/Séries")
def get_series():
    page = int(request.args.get("page", 1))
    data = get_api_data("get_series")
    if "error" in data:
        return jsonify(data), 500
    series = [clean_item(i, "Série") for i in data]
    start, end = (page - 1) * PAGE_SIZE, page * PAGE_SIZE
    return jsonify(series[start:end])

# === Info de Filmes/Séries ===
@app.route("/api/Info/Venus/Filmes")
def info_filme():
    id_ = request.args.get("id")
    if not id_:
        return jsonify({"error": "ID necessário"}), 400
    url = f"{API_BASE}?username={USERNAME}&password={PASSWORD}&action=get_vod_info&vod_id={id_}"
    try:
        info = requests.get(url, timeout=10).json().get("info", {})
    except:
        return jsonify({"error": "Erro ao processar resposta"}), 500
    return jsonify({
        "ID": id_,
        "Título": limpar_titulo(info.get("title")),
        "Capa": url_capa(info.get("movie_image")),
        "Banner": url_banner(info.get("backdrop_path")),
        "Ano": info.get("year") or "",
        "Gênero": primeiro_genero(info.get("genre")),
        "Tipo": "Filme",
        "Sinopse": info.get("plot") or "",
        "Score": info.get("rating") or "",
        "Player": id_
    })

@app.route("/api/Info/Venus/Séries")
def info_serie():
    id_ = request.args.get("id")
    if not id_:
        return jsonify({"error": "ID necessário"}), 400
    url = f"{API_BASE}?username={USERNAME}&password={PASSWORD}&action=get_series_info&series_id={id_}"
    try:
        info = requests.get(url, timeout=10).json().get("info", {})
    except:
        return jsonify({"error": "Erro ao processar resposta"}), 500
    return jsonify({
        "ID": id_,
        "Título": limpar_titulo(info.get("name")),
        "Capa": url_capa(info.get("cover")),
        "Banner": url_banner(info.get("backdrop_path")),
        "Ano": info.get("releaseDate") or "",
        "Gênero": primeiro_genero(info.get("genre")),
        "Tipo": "Série",
        "Sinopse": info.get("plot") or "",
        "Score": info.get("rating") or ""
    })

# === Temporadas e Episódios ===
@app.route("/api/Venus/Temporada")
def get_temporadas():
    id_ = request.args.get("id")
    if not id_:
        return jsonify({"error": "ID necessário"}), 400
    try:
        seasons = requests.get(
            f"{API_BASE}?username={USERNAME}&password={PASSWORD}&action=get_series_info&series_id={id_}"
        ).json().get("episodes", {})
    except:
        return jsonify({"error": "Erro ao obter temporadas"}), 500
    return jsonify([{"Titulo": f"Temporada {t}", "ID": id_, "Temporada": t} for t in seasons])

@app.route("/api/Venus/Episódio")
def get_episodios():
    id_, temporada = request.args.get("id"), request.args.get("temporada")
    if not id_ or not temporada:
        return jsonify({"error": "ID e Temporada necessários"}), 400
    try:
        episodes = requests.get(
            f"{API_BASE}?username={USERNAME}&password={PASSWORD}&action=get_series_info&series_id={id_}"
        ).json().get("episodes", {}).get(temporada, [])
    except:
        return jsonify({"error": "Erro ao obter episódios"}), 500
    return jsonify([
        {
            "ID": ep.get("id"),
            "Episodio": ep.get("episode_num"),
            "Titulo_EP": ep.get("title") or "",
            "Capa_EP": url_capa(ep.get("info", {}).get("movie_image")),
            "Play": ep.get("id"),
            "Temporada": temporada
        } for ep in episodes
    ])

# === Categorias ===
@app.route("/api/Venus/Categorias")
def get_categorias():
    return jsonify(get_api_data("get_vod_categories"))

# === Unifica Filmes + Séries ===
@app.route("/api/VenusPlay")
def all_conteudo():
    page = int(request.args.get("page", 1))
    filmes, series = get_api_data("get_vod_streams"), get_api_data("get_series")
    if "error" in filmes or "error" in series:
        return jsonify({"error": "Erro ao obter dados"}), 500
    todos = [clean_item(i, "Filme") for i in filmes] + [clean_item(s, "Série") for s in series]
    todos.sort(key=lambda x: x["Título"] or "")
    start, end = (page - 1) * PAGE_SIZE, page * PAGE_SIZE
    return jsonify(todos[start:end])

# === Execução local ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

# === Handler para Vercel ===
from vercel_wsgi import handle_request    # <– depende de vercel-wsgi
def handler(environ, start_response):
    return handle_request(app, environ, start_response)

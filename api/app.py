from flask import Flask, jsonify, request
import requests
import re

app = Flask(__name__)

API_BASE = "https://hiveos.space/player_api.php"
USERNAME = "VenusPlay"
PASSWORD = "659225573"
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
        "Sinopse": item.get("plot", ""),  # às vezes vem no item
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
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    return jsonify(filmes[start:end])

@app.route("/api/Venus/Séries")
def get_series():
    page = int(request.args.get("page", 1))
    data = get_api_data("get_series")
    if "error" in data:
        return jsonify(data), 500

    series = [clean_item(i, "Série") for i in data]
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    return jsonify(series[start:end])

# === Info de Filmes/Séries ===

@app.route("/api/Info/Venus/Filmes")
def info_filme():
    id_ = request.args.get("id")
    if not id_:
        return jsonify({"error": "ID necessário"}), 400

    url = f"{API_BASE}?username={USERNAME}&password={PASSWORD}&action=get_vod_info&vod_id={id_}"
    try:
        r = requests.get(url, timeout=10)
        info = r.json().get("info", {})
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
        r = requests.get(url, timeout=10)
        info = r.json().get("info", {})
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
        resp = requests.get(
            f"{API_BASE}?username={USERNAME}&password={PASSWORD}&action=get_series_info&series_id={id_}",
            timeout=10
        )
        data = resp.json()
        info = data.get("info", {})          # <- pega informações da série
        titulo_serie = limpar_titulo(info.get("name"))
        seasons = data.get("episodes", {})   # dicionário {temporada: [episódios]}
    except Exception:
        return jsonify({"error": "Erro ao obter temporadas"}), 500

    # Agora cada item usa o título da série
    return jsonify([
        {
            "ID": id_,
            "Temporada": temp,
            "Titulo": titulo_serie          # <- título correto da série
        }
        for temp in seasons.keys()
    ])

@app.route("/api/Venus/Episódio")
def get_episodios():
    id_ = request.args.get("id")
    temporada = request.args.get("temporada")
    if not id_ or not temporada:
        return jsonify({"error": "ID e Temporada necessários"}), 400

    try:
        r = requests.get(
            f"{API_BASE}?username={USERNAME}&password={PASSWORD}&action=get_series_info&series_id={id_}",
            timeout=10
        )
        episodes_dict = r.json().get("episodes", {})
        episodes = []

        # Busca tolerante: compara ignorando zeros à esquerda
        for key in episodes_dict.keys():
            if key == temporada or key.lstrip("0") == temporada.lstrip("0"):
                episodes = episodes_dict[key]
                break

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
        }
        for ep in episodes
    ])

# === Categorias ===

@app.route("/api/Venus/Categorias")
def get_categorias():
    data = get_api_data("get_vod_categories")
    return jsonify(data)

# === Unifica Filmes + Séries ===

@app.route("/api/VenusPlay")
def all_conteudo():
    page = int(request.args.get("page", 1))

    filmes = get_api_data("get_vod_streams")
    series = get_api_data("get_series")
    if "error" in filmes or "error" in series:
        return jsonify({"error": "Erro ao obter dados"}), 500

    todos = [clean_item(i, "Filme") for i in filmes] + [clean_item(s, "Série") for s in series]
    todos.sort(key=lambda x: x["Título"] or "")
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    return jsonify(todos[start:end])

# === Execução ===

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

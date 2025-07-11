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

@app.route("/api/Venus/Série")
def obter_episodio_serie():
    id_serie = request.args.get("id")
    temporada = request.args.get("Temporada")
    episodio = request.args.get("Episódio")

    if not id_serie or not temporada or not episodio:
        return jsonify({"error": "Parâmetros 'id', 'Temporada' e 'Episódio' são obrigatórios."}), 400

    try:
        # Consulta dados da série
        r = requests.get(
            f"{API_BASE}?username={USERNAME}&password={PASSWORD}&action=get_series_info&series_id={id_serie}",
            timeout=10
        )
        data = r.json()
        info = data.get("info", {})
        episodios_dict = data.get("episodes", {})

        # Chave correta da temporada: S01, S02...
        temporada_key = f"S{int(temporada):02}"

        # Lista de episódios da temporada
        episodios = episodios_dict.get(temporada_key, [])

        # Procura o episódio desejado
        for ep in episodios:
            if str(ep.get("episode_num")) == str(episodio):
                titulo_serie = limpar_titulo(info.get("name"))
                temp_formatada = temporada_key  # já está como S01
                ep_formatado = f"E{int(ep.get('episode_num')):02}"  # E01, E02...

                titulo_completo = f"{titulo_serie} - {temp_formatada}{ep_formatado} - {ep.get('title')}"
                return jsonify([
                    {
                        "ID": id_serie,
                        "Episodio": ep.get("episode_num"),
                        "Titulo_EP": titulo_completo,
                        "Capa_EP": url_banner(ep.get("info", {}).get("backdrop_path")),
                        "Play": ep.get("id"),
                        "Temporada": temporada
                    }
                ])

        return jsonify({"error": "Episódio não encontrado"}), 404

    except Exception as e:
        return jsonify({"error": f"Erro ao buscar episódio: {str(e)}"}), 500

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

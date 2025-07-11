from flask import Flask, jsonify, request
import requests
import re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = Flask(__name__)

# === CONFIGURAÇÃO GERAL ===
API_BASE   = "https://hiveos.space/player_api.php"
USERNAME   = "VenusPlay"
PASSWORD   = "659225573"
PAGE_SIZE  = 27
TIMEOUT    = 10          # segundos para cada requisição à IPTV
POOL_SIZE  = 100         # conexões simultâneas reutilizáveis

# === SESSÃO HTTP COM POOL / RETRY ===
session = requests.Session()
adapter = HTTPAdapter(
    pool_connections=POOL_SIZE,
    pool_maxsize=POOL_SIZE,
    max_retries=Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
)
session.mount("http://", adapter)
session.mount("https://", adapter)

# === FUNÇÕES UTILITÁRIAS ===
def limpar_titulo(titulo: str) -> str:
    if not titulo:
        return ""
    return re.sub(r"\s*\(\d{4}\)$", "", titulo.strip())

def url_banner(path: str) -> str:
    if path and isinstance(path, str):
        if not path.startswith("http"):
            return f"https://image.tmdb.org/t/p/w1280{path}"
        return path
    return ""

def url_capa(path: str) -> str:
    if path and isinstance(path, str):
        if not path.startswith("http"):
            return f"https://image.tmdb.org/t/p/w600_and_h900_bestv2{path}"
        return path
    return ""

def primeiro_genero(genero: str) -> str:
    if not genero:
        return ""
    return genero.split(",")[0].strip()

def get_api_data(endpoint: str):
    """GET simples a qualquer endpoint Xtream"""
    url = f"{API_BASE}?username={USERNAME}&password={PASSWORD}&action={endpoint}"
    try:
        resp = session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

# === PAGINAÇÃO (FILMES / SÉRIES LISTAGEM GERAL) ===
def clean_item(item: dict, tipo: str):
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

# === ROTAS DE LISTAGEM (FILMES / SÉRIES) ===
@app.route("/api/Venus/Filmes")
def get_filmes():
    page  = max(int(request.args.get("page", "1")), 1)
    data  = get_api_data("get_vod_streams")
    if "error" in data:
        return jsonify(data), 502
    filmes = [clean_item(i, "Filme") for i in data]
    i0, i1 = (page-1)*PAGE_SIZE, page*PAGE_SIZE
    return jsonify(filmes[i0:i1])

@app.route("/api/Venus/Séries")
def get_series():
    page  = max(int(request.args.get("page", "1")), 1)
    data  = get_api_data("get_series")
    if "error" in data:
        return jsonify(data), 502
    series = [clean_item(i, "Série") for i in data]
    i0, i1 = (page-1)*PAGE_SIZE, page*PAGE_SIZE
    return jsonify(series[i0:i1])

# === INFO DE FILME / SÉRIE ===
@app.route("/api/Info/Venus/Filmes")
def info_filme():
    id_ = request.args.get("id")
    if not id_:
        return jsonify({"error": "ID necessário"}), 400
    data = get_api_data(f"get_vod_info&vod_id={id_}")
    info = data.get("info", {})
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
    data = get_api_data(f"get_series_info&series_id={id_}")
    info = data.get("info", {})
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

# === ROTAS POR SÉRIE (TEMPORADAS & EPISÓDIOS) ===
def buscar_series_info(id_serie: str):
    return get_api_data(f"get_series_info&series_id={id_serie}")

@app.route("/api/Venus/Temporadas")
def listar_temporadas_da_serie():
    id_serie = request.args.get("id")
    if not id_serie:
        return jsonify({"error": "Parâmetro 'id' da série é obrigatório."}), 400
    data = buscar_series_info(id_serie)
    if "error" in data:
        return jsonify(data), 502
    nome_serie    = limpar_titulo(data.get("info", {}).get("name", ""))
    episodes_dict = data.get("episodes", {})
    resultados = [{
        "ID": str(id_serie),
        "Temporada": k.replace("S", "").lstrip("0") or "0",
        "Titulo": nome_serie
    } for k in episodes_dict.keys()]
    return jsonify(resultados)

@app.route("/api/Venus/Episodios")
def listar_episodios_da_serie():
    id_serie = request.args.get("id")
    if not id_serie:
        return jsonify({"error": "Parâmetro 'id' da série é obrigatório."}), 400
    data = buscar_series_info(id_serie)
    if "error" in data:
        return jsonify(data), 502
    nome_serie    = limpar_titulo(data.get("info", {}).get("name", ""))
    episodes_dict = data.get("episodes", {})
    resultados = []
    for temp_key, episodios in episodes_dict.items():
        num_temp = temp_key.replace("S", "").lstrip("0") or "0"
        for ep in episodios:
            num_ep_raw = ep.get("episode_num") or "0"
            try:
                num_ep = int(num_ep_raw)
            except ValueError:
                num_ep = 0
            info_ep  = ep.get("info", {})
            banner   = url_banner(info_ep.get("backdrop_path") or info_ep.get("movie_image"))
            titulo   = f"{nome_serie} - {temp_key}E{num_ep:02} - {ep.get('title')}"
            resultados.append({
                "ID": str(id_serie),
                "Temporada": num_temp,
                "Episodio": str(num_ep),
                "Titulo_EP": titulo,
                "Capa_EP": banner,
                "Play": ep.get("id")
            })
    return jsonify(resultados)

# === CATEGORIAS ===
@app.route("/api/Venus/Categorias")
def get_categorias():
    return jsonify(get_api_data("get_vod_categories"))

# === FILMES + SÉRIES NUMA LISTA ÚNICA (PAGINADO) ===
@app.route("/api/VenusPlay")
def all_conteudo():
    page    = max(int(request.args.get("page", "1")), 1)
    filmes  = get_api_data("get_vod_streams")
    series  = get_api_data("get_series")
    if "error" in filmes or "error" in series:
        return jsonify({"error": "Erro ao obter dados"}), 502
    todos = [clean_item(i, "Filme") for i in filmes] + [clean_item(s, "Série") for s in series]
    todos.sort(key=lambda x: x["Título"] or "")
    i0, i1 = (page-1)*PAGE_SIZE, page*PAGE_SIZE
    return jsonify(todos[i0:i1])

# === EXECUÇÃO ===
if __name__ == "__main__":
    # threaded=True para múltiplas requisições paralelas no servidor de desenvolvimento
    app.run(host="0.0.0.0", port=5000, threaded=True)

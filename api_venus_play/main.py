from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import httpx
import re
from typing import Optional, Dict, Any, List
import asyncio
import time
from functools import wraps

# ============================================================
# Configurações
# ============================================================

API_BASE = "https://hiveos.space/player_api.php"
USERNAME = "VenusPlay"
PASSWORD = "659225573"

PAGE_SIZE = 27
TIMEOUT = 10          # segundos para cada request externo
CACHE_TTL = 60        # segundos (ajuste conforme necessidade)

app = FastAPI()

# ============================================================
# Recursos globais – criados uma única vez
# ============================================================

# Cliente HTTP compartilhado (connection-pool)
client: httpx.AsyncClient | None = None

# Regex pré-compiladas
RE_TITULO_ANO = re.compile(r"\s*\(\d{4}\)$")
RE_SUFFIX_EP  = re.compile(r"\s*-\s*S\d{2}E\d{2}\s*-\s*Capítulo\s*\d+\s*$", re.IGNORECASE)

# Cache simples em memória (TTL)
_cache: Dict[str, tuple[float, Any]] = {}


def ttl_cache(key_template: str):
    """Decorator simples para cachear corrotinas que hitam a API IPTV."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = key_template.format(*args, **kwargs)
            # hit
            hit = _cache.get(key)
            now = time.time()
            if hit and now - hit[0] < CACHE_TTL:
                return hit[1]
            # miss
            result = await func(*args, **kwargs)
            _cache[key] = (now, result)
            return result
        return wrapper
    return decorator


# ============================================================
# Funções utilitárias
# ============================================================

def limpar_titulo(t: Optional[str]) -> str:
    return "" if not t else RE_TITULO_ANO.sub("", t.strip())

def url_banner(path: Optional[str]) -> str:
    if path and not path.startswith("http"):
        return f"https://image.tmdb.org/t/p/w1280{path}"
    return path or ""

def url_capa(path: Optional[str]) -> str:
    if path and not path.startswith("http"):
        return f"https://image.tmdb.org/t/p/w600_and_h900_bestv2{path}"
    return path or ""

def primeiro_genero(gen: Optional[str]) -> str:
    return "" if not gen else gen.split(",")[0].strip()

async def _fetch(endpoint: str) -> Any:
    """Chamada bruta à API IPTV com tratamento de erro e timeout."""
    url = f"{API_BASE}?username={USERNAME}&password={PASSWORD}&action={endpoint}"
    try:
        r = await client.get(url, timeout=TIMEOUT, follow_redirects=True)
        r.raise_for_status()
        return r.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        # devolve erro tratável pela rota
        return {"error": str(exc)}

@ttl_cache("{0}")
async def get_api_data(endpoint: str):
    """Wrapper com cache TTL."""
    return await _fetch(endpoint)

def clean_item(item: dict, tipo: str) -> dict:
    raw_banner = item.get("backdrop_path")

    if isinstance(raw_banner, list):
        raw_banner = raw_banner[0] if raw_banner else ""
    elif isinstance(raw_banner, str) and "," in raw_banner:
        raw_banner = raw_banner.split(",")[0]

    if not raw_banner:
        raw_banner = item.get("stream_icon") if tipo == "Filme" else item.get("cover")

    return {
        "ID": item.get("stream_id") or item.get("series_id"),
        "Título": limpar_titulo(item.get("name")),
        "Capa":   url_capa(item.get("stream_icon") or item.get("cover")),
        "Banner": url_banner(str(raw_banner).strip()),
        "Ano":    item.get("year") or "",
        "Gênero": primeiro_genero(item.get("genre")),
        "Tipo":   tipo,
        "Sinopse": item.get("plot") or None,
        "Score":   item.get("rating") or 0,
        **({"Player": item.get("stream_id")} if tipo == "Filme" else {})
    }

# ============================================================
# Ciclo de vida – cria/fecha cliente HTTP
# ============================================================

@app.on_event("startup")
async def startup_event():
    global client
    client = httpx.AsyncClient(http2=True, limits=httpx.Limits(max_connections=100))

@app.on_event("shutdown")
async def shutdown_event():
    await client.aclose()

# ============================================================
# Endpoints
# ============================================================

def paginate(items: List[dict], page: int):
    start = (page - 1) * PAGE_SIZE
    return items[start : start + PAGE_SIZE]

@app.get("/api/Venus/Filmes")
async def get_filmes(page: int = Query(1, ge=1)):
    data = await get_api_data("get_vod_streams")
    if "error" in data:
        raise HTTPException(500, data["error"])

    filmes = [clean_item(i, "Filme") for i in data]
    return JSONResponse(
        {
            "data": paginate(filmes, page),
            "page": page,
            "per_page": PAGE_SIZE,
            "total": len(filmes),
        }
    )

@app.get("/api/Venus/Séries")
async def get_series(page: int = Query(1, ge=1)):
    data = await get_api_data("get_series")
    if "error" in data:
        raise HTTPException(500, data["error"])

    series = [clean_item(i, "Série") for i in data]
    return JSONResponse(
        {
            "data": paginate(series, page),
            "page": page,
            "per_page": PAGE_SIZE,
            "total": len(series),
        }
    )

# ------------------------------------------------------------------
# INFO (Filme & Série) – executam em paralelo para reduzir latência
# ------------------------------------------------------------------

async def _info_filme_raw(id_: str):
    return await get_api_data(f"get_vod_info&vod_id={id_}")

async def _info_serie_raw(id_: str):
    return await get_api_data(f"get_series_info&series_id={id_}")

@app.get("/api/Info/Venus/Filmes")
async def info_filme(id: str = Query(...)):
    dados = await _info_filme_raw(id)
    info = dados.get("info", {}) if isinstance(dados, dict) else {}
    if not info:
        raise HTTPException(500, "Erro ao processar resposta")

    banner_raw = info.get("backdrop_path", [])
    banner = banner_raw[0] if isinstance(banner_raw, list) else banner_raw
    ano = (info.get("release_date") or "")[:4]

    return {
        "ID": id,
        "Título": limpar_titulo(info.get("name")),
        "Capa":   url_capa(info.get("movie_image")),
        "Banner": url_banner(banner),
        "Ano":    ano,
        "Gênero": primeiro_genero(info.get("genre")),
        "Tipo":   "Filme",
        "Sinopse": info.get("plot") or None,
        "Score":   info.get("rating") or 0,
        "Player":  id,
    }

@app.get("/api/Info/Venus/Séries")
async def info_serie(id: str = Query(...)):
    dados = await _info_serie_raw(id)
    info = dados.get("info", {}) if isinstance(dados, dict) else {}
    if not info:
        raise HTTPException(500, "Erro ao processar resposta")

    banner_raw = info.get("backdrop_path", [])
    banner = banner_raw[0] if isinstance(banner_raw, list) else banner_raw
    ano = (info.get("releaseDate") or info.get("release_date") or "")[:4]

    return {
        "ID": id,
        "Título": limpar_titulo(info.get("name")),
        "Capa":   url_capa(info.get("cover")),
        "Banner": url_banner(banner.strip().replace(" ", "")),
        "Ano":    ano,
        "Gênero": primeiro_genero(info.get("genre")),
        "Tipo":   "Série",
        "Sinopse": info.get("plot") or None,
        "Score":   info.get("rating") or 0,
    }

# ------------------------------------------------------------------
# ROTA – LISTAR TEMPORADAS
# ------------------------------------------------------------------
@app.get("/api/Venus/Temporadas")
async def listar_temporadas(id: str = Query(..., description="series_id da série")):
    dados = await _info_serie_raw(id)
    episodios_por_temp = dados.get("episodes", {}) if isinstance(dados, dict) else {}
    if not episodios_por_temp:
        raise HTTPException(500, "Erro ao obter temporadas")

    temporadas = []
    for numero, episodios in sorted(episodios_por_temp.items(), key=lambda x: int(x[0])):
        exemplo = episodios[0] if episodios else {}
        img = url_capa(exemplo.get("info", {}).get("movie_image"))
        temporadas.append(
            {
                "Temporada": numero,
                "Qtd_Episodios": len(episodios),
                "Imagem": img,
                "ID": id,
            }
        )
    return temporadas

# ------------------------------------------------------------------
# ROTA – TODOS OS EPISÓDIOS (achatados)
# ------------------------------------------------------------------
@app.get("/api/Venus/TodosEpisodios")
async def listar_todos_episodios(id: str = Query(..., description="series_id da série")):
    dados = await _info_serie_raw(id)
    episodios_por_temp = dados.get("episodes", {}) if isinstance(dados, dict) else {}
    if not episodios_por_temp:
        raise HTTPException(500, "Erro ao obter episódios")

    todos = []
    for temporada, episodios in sorted(episodios_por_temp.items(), key=lambda x: int(x[0])):
        for ep in sorted(episodios, key=lambda e: e.get("episode_num", 0)):
            titulo_limpo = re.sub(RE_SUFFIX_EP, "", ep.get("title", "")).strip()
            todos.append(
                {
                    "ID": ep.get("id"),
                    "Episodio": ep.get("episode_num"),
                    "Titulo_EP": titulo_limpo,
                    "Capa_EP": url_capa(ep.get("info", {}).get("movie_image")),
                    "Temporada": temporada,
                    "Play": ep.get("id"),
                }
            )
    return todos

# ------------------------------------------------------------------
# ROTA – GÊNEROS ÚNICOS
# ------------------------------------------------------------------
@app.get("/api/Venus/Generos")
async def get_generos_unicos():
    # busca filmes e séries em paralelo
    filmes_raw, series_raw = await asyncio.gather(
        get_api_data("get_vod_streams"),
        get_api_data("get_series"),
    )
    if "error" in filmes_raw or "error" in series_raw:
        raise HTTPException(500, "Erro ao obter dados")

    def primeiro_genero_simples(txt: str) -> str:
        if not txt:
            return ""
        parte = txt.split(",")[0].split("/")[0]
        return parte.strip()

    generos_set = {
        primeiro_genero_simples(i.get("genre", ""))
        for i in filmes_raw + series_raw
        if primeiro_genero_simples(i.get("genre", ""))
    }

    return {"generos": sorted(generos_set)}

# ------------------------------------------------------------------
# ROTA – INTERCALAR FILMES & SÉRIES
# ------------------------------------------------------------------
@app.get("/api/VenusPlay/Todos")
async def all_conteudo_todos():
    filmes_raw, series_raw = await asyncio.gather(
        get_api_data("get_vod_streams"),
        get_api_data("get_series"),
    )
    if "error" in filmes_raw or "error" in series_raw:
        raise HTTPException(500, "Erro ao obter dados")

    filmes  = [clean_item(f, "Filme") for f in filmes_raw]
    series  = [clean_item(s, "Série") for s in series_raw]

    resultado = [v for pair in zip(filmes, series) for v in pair]
    # adiciona sobrantes (se existir)
    maior = filmes if len(filmes) > len(series) else series
    resultado.extend(maior[len(resultado)//2:])

    return {"data": resultado, "total": len(resultado)}

from fastapi import FastAPI, HTTPException, Query
import httpx, asyncio, re, time
from typing import Optional, Dict, Any, Tuple

app = FastAPI()
API_BASE  = "https://hiveos.space/player_api.php"
USERNAME  = "VenusPlay"
PASSWORD  = "659225573"
PAGE_SIZE = 27

# ──────────────────────── CLIENTE GLOBAL ────────────────────────
async_client: httpx.AsyncClient | None = None

@app.on_event("startup")
async def _startup():
    global async_client
    async_client = httpx.AsyncClient(
        timeout = 8.0,
        limits  = httpx.Limits(max_connections=50, max_keepalive_connections=20),
        follow_redirects = True,
    )

@app.on_event("shutdown")
async def _shutdown():
    await async_client.aclose()

# ───────────────────────── CACHE SIMPLES ─────────────────────────
_cache: Dict[Tuple[str, str], Tuple[float, Any]] = {}
def _make_key(endpoint: str, params: str = "") -> Tuple[str, str]:
    return (endpoint, params)

def _get_cache(key: Tuple[str, str], ttl: int = 30):
    if key in _cache:
        ts, data = _cache[key]
        if (time.time() - ts) < ttl:
            return data
        _cache.pop(key, None)          # expira
    return None

def _set_cache(key: Tuple[str, str], data: Any):
    _cache[key] = (time.time(), data)

# ───────────────────── FUNÇÕES UTILITÁRIAS ──────────────────────
re_year  = re.compile(r"\s*\(\d{4}\)$")
re_sufix = re.compile(r"\s*-\s*S\d{2}E\d{2}\s*-\s*Capítulo\s*\d+\s*$", re.I)

def limpar_titulo(txt: Optional[str]) -> str:
    return re_year.sub("", txt.strip()) if txt else ""

def url_banner(path: Optional[str]) -> str:
    return f"https://image.tmdb.org/t/p/w1280{path}" if path and not str(path).startswith("http") else str(path or "")

def url_capa(path: Optional[str]) -> str:
    return f"https://image.tmdb.org/t/p/w600_and_h900_bestv2{path}" if path and not str(path).startswith("http") else str(path or "")

def primeiro_genero(txt: Optional[str]) -> str:
    if not txt: return ""
    return txt.split(",")[0].split("/")[0].strip()

async def fetch(endpoint: str, *, ttl: int = 30) -> Any:
    """GET na API IPTV com cache e retentativa curta."""
    key = _make_key(endpoint)
    if data := _get_cache(key, ttl):
        return data

    url = f"{API_BASE}?username={USERNAME}&password={PASSWORD}&action={endpoint}"
    for _ in range(2):  # 1 retentativa
        try:
            r = await async_client.get(url)
            r.raise_for_status()
            data = r.json()
            _set_cache(key, data)
            return data
        except Exception as exc:
            err = exc
            await asyncio.sleep(0.8)
    return {"error": str(err)}

def clean_item(item: dict, tipo: str) -> dict:
    raw_banner = item.get("backdrop_path")
    if isinstance(raw_banner, list): raw_banner = raw_banner[0] if raw_banner else ""
    if isinstance(raw_banner, str) and "," in raw_banner: raw_banner = raw_banner.split(",")[0]
    if not raw_banner:
        raw_banner = item.get("stream_icon") if tipo == "Filme" else item.get("cover")

    base = {
        "ID"      : item.get("stream_id") or item.get("series_id"),
        "Título"  : limpar_titulo(item.get("name")),
        "Capa"    : url_capa(item.get("stream_icon") or item.get("cover")),
        "Banner"  : url_banner(str(raw_banner).strip()),
        "Ano"     : item.get("year") or "",
        "Gênero"  : primeiro_genero(item.get("genre")),
        "Tipo"    : tipo,
        "Sinopse" : item.get("plot") or None,
        "Score"   : item.get("rating") or 0,
    }
    if tipo == "Filme":
        base["Player"] = item.get("stream_id")
    return base

# ───────────────────────────── ROTAS ─────────────────────────────
@app.get("/api/Venus/Filmes")
async def filmes(page: int = Query(1, ge=1)):
    data   = await fetch("get_vod_streams", ttl=30)
    if "error" in data: raise HTTPException(500, data["error"])
    filmes = [clean_item(i, "Filme") for i in data]
    start, end = (page-1)*PAGE_SIZE, (page)*PAGE_SIZE
    return {"data": filmes[start:end], "page": page, "per_page": PAGE_SIZE, "total": len(filmes)}

@app.get("/api/Venus/Séries")
async def series(page: int = Query(1, ge=1)):
    data   = await fetch("get_series", ttl=30)
    if "error" in data: raise HTTPException(500, data["error"])
    series = [clean_item(i, "Série") for i in data]
    start, end = (page-1)*PAGE_SIZE, (page)*PAGE_SIZE
    return {"data": series[start:end], "page": page, "per_page": PAGE_SIZE, "total": len(series)}

# Info de filmes e séries mantido igual (chamadas pouco frequentes) …

# --------------- GENEROS (filmes + séries) ---------------
@app.get("/api/Venus/Generos")
async def generos():
    filmes, series = await asyncio.gather(fetch("get_vod_streams", ttl=60),
                                          fetch("get_series", ttl=60))
    if "error" in filmes or "error" in series:
        raise HTTPException(500, "Erro ao obter dados")
    gen = {primeiro_genero(i.get("genre","")) for i in (*filmes, *series) if primeiro_genero(i.get("genre",""))}
    return {"generos": sorted(gen)}

# --------------- CATÁLOGO INTERCALADO --------------------
@app.get("/api/VenusPlay/Todos")
async def intercalado():
    filmes_raw = await fetch("get_vod_streams", ttl=30)
    series_raw = await fetch("get_series", ttl=30)
    if "error" in filmes_raw or "error" in series_raw:
        raise HTTPException(500, "Erro ao obter dados")
    filmes  = [clean_item(f, "Filme") for f in filmes_raw]
    series  = [clean_item(s, "Série") for s in series_raw]
    mix     = [x for pair in zip(filmes, series) for x in pair]
    # se listas de tamanhos diferentes:
    mix.extend(filmes[len(series):] if len(filmes) > len(series) else series[len(filmes):])
    return {"data": mix, "total": len(mix)}

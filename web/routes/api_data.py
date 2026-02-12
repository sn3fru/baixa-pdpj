"""API de dados: upload, individuos, processos, devedores, arquivos."""

import os
import io
import json
import glob
import shutil
import zipfile
import threading
from datetime import datetime

import re
import html as html_mod

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from config import Config

router = APIRouter(tags=["data"])


# ============================================================================
# Cache de DataFrames (evita reler Excel a cada request)
# ============================================================================

class _DFCache:
    """Cache thread-safe de DataFrames lidos de Excel.
    Invalida automaticamente se o arquivo mudou (mtime)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cache: dict = {}   # key -> (mtime, df)

    def get(self, filepath: str) -> pd.DataFrame:
        mtime = os.path.getmtime(filepath) if os.path.isfile(filepath) else 0
        with self._lock:
            if filepath in self._cache:
                cached_mtime, cached_df = self._cache[filepath]
                if cached_mtime == mtime:
                    return cached_df
        # Leitura fora do lock (pode ser lenta)
        df = pd.read_excel(filepath, dtype=str)
        df = df.fillna("")
        with self._lock:
            self._cache[filepath] = (mtime, df)
        return df

    def invalidate(self, filepath: str = None):
        with self._lock:
            if filepath:
                self._cache.pop(filepath, None)
            else:
                self._cache.clear()


_df_cache = _DFCache()


def _paginate_df(df: pd.DataFrame, page: int, size: int,
                 sort_field: str = None, sort_dir: str = "asc",
                 filters: dict = None) -> dict:
    """Aplica filtro, ordenacao e paginacao server-side a um DataFrame.

    Returns dict no formato que Tabulator espera para paginacao remota:
      { "last_page": N, "data": [...] }
    Tambem retorna "total_filtered" e "total" para stats.
    """
    total = len(df)

    # 1. Filtros (header filters do Tabulator)
    if filters:
        for col, value in filters.items():
            if col in df.columns and value:
                val = str(value).lower()
                mask = df[col].astype(str).str.lower().str.contains(val, na=False)
                df = df[mask]

    total_filtered = len(df)

    # 2. Ordenacao
    if sort_field and sort_field in df.columns:
        ascending = sort_dir != "desc"
        # Tenta converter para numerico para ordenar corretamente
        try:
            numeric = pd.to_numeric(df[sort_field], errors='coerce')
            if numeric.notna().sum() > total_filtered * 0.5:
                # Maioria e numero, ordena numericamente
                df = df.assign(_sort_key=numeric).sort_values(
                    "_sort_key", ascending=ascending, na_position="last"
                ).drop(columns=["_sort_key"])
            else:
                df = df.sort_values(sort_field, ascending=ascending)
        except Exception:
            df = df.sort_values(sort_field, ascending=ascending)

    # 3. Paginacao
    last_page = max(1, -(-total_filtered // size))  # ceil division
    page = max(1, min(page, last_page))
    start = (page - 1) * size
    end = start + size
    page_data = df.iloc[start:end]

    return {
        "last_page": last_page,
        "data": page_data.to_dict(orient="records"),
        "total": total,
        "total_filtered": total_filtered,
    }

REQUIRED_COLUMNS = ["nr_documento"]
OPTIONAL_COLUMNS = ["posicao", "nome_estoque", "tp_documento"]
ALL_KNOWN_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS


# ============================================================================
# Upload
# ============================================================================

@router.post("/upload")
async def upload_file(arquivo: UploadFile = File(...)):
    """Recebe planilha, valida colunas, salva, retorna preview."""
    cfg = Config.from_env()
    os.makedirs(cfg.output_dir, exist_ok=True)

    # Salva arquivo temporario
    ext = os.path.splitext(arquivo.filename)[1].lower()
    if ext not in (".xlsx", ".xls"):
        return {"error": "Formato invalido. Aceito: .xlsx, .xls"}

    # Salva arquivo original temporario para leitura
    temp_name = f"_temp_upload{ext}"
    project_root = os.path.abspath(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".."))
    temp_path = os.path.join(project_root, temp_name)

    content = await arquivo.read()
    with open(temp_path, "wb") as f:
        f.write(content)

    # Le e valida
    try:
        if ext == ".xls":
            df = pd.read_excel(temp_path, dtype=str, engine="xlrd")
        else:
            df = pd.read_excel(temp_path, dtype=str)
    except Exception as e:
        os.remove(temp_path)
        return {"error": f"Erro ao ler arquivo: {e}"}
    finally:
        # Remove temp independente do resultado
        if os.path.isfile(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

    cols = [c.strip() for c in df.columns]
    df.columns = cols

    # Validacao
    issues = []
    has_doc = any(c in cols for c in ["nr_documento", "documento", "cpf", "cnpj", "cpf_cnpj"])
    has_nome = any(c in cols for c in ["nome_estoque", "nome", "nome_parte"])
    if not has_doc and not has_nome:
        issues.append("Planilha precisa ter pelo menos uma coluna de documento (nr_documento) ou nome (nome_estoque).")

    # Normaliza nomes de colunas conhecidas
    rename_map = {}
    for c in cols:
        cl = c.lower().strip()
        if cl in ("documento", "cpf", "cnpj", "cpf_cnpj") and "nr_documento" not in cols:
            rename_map[c] = "nr_documento"
        if cl in ("nome", "nome_parte") and "nome_estoque" not in cols:
            rename_map[c] = "nome_estoque"
    if rename_map:
        df = df.rename(columns=rename_map)

    # Auto-gera posicao se nao existir
    if "posicao" not in df.columns:
        df.insert(0, "posicao", range(1, len(df) + 1))

    # Salva versao normalizada SEMPRE como .xlsx (compativel com openpyxl)
    save_name = f"entrada_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    save_path = os.path.join(project_root, save_name)
    df.to_excel(save_path, index=False, engine="openpyxl")

    # Atualiza .env para apontar para novo arquivo
    _update_env("INPUT_FILE", save_name)

    preview = df.head(50).fillna("").to_dict(orient="records")
    return {
        "status": "ok",
        "filename": save_name,
        "path": save_path,
        "rows": len(df),
        "columns": list(df.columns),
        "issues": issues,
        "preview": preview,
    }


@router.get("/upload/preview")
async def preview_input():
    """Retorna preview da planilha de entrada atual."""
    cfg = Config.from_env()
    project_root = os.path.abspath(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".."))
    path = cfg.input_file

    # Tenta caminho absoluto, depois relativo ao projeto
    if not os.path.isfile(path):
        alt = os.path.join(project_root, path)
        if os.path.isfile(alt):
            path = alt
        else:
            return {"error": f"Arquivo de entrada nao encontrado: {cfg.input_file}",
                    "path": cfg.input_file}

    # Tenta ler com openpyxl primeiro, fallback xlrd
    df = None
    errors = []
    for engine in ("openpyxl", "xlrd"):
        try:
            df = pd.read_excel(path, dtype=str, engine=engine)
            break
        except Exception as e:
            errors.append(f"{engine}: {e}")
    if df is None:
        return {"error": f"Erro ao ler arquivo: {'; '.join(errors)}"}

    return {
        "filename": os.path.basename(path),
        "rows": len(df),
        "columns": list(df.columns),
        "data": df.fillna("").to_dict(orient="records"),
    }


# ============================================================================
# Individuos
# ============================================================================

@router.get("/individuos")
async def list_individuos():
    """Retorna lista de individuos processados."""
    cfg = Config.from_env()
    output_dir = cfg.output_dir
    if not os.path.isdir(output_dir):
        return []

    result = []
    for name in sorted(os.listdir(output_dir)):
        d = os.path.join(output_dir, name)
        meta_path = os.path.join(d, "metadata.json")
        if not os.path.isdir(d) or not os.path.isfile(meta_path):
            continue
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            # Conta arquivos
            n_pages = n_dets = 0
            for root, _, files in os.walk(d):
                for fn in files:
                    if fn.startswith("page_") and fn.endswith(".json"):
                        n_pages += 1
                    elif fn.endswith(".json") and fn not in ("metadata.json", "processos_unicos.json"):
                        n_dets += 1
            meta["_pages"] = n_pages
            meta["_detalhes"] = n_dets
            result.append(meta)
        except Exception:
            result.append({"id": name, "erro": "falha ao ler metadata"})
    return result


@router.get("/individuos/{id_ind}")
async def get_individuo(id_ind: str):
    """Retorna dados completos de um individuo."""
    cfg = Config.from_env()
    ind_dir = os.path.join(cfg.output_dir, id_ind)
    if not os.path.isdir(ind_dir):
        return {"error": "Individuo nao encontrado."}

    data = {"id": id_ind, "metadata": {}, "processos_unicos": {}, "arquivos": []}

    meta_path = os.path.join(ind_dir, "metadata.json")
    if os.path.isfile(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            data["metadata"] = json.load(f)

    pu_path = os.path.join(ind_dir, "processos_unicos.json")
    if os.path.isfile(pu_path):
        with open(pu_path, "r", encoding="utf-8") as f:
            data["processos_unicos"] = json.load(f)

    # Arvore de arquivos
    for root, dirs, files in os.walk(ind_dir):
        rel = os.path.relpath(root, ind_dir)
        for fn in sorted(files):
            fpath = os.path.join(rel, fn) if rel != "." else fn
            data["arquivos"].append({
                "path": fpath.replace("\\", "/"),
                "size": os.path.getsize(os.path.join(root, fn)),
                "is_json": fn.endswith(".json"),
            })
    return data


# ============================================================================
# Processos (tabela S2) — paginacao server-side
# ============================================================================

def _find_latest_file(output_dir: str, pattern_name: str) -> str | None:
    pattern = os.path.join(output_dir, pattern_name)
    files = sorted(glob.glob(pattern), reverse=True)
    return files[0] if files else None


@router.get("/processos/meta")
async def processos_meta():
    """Retorna metadados (colunas, total, arquivo) sem enviar dados.
    Chamado uma vez pelo frontend para configurar a tabela."""
    cfg = Config.from_env()
    filepath = _find_latest_file(cfg.output_dir, "saida_processos_consolidados_*.xlsx")
    if not filepath:
        return {"columns": [], "file": None, "total": 0}

    df = _df_cache.get(filepath)
    return {
        "columns": list(df.columns),
        "file": os.path.basename(filepath),
        "total": len(df),
    }


@router.get("/processos")
async def list_processos(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=10, le=500),
    sort: str = Query(None),
    dir: str = Query("asc"),
    # Filtros vem como query params: filter_<coluna>=valor
):
    """Paginacao server-side para Tabulator."""
    cfg = Config.from_env()
    filepath = _find_latest_file(cfg.output_dir, "saida_processos_consolidados_*.xlsx")
    if not filepath:
        return {"last_page": 1, "data": []}

    df = _df_cache.get(filepath)

    # Extrai filtros da query string (filter_Processo=xyz)
    # Tabulator envia: filter[0][field]=X&filter[0][value]=Y
    # Mas nosso frontend vai enviar formato simplificado
    filters = {}
    # Compatibilidade com ambos formatos
    return _paginate_df(df, page, size, sort, dir, filters)


@router.get("/processos/filter")
async def filter_processos(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=10, le=500),
    sort: str = Query(None),
    dir: str = Query("asc"),
    q: str = Query("{}"),  # JSON com filtros {coluna: valor}
):
    """Paginacao + filtro server-side. Frontend envia filtros como JSON no param q."""
    cfg = Config.from_env()
    filepath = _find_latest_file(cfg.output_dir, "saida_processos_consolidados_*.xlsx")
    if not filepath:
        return {"last_page": 1, "data": [], "total": 0, "total_filtered": 0}

    df = _df_cache.get(filepath)
    try:
        filters = json.loads(q) if q and q != "{}" else {}
    except Exception:
        filters = {}
    return _paginate_df(df, page, size, sort, dir, filters)


# ============================================================================
# Devedores (tabela S3) — paginacao server-side
# ============================================================================

@router.get("/devedores/meta")
async def devedores_meta():
    """Metadados da tabela de devedores."""
    cfg = Config.from_env()
    filepath = _find_latest_file(cfg.output_dir, "visao_devedor_*.xlsx")
    if not filepath:
        return {"columns": [], "file": None, "total": 0}

    df = _df_cache.get(filepath)
    return {
        "columns": list(df.columns),
        "file": os.path.basename(filepath),
        "total": len(df),
    }


@router.get("/devedores")
async def list_devedores(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=10, le=500),
    sort: str = Query(None),
    dir: str = Query("asc"),
):
    """Paginacao server-side para devedores."""
    cfg = Config.from_env()
    filepath = _find_latest_file(cfg.output_dir, "visao_devedor_*.xlsx")
    if not filepath:
        return {"last_page": 1, "data": []}

    df = _df_cache.get(filepath)
    return _paginate_df(df, page, size, sort, dir)


@router.get("/devedores/filter")
async def filter_devedores(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=10, le=500),
    sort: str = Query(None),
    dir: str = Query("asc"),
    q: str = Query("{}"),
):
    """Paginacao + filtro server-side para devedores."""
    cfg = Config.from_env()
    filepath = _find_latest_file(cfg.output_dir, "visao_devedor_*.xlsx")
    if not filepath:
        return {"last_page": 1, "data": [], "total": 0, "total_filtered": 0}

    df = _df_cache.get(filepath)
    try:
        filters = json.loads(q) if q and q != "{}" else {}
    except Exception:
        filters = {}
    return _paginate_df(df, page, size, sort, dir, filters)


# ============================================================================
# Dashboard stats
# ============================================================================

@router.get("/stats")
async def get_stats():
    """Retorna estatisticas gerais para o dashboard."""
    cfg = Config.from_env()
    output_dir = cfg.output_dir
    stats = {
        "individuos": 0, "processos": 0, "detalhes": 0,
        "pages": 0, "devedores": 0,
        "exec_fiscal": 0, "ativos": 0, "extintos": 0,
        "origens": {"por_documento": 0, "por_nome": 0, "por_filial": 0},
    }

    if not os.path.isdir(output_dir):
        return stats

    # Conta individuos
    for name in os.listdir(output_dir):
        d = os.path.join(output_dir, name)
        if os.path.isdir(d) and os.path.isfile(os.path.join(d, "metadata.json")):
            stats["individuos"] += 1

    # Le S2 para processos
    filepath_s2 = _find_latest_file(output_dir, "saida_processos_consolidados_*.xlsx")
    if filepath_s2:
        try:
            df = _df_cache.get(filepath_s2)
            stats["processos"] = len(df)
            if "Flag Extinto" in df.columns:
                stats["ativos"] = int((df["Flag Extinto"].astype(str) == "0").sum())
                stats["extintos"] = int((df["Flag Extinto"].astype(str) == "1").sum())
            if "Classe" in df.columns:
                stats["exec_fiscal"] = int(df["Classe"].str.contains("1116", na=False).sum())
            if "Origens" in df.columns:
                for _, row in df.iterrows():
                    ori = str(row.get("Origens", ""))
                    if "por_documento" in ori:
                        stats["origens"]["por_documento"] += 1
                    if "por_nome" in ori:
                        stats["origens"]["por_nome"] += 1
                    if "por_filial" in ori:
                        stats["origens"]["por_filial"] += 1
        except Exception:
            pass

    # Le S3 para devedores
    filepath_s3 = _find_latest_file(output_dir, "visao_devedor_*.xlsx")
    if filepath_s3:
        try:
            df3 = _df_cache.get(filepath_s3)
            stats["devedores"] = len(df3)
        except Exception:
            pass

    return stats


# ============================================================================
# Arquivos (file browser)
# ============================================================================

@router.get("/arquivos")
async def list_arquivos(path: str = Query("", alias="path")):
    """Lista conteudo de um diretorio dentro de output_dir."""
    cfg = Config.from_env()
    base = os.path.abspath(cfg.output_dir)
    target = os.path.abspath(os.path.join(base, path))

    # Security check
    if not target.startswith(base):
        return {"error": "Acesso negado."}

    if not os.path.exists(target):
        return {"error": "Caminho nao encontrado."}

    if os.path.isfile(target):
        if target.endswith(".json"):
            with open(target, "r", encoding="utf-8") as f:
                try:
                    return {"type": "json", "path": path, "content": json.load(f)}
                except Exception:
                    return {"type": "text", "path": path, "content": f.read()}
        if target.endswith((".xlsx", ".xls")):
            return FileResponse(target, filename=os.path.basename(target))
        return {"type": "file", "path": path, "size": os.path.getsize(target)}

    # Diretorio
    items = []
    for name in sorted(os.listdir(target)):
        full = os.path.join(target, name)
        rel = os.path.join(path, name) if path else name
        is_dir = os.path.isdir(full)
        items.append({
            "name": name,
            "path": rel.replace("\\", "/"),
            "is_dir": is_dir,
            "size": os.path.getsize(full) if not is_dir else 0,
            "children": len(os.listdir(full)) if is_dir else 0,
        })
    return {"type": "directory", "path": path, "items": items}


@router.get("/arquivos/download")
async def download_file(path: str = Query(...)):
    """Download de arquivo."""
    cfg = Config.from_env()
    base = os.path.abspath(cfg.output_dir)
    target = os.path.abspath(os.path.join(base, path))
    if not target.startswith(base) or not os.path.isfile(target):
        return {"error": "Arquivo nao encontrado."}
    return FileResponse(target, filename=os.path.basename(target))


# ============================================================================
# Documentacao (Markdown -> HTML simples)
# ============================================================================

@router.get("/docs", response_class=HTMLResponse)
async def get_docs():
    """Le DOCUMENTACAO_TECNICA.md e retorna como HTML."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    md_path = os.path.join(project_root, "DOCUMENTACAO_TECNICA.md")
    if not os.path.isfile(md_path):
        return HTMLResponse("<p class='text-red-400'>DOCUMENTACAO_TECNICA.md nao encontrado.</p>")

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    html_content = _markdown_to_html(md_text)
    return HTMLResponse(html_content)


def _markdown_to_html(md: str) -> str:
    """Conversor markdown -> HTML minimalista (sem dependencias externas).
    Suporta headers, code blocks, tabelas, listas, paragrafos, negrito, italico, code inline."""
    lines = md.split("\n")
    out = []
    in_code = False
    in_table = False
    in_list = False

    for line in lines:
        # Code blocks
        if line.strip().startswith("```"):
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                lang = line.strip()[3:].strip()
                out.append(f'<pre class="bg-gray-800 rounded p-3 overflow-x-auto my-3 text-xs"><code class="text-gray-300">')
                in_code = True
            continue
        if in_code:
            out.append(html_mod.escape(line))
            continue

        stripped = line.strip()

        # Empty line
        if not stripped:
            if in_table:
                out.append("</tbody></table></div>")
                in_table = False
            if in_list:
                out.append("</ul>")
                in_list = False
            continue

        # Headers
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            level = min(level, 6)
            text = stripped[level:].strip()
            sizes = {1: "text-xl font-bold mt-8 mb-3 text-gray-100",
                     2: "text-lg font-bold mt-6 mb-2 text-gray-200",
                     3: "text-base font-semibold mt-4 mb-2 text-gray-300",
                     4: "text-sm font-semibold mt-3 mb-1 text-gray-400",
                     5: "text-sm font-medium text-gray-400",
                     6: "text-xs font-medium text-gray-500"}
            cls = sizes.get(level, sizes[6])
            out.append(f'<h{level} class="{cls}">{_inline(text)}</h{level}>')
            continue

        # Horizontal rule
        if stripped in ("---", "***", "___"):
            out.append('<hr class="border-gray-800 my-4">')
            continue

        # Table
        if "|" in stripped and stripped.startswith("|"):
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            # Separator row
            if all(c.replace("-", "").replace(":", "") == "" for c in cells):
                continue
            if not in_table:
                out.append('<div class="overflow-x-auto my-3"><table class="w-full text-sm">')
                out.append('<thead><tr class="border-b border-gray-700 text-gray-400">')
                for c in cells:
                    out.append(f'<th class="text-left py-1.5 px-2 text-xs">{_inline(c)}</th>')
                out.append("</tr></thead><tbody>")
                in_table = True
            else:
                out.append('<tr class="border-b border-gray-800/50">')
                for c in cells:
                    out.append(f'<td class="py-1 px-2 text-xs text-gray-400">{_inline(c)}</td>')
                out.append("</tr>")
            continue

        # List items
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                out.append('<ul class="list-disc list-inside space-y-1 my-2 text-sm text-gray-400">')
                in_list = True
            text = stripped[2:]
            out.append(f"<li>{_inline(text)}</li>")
            continue
        if re.match(r"^\d+\.\s", stripped):
            if not in_list:
                out.append('<ul class="list-decimal list-inside space-y-1 my-2 text-sm text-gray-400">')
                in_list = True
            text = re.sub(r"^\d+\.\s", "", stripped)
            out.append(f"<li>{_inline(text)}</li>")
            continue

        if in_list:
            out.append("</ul>")
            in_list = False

        # Paragraph
        out.append(f'<p class="text-sm text-gray-400 my-1.5">{_inline(stripped)}</p>')

    if in_code:
        out.append("</code></pre>")
    if in_table:
        out.append("</tbody></table></div>")
    if in_list:
        out.append("</ul>")

    return "\n".join(out)


def _inline(text: str) -> str:
    """Processa formatacao inline: negrito, italico, code, links."""
    text = html_mod.escape(text)
    # Code inline
    text = re.sub(r'`([^`]+)`', r'<code class="text-blue-400 bg-gray-800 px-1 rounded text-xs">\1</code>', text)
    # Bold
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong class="text-gray-200">\1</strong>', text)
    # Italic
    text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)
    # Links
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" class="text-blue-400 underline">\1</a>', text)
    return text


# ============================================================================
# Download ZIP de todos os resultados
# ============================================================================

@router.get("/download-zip")
async def download_zip():
    """Gera um ZIP com todos os outputs (JSONs, Excels, pastas de individuos)
    para download. Streama direto sem salvar em disco.

    Importante para Heroku: filesystem efemero perde dados no restart.
    Este endpoint permite salvar tudo localmente antes que isso aconteca."""
    cfg = Config.from_env()
    output_dir = os.path.abspath(cfg.output_dir)

    if not os.path.isdir(output_dir):
        return {"error": "Nenhum dado encontrado. Execute o pipeline primeiro."}

    # Coleta também os Excels de resumo na raiz do projeto
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def _generate_zip():
        """Generator que streama o ZIP em chunks."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            # 1. Toda a pasta outputs/
            for root, dirs, files in os.walk(output_dir):
                for fn in files:
                    full_path = os.path.join(root, fn)
                    arcname = os.path.join("outputs", os.path.relpath(full_path, output_dir))
                    arcname = arcname.replace("\\", "/")
                    try:
                        zf.write(full_path, arcname)
                    except Exception:
                        pass  # Ignora arquivos bloqueados

            # 2. Excels de resumo na raiz (saida_*, visao_devedor_*, entrada_*)
            for pattern in ["saida_*.xlsx", "visao_devedor_*.xlsx", "entrada_*.xlsx"]:
                for f in glob.glob(os.path.join(project_root, pattern)):
                    arcname = os.path.basename(f)
                    try:
                        zf.write(f, arcname)
                    except Exception:
                        pass

            # 3. Caches uteis
            for cache_name in ["selic_cache.json", "processos_404.json",
                               "filiais_inexistentes.json", "log_erros_detalhado.json"]:
                cache_path = os.path.join(project_root, cache_name)
                if os.path.isfile(cache_path):
                    try:
                        zf.write(cache_path, cache_name)
                    except Exception:
                        pass

        buffer.seek(0)
        yield buffer.read()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"devedor360_resultados_{timestamp}.zip"

    return StreamingResponse(
        _generate_zip(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/download-zip/info")
async def download_zip_info():
    """Retorna informacoes sobre o que seria incluido no ZIP (tamanho, arquivos)."""
    cfg = Config.from_env()
    output_dir = os.path.abspath(cfg.output_dir)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    if not os.path.isdir(output_dir):
        return {"exists": False, "files": 0, "size_bytes": 0}

    total_files = 0
    total_size = 0

    for root, dirs, files in os.walk(output_dir):
        for fn in files:
            total_files += 1
            total_size += os.path.getsize(os.path.join(root, fn))

    for pattern in ["saida_*.xlsx", "visao_devedor_*.xlsx", "entrada_*.xlsx"]:
        for f in glob.glob(os.path.join(project_root, pattern)):
            total_files += 1
            total_size += os.path.getsize(f)

    return {
        "exists": True,
        "files": total_files,
        "size_bytes": total_size,
        "size_mb": round(total_size / 1024 / 1024, 1),
    }


# ============================================================================
# Keep-alive / Health check (previne hibernacao no Heroku)
# ============================================================================

@router.get("/ping")
async def ping():
    """Health check simples. O frontend faz polling desse endpoint
    enquanto o pipeline roda para manter o dyno Heroku acordado."""
    from web.state import app_state
    return {
        "status": "ok",
        "running": app_state.is_running(),
        "ts": datetime.now().isoformat(),
    }


# ============================================================================
# Helpers
# ============================================================================

def _update_env(key: str, value: str):
    """Atualiza uma chave no .env."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "..", ".env")
    env_path = os.path.abspath(env_path)
    lines = []
    if os.path.isfile(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    found = False
    new_lines = []
    for line in lines:
        if line.strip().startswith(key + "="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}\n")
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

import os
import io
import math
import datetime
import glob
import json
import logging
import re
import unicodedata
from collections import defaultdict
from enum import Enum
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
import geopandas as gpd
import pandas as pd

from database import engine, get_db, Base
from models import Ponto
from routers.top_clientes import router as top_clientes_router
from routers.db_viewer import router as db_viewer_router

logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB

Base.metadata.create_all(bind=engine)


def ensure_database_columns():
    """Add new SQLite columns if the table schema is older than the model."""
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "volume.db"))
    if not os.path.exists(db_path):
        return
    with engine.connect() as conn:
        existing = {row['name'] for row in conn.execute(text("PRAGMA table_info(pontos)")).mappings()}
        new_columns = [
            ("qtd_eco_totais", "FLOAT"),
            ("qtd_eco_res", "FLOAT"),
            ("qtd_eco_com", "FLOAT"),
            ("qtd_eco_ind", "FLOAT"),
            ("qtd_eco_out", "FLOAT"),
            ("qtd_eco_pub", "FLOAT"),
            ("volume_01", "FLOAT"),
            ("volume_02", "FLOAT"),
            ("volume_03", "FLOAT"),
            ("volume_04", "FLOAT"),
            ("volume_05", "FLOAT"),
            ("volume_06", "FLOAT"),
            ("volume_07", "FLOAT"),
            ("volume_08", "FLOAT"),
            ("volume_09", "FLOAT"),
            ("volume_10", "FLOAT"),
            ("volume_11", "FLOAT"),
            ("volume_12", "FLOAT"),
            ("volume_total", "FLOAT"),
            ("deriva_faturar", "FLOAT"),
            ("bairro", "VARCHAR"),
        ]
        for name, col_type in new_columns:
            if name not in existing:
                conn.execute(text(f"ALTER TABLE pontos ADD COLUMN {name} {col_type}"))

ensure_database_columns()

app = FastAPI(title="Volume Platform API", version="1.0.0")
app.include_router(top_clientes_router)
app.include_router(db_viewer_router)

from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Erro interno do servidor. Consulte os logs para detalhes."})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
STATIC_DIR = os.path.join(FRONTEND_DIR, "static")
TEMPLATES_DIR = os.path.join(FRONTEND_DIR, "templates")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# GIS / shapefile folder
GIS_DIR = os.path.join(os.path.dirname(__file__), "ArcGis")


def slugify_layer_name(name: str) -> str:
    normalized = unicodedata.normalize('NFKD', name)
    normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    normalized = re.sub(r'[^A-Za-z0-9]+', '_', normalized)
    return normalized.strip('_') or name


def get_gis_layers():
    if not os.path.isdir(GIS_DIR):
        return []
    layer_files = sorted(glob.glob(os.path.join(GIS_DIR, '*.shp')))
    seen = set()
    layers = []
    for path in layer_files:
        title = os.path.splitext(os.path.basename(path))[0]
        layer_id = slugify_layer_name(title)
        if layer_id in seen:
            suffix = 1
            while f"{layer_id}_{suffix}" in seen:
                suffix += 1
            layer_id = f"{layer_id}_{suffix}"
        seen.add(layer_id)
        layers.append({
            'id': layer_id,
            'title': title,
            'filename': os.path.basename(path),
        })
    return layers


def find_gis_layer_path(layer_id: str) -> str:
    for info in get_gis_layers():
        if info['id'] == layer_id:
            return os.path.join(GIS_DIR, info['filename'])
    raise HTTPException(status_code=404, detail=f"Layer GIS '{layer_id}' não encontrada")


# Column name normalization mapping
# After normalize_col(), the Excel headers become these keys:
COLUMN_MAP = {
    # Identification
    "NUM_LIGACAO": "num_ligacao",
    "NOM_CLIENTE": "nom_cliente",
    "CATEGORIA": "categoria",
    "COD_GRUPO": "cod_grupo",
    "COD_GRUPО": "cod_grupo",  # alternate casing
    "NUM_MEDIDOR": "num_medidor",
    "TIPO_FATURAMENTO": "tipo_faturamento",
    "CIDADE": "cidade",
    "BAIRRO": "bairro",
    "MACRO": "macro",
    "MICRO": "micro",
    "REFERENCIA": "referencia",
    # Situation
    "SIT_LIG": "sit_ligacao",
    "SIT_LIGACAO": "sit_ligacao",
    # Coordinates
    "COD_LATITUDE": "cod_latitude",
    "LATITUDE": "cod_latitude",
    "LAT": "cod_latitude",
    "COD_LONGITUDE": "cod_longitude",
    "LONGITUDE": "cod_longitude",
    "LNG": "cod_longitude",
    "LON": "cod_longitude",
    # Grand consumer — actual column: IsGrandTotalRowTotal
    "ISGRANDTOTALROWTOTAL": "is_grande",
    "ISGRANDECONSUMIDOR": "is_grande",
    "ISGRANDE": "is_grande",
    # Financials — actual column: SumVALOR
    "SUMVALOR": "sum_valor",
    "SUM_VALOR": "sum_valor",
    # Valores diretos — actual: Valor_Diretas_Agua / Valor_Diretas_Esgoto
    "VALOR_DIRETAS_AGUA": "valor_d1",
    "VALOR_DIRETAS_ESGOTO": "valor_d2",
    "VALOR_D1": "valor_d1",
    "VALOR_D2": "valor_d2",
    # Valores indiretos — actual: Valor_Indiretas__Esgoto / Valor_Indiretas_Água
    "VALOR_INDIRETAS__ESGOTO": "valor_in1",
    "VALOR_INDIRETAS_ESGOTO": "valor_in1",
    "VALOR_INDIRETAS_AGUA": "valor_in2",
    "VALOR_INDIRETAS__AGUA": "valor_in2",
    "VALOR_IN1": "valor_in1",
    "VALOR_IN2": "valor_in2",
    # Abatimentos — actual: Valor_Abatimentos
    "VALOR_ABATIMENTOS": "valor_a",
    "VALOR_A": "valor_a",
    # Economias — actual: Qtd_Economias_Fat_Água / Qtd_Economias_Fat_Esgoto
    "QTD_ECONOMIAS_FAT_AGUA": "qtd_eco1",
    "QTD_ECONOMIAS_FAT_AGUAS": "qtd_eco1",
    "QTD_ECONOMIAS_FAT_ESGOTO": "qtd_eco2",
    "QTD_ECO1": "qtd_eco1",
    "QTD_ECO2": "qtd_eco2",
    "ECO_TOTAIS": "qtd_eco_totais",
    "SUMQTD_ECO_RES": "qtd_eco_res",
    "SUMQTD_ECO_COM": "qtd_eco_com",
    "SUMQTD_ECO_IND": "qtd_eco_ind",
    "SUMQTD_ECO_OUT": "qtd_eco_out",
    "SUMQTD_ECO_PUB": "qtd_eco_pub",
    # Volume — actual: Vol_Fat__Águas_Fat_
    "VOL_FAT__AGUAS_FAT_": "vol_fat",
    "VOL_FAT__AGUAS_FAT": "vol_fat",
    "VOL_FAT": "vol_fat",
    "VOLUME": "volume_total",
    "VOLUME_01_JA": "volume_01",
    "VOLUME_02_FE": "volume_02",
    "DERIVA_FATURAR": "deriva_faturar",
    "DEVERIA_FATURAR": "deriva_faturar",
    # GC filter (column: GC, values "SIM" / "NÃO")
    "GC": "gc",
    "GRANDE_CONSUMIDOR": "gc",
    # Rota
    "ROTA": "rota",
}


def normalize_col(name: str) -> str:
    """Normalize column name: uppercase, replace spaces and punctuation with underscores."""
    normalized = unicodedata.normalize("NFD", str(name))
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    normalized = normalized.upper().strip()
    normalized = re.sub(r"[^A-Z0-9]+", "_", normalized)
    return normalized.strip("_")


@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = os.path.join(TEMPLATES_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.post("/api/upload")
async def upload_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Arquivo deve ser .xlsx ou .xls")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"Arquivo muito grande. Limite: {MAX_UPLOAD_SIZE // (1024*1024)} MB")
    try:
        # dtype=object evita que pandas converta automaticamente datas/números
        df = pd.read_excel(io.BytesIO(contents), dtype=object)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler Excel: {str(e)}")

    # Normalize column names (remove accents, uppercase, spaces→_)
    original_cols = list(df.columns)
    df.columns = [normalize_col(c) for c in df.columns]
    normalized_cols = list(df.columns)

    # Map normalized names to model fields, skip duplicates
    rename_map = {}
    already_mapped = set()
    for col in normalized_cols:
        target = COLUMN_MAP.get(col)
        if target and target not in already_mapped:
            rename_map[col] = target
            already_mapped.add(target)

    # Fallback mapping for month-style volume columns not explicitly listed
    for col in normalized_cols:
        if col in rename_map:
            continue
        month_match = re.match(r"^VOLUME_(\d{1,2})(?:_.*)?$", col)
        if month_match:
            target = f"volume_{int(month_match.group(1)):02d}"
            if target not in already_mapped:
                rename_map[col] = target
                already_mapped.add(target)

    df = df.rename(columns=rename_map)

    # Coerce numeric columns to float (they come as object/str with dtype=object)
    NUMERIC_FIELDS = [
        'cod_latitude', 'cod_longitude', 'sum_valor',
        'valor_d1', 'valor_d2', 'valor_in1', 'valor_in2', 'valor_a',
        'qtd_eco1', 'qtd_eco2', 'qtd_eco_totais', 'qtd_eco_res', 'qtd_eco_com',
        'qtd_eco_ind', 'qtd_eco_out', 'qtd_eco_pub',
        'vol_fat', 'volume_total', 'volume_01', 'volume_02',
        'volume_03', 'volume_04', 'volume_05', 'volume_06', 'volume_07',
        'volume_08', 'volume_09', 'volume_10', 'volume_11', 'volume_12',
        'deriva_faturar',
    ]
    for field in NUMERIC_FIELDS:
        if field in df.columns:
            df[field] = pd.to_numeric(df[field], errors='coerce')

    # Clear existing data (fast bulk delete)
    try:
        db.execute(text("DELETE FROM pontos"))
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao limpar banco: {str(e)}")

    # Insert rows efficiently via SQLAlchemy Core
    model_fields = {c.name for c in Ponto.__table__.columns} - {"id"}

    def safe_val(val):
        """Convert any pandas/numpy value to a SQLite-safe Python native type."""
        if val is None:
            return None
        # Handle numpy/pandas NA types
        try:
            if pd.isna(val):
                return None
        except (TypeError, ValueError):
            pass
        # Convert numpy scalar to Python native
        if hasattr(val, 'item'):
            try:
                val = val.item()
            except Exception:
                pass
        # Convert pandas Timestamp / datetime to string
        if isinstance(val, (pd.Timestamp, datetime.datetime, datetime.date)):
            return str(val)
        # Convert float: reject inf / -inf
        if isinstance(val, float):
            if math.isinf(val) or math.isnan(val):
                return None
        return val

    try:
        records = []
        for _, row in df.iterrows():
            data = {}
            for field in model_fields:
                val = row[field] if field in row.index else None
                data[field] = safe_val(val)
            records.append(data)

        if records:
            db.execute(Ponto.__table__.insert(), records)
            db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("Error inserting upload data")
        raise HTTPException(status_code=500, detail=f"Erro ao inserir dados: {str(e)}")

    # Report unmapped columns for debugging
    unmapped = [normalized_cols[i] for i, orig in enumerate(normalized_cols)
                if normalized_cols[i] not in rename_map and normalized_cols[i] not in model_fields]

    return {
        "message": f"{len(records)} registros importados com sucesso.",
        "total": len(records),
        "colunas_mapeadas": list(rename_map.keys()),
        "colunas_nao_mapeadas": unmapped,
    }


@app.post("/api/diagnostico")
async def diagnostico_excel(file: UploadFile = File(...)):
    """Retorna as colunas detectadas no Excel sem importar dados (para depuração)."""
    contents = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(contents), nrows=2)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler Excel: {str(e)}")
    original = list(df.columns)
    normalized = [normalize_col(c) for c in original]
    mapeadas = {n: COLUMN_MAP[n] for n in normalized if n in COLUMN_MAP}
    nao_mapeadas = [n for n in normalized if n not in COLUMN_MAP]
    return {
        "colunas_originais": original,
        "colunas_normalizadas": normalized,
        "mapeadas": mapeadas,
        "nao_mapeadas": nao_mapeadas,
    }



class CompareMode(str, Enum):
    deveria = "deveria"
    month = "month"


def get_month_volume(ponto: Ponto, month: Optional[int]) -> Optional[float]:
    if month is None:
        return None
    return getattr(ponto, f"volume_{month:02d}", None)


def resolve_actual_volume(ponto: Ponto, selected_month: Optional[int] = None) -> Optional[float]:
    if selected_month is not None:
        return get_month_volume(ponto, selected_month)
    return ponto.vol_fat


def resolve_expected_volume(ponto: Ponto, compare_with_deveria: bool = False, comparison_month: Optional[int] = None) -> Optional[float]:
    if compare_with_deveria:
        return ponto.deriva_faturar
    if comparison_month is not None:
        return get_month_volume(ponto, comparison_month)
    return None


def format_variance(actual: Optional[float], expected: Optional[float]) -> Optional[float]:
    if actual is None or expected is None:
        return None
    return float(actual - expected)


def format_variance_pct(actual: Optional[float], expected: Optional[float]) -> Optional[float]:
    if actual is None or expected is None or expected == 0:
        return None
    return float((actual - expected) / expected * 100)


def get_variance_category_label(actual: Optional[float], expected: Optional[float]) -> str:
    if actual is None or expected is None or expected == 0:
        return 'Sem comparação'
    pct = (actual - expected) / expected * 100
    if pct < -75:
        return 'Muito menos (<-75%)'
    if pct < -50:
        return 'Muito menos (-75% a -50%)'
    if pct < -30:
        return 'Menos (-50% a -30%)'
    if pct < -10:
        return 'Pouco menos (-30% a -10%)'
    if pct <= 2:
        return 'Esperado (-2% a +2%)'
    if pct < 10:
        return 'Pouco mais (+2% a +10%)'
    if pct < 30:
        return 'Mais (+10% a +30%)'
    if pct < 75:
        return 'Muito mais (+30% a +75%)'
    return 'Muito mais (>+75%)'


def categorize_vol_fat(vol: Optional[float]) -> str:
    if vol is None or (isinstance(vol, float) and math.isnan(vol)):
        return 'Sem volume'
    if vol < 10:
        return '0 - 10 m³'
    if vol < 50:
        return '10 - 50 m³'
    if vol < 100:
        return '50 - 100 m³'
    if vol < 300:
        return '100 - 300 m³'
    if vol < 500:
        return '300 - 500 m³'
    if vol < 1000:
        return '500 - 1.000 m³'
    return '> 1.000 m³'


def build_analitico_row(
    ponto: Ponto,
    selected_month: Optional[int],
    comparison_month: Optional[int],
    compare_with_deveria: bool,
) -> dict:
    actual = resolve_actual_volume(ponto, selected_month)
    expected = resolve_expected_volume(ponto, compare_with_deveria, comparison_month)
    return {
        "num_ligacao":    ponto.num_ligacao,
        "nom_cliente":    ponto.nom_cliente,
        "tipo_faturamento": ponto.tipo_faturamento,
        "cidade":         ponto.cidade,
        "bairro":         ponto.bairro,
        "macro":          ponto.macro,
        "micro":          ponto.micro,
        "cod_grupo":      ponto.cod_grupo,
        "rota":           ponto.rota,
        "gc":             ponto.gc,
        "sit_ligacao":    ponto.sit_ligacao,
        "categoria":      ponto.categoria,
        "vol_fat":        ponto.vol_fat,
        "sum_valor":      ponto.sum_valor,
        "is_grande":      ponto.is_grande,
        "selected_month": selected_month,
        "comparison_month": comparison_month,
        "compare_with_deveria": compare_with_deveria,
        "selected_month_label": f"Mês {selected_month:02d}" if selected_month else "Nenhum",
        "comparison_month_label": compare_with_deveria
            and 'Deveria Faturar' or (f"Mês {comparison_month:02d}" if comparison_month else 'Nenhum'),
        "actual_value":    actual,
        "expected_value":  expected,
        "deveria":         ponto.deriva_faturar,
        "variance":        format_variance(actual, expected),
        "variance_pct":    format_variance_pct(actual, expected),
    }


def build_analitico_rows(
    pontos: List[Ponto],
    selected_month: Optional[int],
    comparison_month: Optional[int],
    compare_with_deveria: bool,
) -> List[dict]:
    return [
        build_analitico_row(p, selected_month, comparison_month, compare_with_deveria)
        for p in pontos
    ]


@app.get("/api/pontos")
def get_pontos(
    db: Session = Depends(get_db),
    tipo_faturamento: Optional[str] = Query(None),
    cidade: Optional[str] = Query(None),
    macro: Optional[str] = Query(None),
    grupo: Optional[str] = Query(None),
    rota: Optional[str] = Query(None),
    gc: Optional[str] = Query(None),  # "SIM" | "NAO" for gc column
    selected_month: Optional[int] = Query(None, ge=1, le=12),
    comparison_month: Optional[int] = Query(None, ge=1, le=12),
    compare_with_deveria: bool = Query(False),
    compare_month_legacy: Optional[int] = Query(None, alias="compare_month", ge=1, le=12),
    limit: int = Query(30000, le=100000),
    offset: int = Query(0),
):
    if selected_month is None and compare_month_legacy is not None:
        selected_month = compare_month_legacy
    if compare_with_deveria:
        comparison_month = None
    query = db.query(Ponto).filter(
        Ponto.cod_latitude.isnot(None),
        Ponto.cod_longitude.isnot(None),
    )
    if tipo_faturamento:
        query = query.filter(Ponto.tipo_faturamento == tipo_faturamento)
    if cidade:
        query = query.filter(Ponto.cidade == cidade)
    if macro:
        query = query.filter(Ponto.macro == macro)
    if grupo:
        query = query.filter(Ponto.cod_grupo == grupo)
    if rota:
        query = query.filter(Ponto.rota == rota)
    if gc:
        gc_norm = gc.strip().upper().replace('Ã', 'A').replace('Õ', 'O')
        if gc_norm == "SIM":
            query = query.filter(Ponto.gc.ilike("SIM"))
        elif gc_norm == "NAO":
            query = query.filter(~Ponto.gc.ilike("SIM"))

    total = query.count()
    pontos = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "data": [
            {
                "id": p.id,
                "lat": p.cod_latitude,
                "lng": p.cod_longitude,
                "tipo_faturamento": p.tipo_faturamento,
                "nom_cliente": p.nom_cliente,
                "cidade": p.cidade,
                "macro": p.macro,
                "micro": p.micro,
                "rota": p.rota,
                "referencia": p.referencia,
                "sit_ligacao": p.sit_ligacao,
                "vol_fat": p.vol_fat,
                "num_ligacao": p.num_ligacao,
                "categoria": p.categoria,
                "cod_grupo": p.cod_grupo,
                "gc": p.gc,
                "is_grande": p.is_grande,
                "sum_valor": p.sum_valor,
                "qtd_eco_totais": p.qtd_eco_totais,
                "qtd_eco_res": p.qtd_eco_res,
                "qtd_eco_com": p.qtd_eco_com,
                "qtd_eco_ind": p.qtd_eco_ind,
                "qtd_eco_out": p.qtd_eco_out,
                "qtd_eco_pub": p.qtd_eco_pub,
                "volume_total": p.volume_total,
                "volume_01": p.volume_01,
                "volume_02": p.volume_02,
                "volume_03": p.volume_03,
                "volume_04": p.volume_04,
                "volume_05": p.volume_05,
                "volume_06": p.volume_06,
                "volume_07": p.volume_07,
                "volume_08": p.volume_08,
                "volume_09": p.volume_09,
                "volume_10": p.volume_10,
                "volume_11": p.volume_11,
                "volume_12": p.volume_12,
                "deriva_faturar": p.deriva_faturar,
                "selected_month": selected_month,
                "comparison_month": comparison_month,
                "compare_with_deveria": compare_with_deveria,
                "selected_month_label": f"Mês {selected_month:02d}" if selected_month else "Nenhum",
                "comparison_month_label": compare_with_deveria
                    and 'Deveria Faturar' or (f"Mês {comparison_month:02d}" if comparison_month else 'Nenhum'),
                "actual_value": resolve_actual_volume(p, selected_month),
                "expected_value": resolve_expected_volume(p, compare_with_deveria, comparison_month),
                "deveria": p.deriva_faturar,
                "variance": format_variance(
                    resolve_actual_volume(p, selected_month),
                    resolve_expected_volume(p, compare_with_deveria, comparison_month),
                ),
                "variance_pct": format_variance_pct(
                    resolve_actual_volume(p, selected_month),
                    resolve_expected_volume(p, compare_with_deveria, comparison_month),
                ),
            }
            for p in pontos
        ],
    }


@app.get("/api/heatmap")
def get_heatmap(
    db: Session = Depends(get_db),
    limit: int = Query(50000, ge=1000, le=500000),
    cidade: Optional[str] = Query(None),
    selected_month: Optional[int] = Query(None, ge=1, le=12),
    comparison_month: Optional[int] = Query(None, ge=1, le=12),
    compare_with_deveria: bool = Query(False),
    variance_pct_min: float = Query(-100, ge=-100, le=1000),
    variance_pct_max: float = Query(1000, ge=-100, le=1000),
):
    """Returns lat/lng/weight points for heatmap based on volume variance (deficiência).
    Shows areas with higher variance to identify neighborhoods with supply issues.
    Supports filtering by cidade, comparison modes, and variance percentage range.
    """
    query = db.query(Ponto).filter(
        Ponto.cod_latitude.isnot(None),
        Ponto.cod_longitude.isnot(None),
    )
    if cidade:
        query = query.filter(Ponto.cidade.contains(cidade))
    
    pontos = query.order_by(Ponto.id.desc()).limit(limit).all()
    
    # Build heatmap data with variance as weight, filtered by variance percentage
    result = []
    for p in pontos:
        actual = resolve_actual_volume(p, selected_month)
        expected = resolve_expected_volume(p, compare_with_deveria, comparison_month)
        
        if actual is not None and expected is not None and expected > 0:
            # Calculate variance percentage
            variance_pct = ((actual - expected) / expected) * 100
            
            # Filter by variance percentage range
            if variance_pct_min <= variance_pct <= variance_pct_max:
                # Use absolute variance value for heatmap intensity
                variance = abs(actual - expected)
                result.append([float(p.cod_latitude), float(p.cod_longitude), float(variance)])
    
    return result


@app.get("/api/filtros")
def get_filtros(
    db: Session = Depends(get_db),
    cidade: Optional[str] = Query(None),
    tipo_faturamento: Optional[str] = Query(None),
    macro: Optional[str] = Query(None),
    grupo: Optional[str] = Query(None),
    rota: Optional[str] = Query(None),
):
    """Returns unique values for filter dropdowns, restricted to existing combinations of selected filters."""
    # cidades are always the full list (top-level anchor)
    cidades = [r[0] for r in db.query(Ponto.cidade).distinct().order_by(Ponto.cidade).all() if r[0]]

    # For each field we compute its distinct values under ALL OTHER active filters.
    # This way each dropdown shows only what's reachable given the rest of the selection.
    def _q(exclude: str):
        """Base query with all active filters EXCEPT the excluded field."""
        q = db.query(Ponto)
        if exclude != 'cidade'         and cidade:           q = q.filter(Ponto.cidade == cidade)
        if exclude != 'tipo_faturamento' and tipo_faturamento: q = q.filter(Ponto.tipo_faturamento == tipo_faturamento)
        if exclude != 'macro'           and macro:            q = q.filter(Ponto.macro == macro)
        if exclude != 'grupo'           and grupo:            q = q.filter(Ponto.cod_grupo == grupo)
        if exclude != 'rota'            and rota:             q = q.filter(Ponto.rota == rota)
        return q

    tipos     = [r[0] for r in _q('tipo_faturamento').with_entities(Ponto.tipo_faturamento).distinct().all() if r[0]]
    macros    = [r[0] for r in _q('macro').with_entities(Ponto.macro).distinct().order_by(Ponto.macro).all() if r[0]]
    grupos    = [r[0] for r in _q('grupo').with_entities(Ponto.cod_grupo).distinct().order_by(Ponto.cod_grupo).all() if r[0]]
    rotas     = [r[0] for r in _q('rota').with_entities(Ponto.rota).distinct().order_by(Ponto.rota).all() if r[0]]
    gc_values = [r[0] for r in _q('gc').with_entities(Ponto.gc).distinct().all() if r[0]]
    return {"tipos_faturamento": tipos, "cidades": cidades, "macros": macros, "grupos": grupos, "gc_values": gc_values, "rotas": rotas}


@app.get('/api/gis/layers')
def get_gis_layers_endpoint():
    """List available shapefile layers from backend/ArcGis."""
    return {"layers": get_gis_layers()}


@app.get('/api/gis/layer/{layer_id}')
def get_gis_layer(layer_id: str):
    """Return GeoJSON for the requested GIS layer."""
    shapefile_path = find_gis_layer_path(layer_id)
    if not os.path.exists(shapefile_path):
        raise HTTPException(status_code=404, detail=f"Arquivo shapefile não encontrado: {shapefile_path}")
    try:
        gdf = gpd.read_file(shapefile_path)
        if gdf.crs is not None and getattr(gdf.crs, 'to_epsg', lambda: None)() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        geojson = json.loads(gdf.to_json())
        return geojson
    except Exception as e:
        logger.exception('Erro ao ler shapefile %s', shapefile_path)
        raise HTTPException(status_code=500, detail=f"Erro ao processar shapefile: {str(e)}")


@app.get('/api/gis/layer/{layer_id}/info')
def get_gis_layer_info(layer_id: str):
    """Return summary information for the requested GIS layer."""
    shapefile_path = find_gis_layer_path(layer_id)
    if not os.path.exists(shapefile_path):
        raise HTTPException(status_code=404, detail=f"Arquivo shapefile não encontrado: {shapefile_path}")
    try:
        gdf = gpd.read_file(shapefile_path)
        
        n_rows, n_cols = gdf.shape
        geom_types = gdf.geometry.type.value_counts().to_dict()
        bounds = gdf.total_bounds.tolist()
        
        # Colunas com informações
        columns_info = []
        for col in gdf.columns:
            if col != 'geometry':
                columns_info.append({
                    'name': col,
                    'type': str(gdf[col].dtype),
                    'non_null': int(gdf[col].notna().sum()),
                    'unique': int(gdf[col].nunique()),
                })
        
        return {
            'layer_id': layer_id,
            'filename': os.path.basename(shapefile_path),
            'shape': [n_rows, n_cols],
            'crs': str(gdf.crs) if gdf.crs else None,
            'geometry_types': geom_types,
            'bounds': bounds,
            'columns': columns_info,
        }
    except Exception as e:
        logger.exception('Erro ao analisar shapefile %s', shapefile_path)
        raise HTTPException(status_code=500, detail=f"Erro ao processar shapefile: {str(e)}")


@app.get('/api/gis/layer/{layer_id}/statistics')
def get_gis_layer_statistics(layer_id: str):
    """Return detailed statistics for the requested GIS layer."""
    shapefile_path = find_gis_layer_path(layer_id)
    if not os.path.exists(shapefile_path):
        raise HTTPException(status_code=404, detail=f"Arquivo shapefile não encontrado: {shapefile_path}")
    try:
        from gis_analyzer import GisAnalyzer
        
        analyzer = GisAnalyzer(shapefile_path)
        if not analyzer.load_data():
            raise HTTPException(status_code=500, detail="Erro ao carregar shapefile")
        
        analyzer.inspect_data()
        analyzer.process_geometry()
        
        return analyzer.get_summary()
    except Exception as e:
        logger.exception('Erro ao analisar shapefile %s', shapefile_path)
        raise HTTPException(status_code=500, detail=f"Erro ao processar shapefile: {str(e)}")


@app.get("/api/stats")
def get_stats(
    db: Session = Depends(get_db),
    tipo_faturamento: Optional[str] = Query(None),
    cidade: Optional[str] = Query(None),
    macro: Optional[str] = Query(None),
    grupo: Optional[str] = Query(None),
    rota: Optional[str] = Query(None),
    gc: Optional[str] = Query(None),
    selected_month: Optional[int] = Query(None, ge=1, le=12),
    comparison_month: Optional[int] = Query(None, ge=1, le=12),
    compare_with_deveria: bool = Query(False),
    compare_month_legacy: Optional[int] = Query(None, alias="compare_month", ge=1, le=12),
):
    from sqlalchemy import func as sqlfunc

    if selected_month is None and compare_month_legacy is not None:
        selected_month = compare_month_legacy
    if compare_with_deveria:
        comparison_month = None

    def _normalize_gc(value: str) -> str:
        return value.strip().upper().replace('Ã', 'A').replace('Õ', 'O')

    def _apply_filters(query):
        if tipo_faturamento:
            query = query.filter(Ponto.tipo_faturamento == tipo_faturamento)
        if cidade:
            query = query.filter(Ponto.cidade == cidade)
        if macro:
            query = query.filter(Ponto.macro == macro)
        if grupo:
            query = query.filter(Ponto.cod_grupo == grupo)
        if rota:
            query = query.filter(Ponto.rota == rota)
        if gc:
            gc_norm = _normalize_gc(gc)
            if gc_norm == 'SIM':
                query = query.filter(Ponto.gc.ilike('SIM'))
            elif gc_norm == 'NAO':
                query = query.filter(~Ponto.gc.ilike('SIM'))
        return query

    filtered_q = _apply_filters(db.query(Ponto))
    total = filtered_q.count()
    coord_q = _apply_filters(db.query(Ponto)).filter(
        Ponto.cod_latitude.isnot(None), Ponto.cod_longitude.isnot(None)
    )
    com_coords = coord_q.count()

    by_tipo = [
        {
            'tipo': r[0] or 'N/A',
            'qtd': r[1],
            'total_vol': r[2] or 0,
        }
        for r in _apply_filters(db.query(Ponto))
            .with_entities(
                Ponto.tipo_faturamento,
                sqlfunc.count(Ponto.id),
                sqlfunc.coalesce(sqlfunc.sum(Ponto.vol_fat), 0),
            )
            .group_by(Ponto.tipo_faturamento)
            .order_by(sqlfunc.count(Ponto.id).desc())
            .all()
    ]

    points = _apply_filters(db.query(Ponto)).all()
    faixa_counts = defaultdict(int)
    faixa_volumes = defaultdict(float)
    bairro_faixa_counts = defaultdict(lambda: defaultdict(int))
    bairro_volumes = defaultdict(lambda: {
        'qtd': 0,
        'vol_selected': 0.0,  # volume do mês selecionado
        'vol_compared': 0.0,  # volume comparado
        'vol_diff': 0.0,      # diferença
    })

    for p in points:
        faixa = categorize_vol_fat(p.vol_fat)
        faixa_counts[faixa] += 1
        faixa_volumes[faixa] += float(p.vol_fat or 0)

        category = get_variance_category_label(
            resolve_actual_volume(p, selected_month),
            resolve_expected_volume(p, compare_with_deveria, comparison_month),
        )
        bairro_label = (p.bairro or '').strip() or 'N/A'
        bairro_faixa_counts[bairro_label][category] += 1
        
        # Agregar volumes por bairro
        actual_vol = resolve_actual_volume(p, selected_month)
        expected_vol = resolve_expected_volume(p, compare_with_deveria, comparison_month)
        
        bairro_volumes[bairro_label]['qtd'] += 1
        if actual_vol is not None:
            bairro_volumes[bairro_label]['vol_selected'] += float(actual_vol)
        if expected_vol is not None:
            bairro_volumes[bairro_label]['vol_compared'] += float(expected_vol)
        if actual_vol is not None and expected_vol is not None:
            bairro_volumes[bairro_label]['vol_diff'] += float(actual_vol - expected_vol)

    faixa_order = [
        'Sem volume',
        '0 - 10 m³',
        '10 - 50 m³',
        '50 - 100 m³',
        '100 - 300 m³',
        '300 - 500 m³',
        '500 - 1.000 m³',
        '> 1.000 m³',
    ]
    by_faixa = [
        {
            'faixa': faixa,
            'qtd': faixa_counts[faixa],
            'total_vol': faixa_volumes[faixa],
        }
        for faixa in faixa_order
        if faixa_counts[faixa] > 0
    ]

    # Construir by_bairro com os 3 volumes
    by_bairro = [
        {
            'bairro': bairro,
            'qtd': bairro_volumes[bairro]['qtd'],
            'vol_selected': round(bairro_volumes[bairro]['vol_selected'], 2),
            'vol_compared': round(bairro_volumes[bairro]['vol_compared'], 2),
            'vol_diff': round(bairro_volumes[bairro]['vol_diff'], 2),
        }
        for bairro in sorted(bairro_volumes.keys(), key=lambda x: bairro_volumes[x]['qtd'], reverse=True)
    ]

    variance_order = [
        'Muito menos (<-75%)',
        'Muito menos (-75% a -50%)',
        'Menos (-50% a -30%)',
        'Pouco menos (-30% a -10%)',
        'Esperado (-2% a +2%)',
        'Pouco mais (+2% a +10%)',
        'Mais (+10% a +30%)',
        'Muito mais (+30% a +75%)',
        'Muito mais (>+75%)',
        'Sem comparação',
    ]
    by_bairro_faixa = []
    for bairro_label in sorted(bairro_faixa_counts.keys(), key=lambda x: x.lower()):
        for faixa in variance_order:
            qtd = bairro_faixa_counts[bairro_label].get(faixa, 0)
            if qtd > 0:
                by_bairro_faixa.append({
                    'bairro': bairro_label,
                    'faixa': faixa,
                    'qtd': qtd,
                })

    vol_fat_max_row = _apply_filters(db.query(Ponto)).filter(Ponto.vol_fat.isnot(None))
    vol_fat_max = float(vol_fat_max_row.with_entities(sqlfunc.max(Ponto.vol_fat)).scalar() or 0)

    total_vol_q = _apply_filters(db.query(Ponto)).with_entities(sqlfunc.coalesce(sqlfunc.sum(Ponto.vol_fat), 0))
    total_valor_q = _apply_filters(db.query(Ponto)).with_entities(sqlfunc.coalesce(sqlfunc.sum(Ponto.sum_valor), 0))
    total_volume_total_q = _apply_filters(db.query(Ponto)).with_entities(sqlfunc.coalesce(sqlfunc.sum(Ponto.volume_total), 0))
    total_deriva_q = _apply_filters(db.query(Ponto)).with_entities(sqlfunc.coalesce(sqlfunc.sum(Ponto.deriva_faturar), 0))

    total_vol_row = total_vol_q.scalar()
    total_valor_row = total_valor_q.scalar()
    total_volume_total_row = total_volume_total_q.scalar()
    total_deriva_row = total_deriva_q.scalar()

    volume_series = {}
    for i in range(1, 13):
        volume_series[f"volume_{i:02d}"] = float(
            _apply_filters(db.query(Ponto))
                .with_entities(sqlfunc.coalesce(sqlfunc.sum(getattr(Ponto, f'volume_{i:02d}')), 0))
                .scalar() or 0
        )

    return {
        'total': total,
        'com_coords': com_coords,
        'by_tipo': by_tipo,
        'by_bairro': by_bairro,
        'by_faixa': by_faixa,
        'by_bairro_faixa': by_bairro_faixa,
        'vol_fat_max': vol_fat_max,
        'total_vol': float(total_vol_row) if total_vol_row else 0,
        'total_valor': float(total_valor_row) if total_valor_row else 0,
        'total_volume_total': float(total_volume_total_row) if total_volume_total_row else 0,
        'total_deriva_faturar': float(total_deriva_row) if total_deriva_row else 0,
        'volume_series': volume_series,
    }


@app.get("/api/volume-comparison")
def get_volume_comparison(
    db: Session = Depends(get_db),
    cidade: Optional[str] = Query(None),
    tipo_faturamento: Optional[str] = Query(None),
    gc: Optional[str] = Query(None),
):
    from sqlalchemy import func as sqlfunc
    base_q = db.query(Ponto)
    if cidade:
        base_q = base_q.filter(Ponto.cidade == cidade)
    if tipo_faturamento:
        base_q = base_q.filter(Ponto.tipo_faturamento == tipo_faturamento)
    if gc:
        gc_norm = gc.strip().upper().replace('Ã', 'A').replace('Õ', 'O')
        if gc_norm == "SIM":
            base_q = base_q.filter(Ponto.gc.ilike("SIM"))
        elif gc_norm == "NAO":
            base_q = base_q.filter(~Ponto.gc.ilike("SIM"))

    totals = {
        "vol_fat": float(base_q.with_entities(sqlfunc.coalesce(sqlfunc.sum(Ponto.vol_fat), 0)).scalar() or 0),
        "volume_total": float(base_q.with_entities(sqlfunc.coalesce(sqlfunc.sum(Ponto.volume_total), 0)).scalar() or 0),
        "deriva_faturar": float(base_q.with_entities(sqlfunc.coalesce(sqlfunc.sum(Ponto.deriva_faturar), 0)).scalar() or 0),
    }
    volume_series = {}
    for i in range(1, 13):
        field = getattr(Ponto, f"volume_{i:02d}")
        volume_series[f"volume_{i:02d}"] = float(base_q.with_entities(sqlfunc.coalesce(sqlfunc.sum(field), 0)).scalar() or 0)
    return {"totals": totals, "volume_series": volume_series}


@app.get("/api/buscar")
def buscar_ponto(
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, le=100),
):
    """Busca pontos por nome do cliente ou número da ligação."""
    from sqlalchemy import or_
    results = (
        db.query(Ponto)
        .filter(
            Ponto.cod_latitude.isnot(None),
            Ponto.cod_longitude.isnot(None),
            or_(
                Ponto.nom_cliente.contains(q),
                Ponto.num_ligacao.contains(q),
            ),
        )
        .limit(limit)
        .all()
    )
    return [
        {
            "id": p.id,
            "lat": p.cod_latitude,
            "lng": p.cod_longitude,
            "nom_cliente": p.nom_cliente,
            "num_ligacao": p.num_ligacao,
            "tipo_faturamento": p.tipo_faturamento,
            "cidade": p.cidade,
            "macro": p.macro,
            "micro": p.micro,
            "referencia": p.referencia,
            "sit_ligacao": p.sit_ligacao,
            "vol_fat": p.vol_fat,
            "sum_valor": p.sum_valor,
            "is_grande": p.is_grande,
            "categoria": p.categoria,
        }
        for p in results
    ]


@app.get("/api/ranking")
def get_ranking(
    db: Session = Depends(get_db),
    limit: int = Query(50, le=200),
    cidade: Optional[str] = Query(None),
    tipo_faturamento: Optional[str] = Query(None),
):
    """Retorna clientes ordenados por volume faturado (maior → menor)."""
    query = db.query(Ponto).filter(
        Ponto.cod_latitude.isnot(None),
        Ponto.cod_longitude.isnot(None),
        Ponto.vol_fat.isnot(None),
        Ponto.vol_fat > 0,
    )
    if cidade:
        query = query.filter(Ponto.cidade == cidade)
    if tipo_faturamento:
        query = query.filter(Ponto.tipo_faturamento == tipo_faturamento)
    pontos = query.order_by(Ponto.vol_fat.desc()).limit(limit).all()
    return [
        {
            "id": p.id,
            "lat": p.cod_latitude,
            "lng": p.cod_longitude,
            "nom_cliente": p.nom_cliente,
            "num_ligacao": p.num_ligacao,
            "tipo_faturamento": p.tipo_faturamento,
            "cidade": p.cidade,
            "macro": p.macro,
            "micro": p.micro,
            "referencia": p.referencia,
            "sit_ligacao": p.sit_ligacao,
            "vol_fat": p.vol_fat,
            "sum_valor": p.sum_valor,
            "is_grande": p.is_grande,
            "categoria": p.categoria,
        }
        for p in pontos
    ]


@app.get("/api/ranking/rotas")
def ranking_rotas(
    db: Session = Depends(get_db),
    limit: int = Query(50, le=200),
    cidade: Optional[str] = Query(None),
):
    """Retorna rotas ordenadas por volume total e valor total."""
    cidade_filter = "AND cidade = :cidade" if cidade else ""
    params: dict = {"limit": limit}
    if cidade:
        params["cidade"] = cidade
    result = db.execute(text(
        f"SELECT rota, COUNT(*) as qtd, SUM(vol_fat) as total_vol, SUM(sum_valor) as total_valor "
        f"FROM pontos WHERE rota IS NOT NULL AND rota != '' {cidade_filter} "
        "GROUP BY rota ORDER BY total_vol DESC LIMIT :limit"
    ), params).fetchall()
    return [{"rota": r[0], "qtd": r[1], "total_vol": r[2] or 0, "total_valor": r[3] or 0} for r in result]


@app.get("/api/ranking/grupos")
def ranking_grupos(
    db: Session = Depends(get_db),
    limit: int = Query(50, le=200),
    cidade: Optional[str] = Query(None),
):
    """Retorna cod_grupos ordenados por volume total e valor total."""
    cidade_filter = "AND cidade = :cidade" if cidade else ""
    params: dict = {"limit": limit}
    if cidade:
        params["cidade"] = cidade
    result = db.execute(text(
        f"SELECT cod_grupo, COUNT(*) as qtd, SUM(vol_fat) as total_vol, SUM(sum_valor) as total_valor "
        f"FROM pontos WHERE cod_grupo IS NOT NULL AND cod_grupo != '' {cidade_filter} "
        "GROUP BY cod_grupo ORDER BY total_vol DESC LIMIT :limit"
    ), params).fetchall()
    return [{"cod_grupo": r[0], "qtd": r[1], "total_vol": r[2] or 0, "total_valor": r[3] or 0} for r in result]


@app.get("/api/ranking/grupos/{grupo}/rotas")
def ranking_grupo_rotas(
    grupo: str,
    db: Session = Depends(get_db),
    limit: int = Query(10, le=50),
    cidade: Optional[str] = Query(None),
):
    """Retorna as rotas de um cod_grupo ordenadas por volume e valor."""
    cidade_filter = "AND cidade = :cidade" if cidade else ""
    params: dict = {"grupo": grupo, "limit": limit}
    if cidade:
        params["cidade"] = cidade
    result = db.execute(text(
        f"SELECT cidade, rota, COUNT(*) as qtd, SUM(vol_fat) as total_vol, SUM(sum_valor) as total_valor "
        f"FROM pontos WHERE cod_grupo = :grupo AND rota IS NOT NULL AND rota != '' {cidade_filter} "
        "GROUP BY cidade, rota ORDER BY total_valor DESC LIMIT :limit"
    ), params).fetchall()
    return [{"cidade": r[0], "rota": r[1], "qtd": r[2], "total_vol": r[3] or 0, "total_valor": r[4] or 0} for r in result]


@app.get("/api/analitico")
def get_analitico(
    db: Session = Depends(get_db),
    cidade: Optional[str] = Query(None),
    grupo: Optional[str] = Query(None),
    rota: Optional[str] = Query(None),
    tipo_faturamento: Optional[str] = Query(None),
    macro: Optional[str] = Query(None),
    gc: Optional[str] = Query(None),
    selected_month: Optional[int] = Query(None, ge=1, le=12),
    comparison_month: Optional[int] = Query(None, ge=1, le=12),
    compare_with_deveria: bool = Query(False),
    compare_month_legacy: Optional[int] = Query(None, alias="compare_month", ge=1, le=12),
    limit: int = Query(50000, le=200000),
):
    """Retorna analítico agregado dos registros nos filtros selecionados."""
    if selected_month is None and compare_month_legacy is not None:
        selected_month = compare_month_legacy
    if compare_with_deveria:
        comparison_month = None
    from sqlalchemy import func as sqlfunc

    base_q = db.query(Ponto)
    if cidade:           base_q = base_q.filter(Ponto.cidade == cidade)
    if grupo:            base_q = base_q.filter(Ponto.cod_grupo == grupo)
    if rota:             base_q = base_q.filter(Ponto.rota == rota)
    if tipo_faturamento: base_q = base_q.filter(Ponto.tipo_faturamento == tipo_faturamento)
    if macro:            base_q = base_q.filter(Ponto.macro == macro)
    if gc:
        gc_norm = gc.strip().upper().replace('Ã', 'A').replace('Õ', 'O')
        if gc_norm == "SIM":
            base_q = base_q.filter(Ponto.gc.ilike("SIM"))
        elif gc_norm == "NAO":
            base_q = base_q.filter(~Ponto.gc.ilike("SIM"))

    total = base_q.count()
    agg_row = base_q.with_entities(
        sqlfunc.coalesce(sqlfunc.sum(Ponto.vol_fat), 0),
        sqlfunc.coalesce(sqlfunc.sum(Ponto.sum_valor), 0),
    ).one()
    total_vol   = float(agg_row[0])
    total_valor = float(agg_row[1])
    total_gc    = base_q.filter(Ponto.gc.ilike("SIM")).count()

    def breakdown(field):
        rows = (
            base_q.with_entities(
                field,
                sqlfunc.count(Ponto.id),
                sqlfunc.coalesce(sqlfunc.sum(Ponto.vol_fat), 0),
                sqlfunc.coalesce(sqlfunc.sum(Ponto.sum_valor), 0),
            )
            .group_by(field)
            .order_by(sqlfunc.sum(Ponto.vol_fat).desc().nullslast())
            .all()
        )
        return [{"label": r[0] or "N/A", "qtd": r[1], "vol": float(r[2]), "valor": float(r[3])} for r in rows]

    by_tipo = breakdown(Ponto.tipo_faturamento)
    by_rota = breakdown(Ponto.rota)
    by_sit  = breakdown(Ponto.sit_ligacao)

    pontos = base_q.order_by(Ponto.vol_fat.desc().nullslast()).limit(limit).all()
    pontos_out = [
        {
            "num_ligacao":    p.num_ligacao,
            "nom_cliente":    p.nom_cliente,
            "tipo_faturamento": p.tipo_faturamento,
            "cidade":         p.cidade,
            "macro":          p.macro,
            "micro":          p.micro,
            "cod_grupo":      p.cod_grupo,
            "rota":           p.rota,
            "gc":             p.gc,
            "sit_ligacao":    p.sit_ligacao,
            "categoria":      p.categoria,
            "vol_fat":        p.vol_fat,
            "sum_valor":      p.sum_valor,
            "is_grande":      p.is_grande,
            "selected_month": selected_month,
            "comparison_month": comparison_month,
            "compare_with_deveria": compare_with_deveria,
            "selected_month_label": f"Mês {selected_month:02d}" if selected_month else "Nenhum",
            "comparison_month_label": compare_with_deveria
                and 'Deveria Faturar' or (f"Mês {comparison_month:02d}" if comparison_month else 'Nenhum'),
            "actual_value":    resolve_actual_volume(p, selected_month),
            "expected_value":  resolve_expected_volume(p, compare_with_deveria, comparison_month),
            "deveria":         p.deriva_faturar,
            "variance":        format_variance(
                resolve_actual_volume(p, selected_month),
                resolve_expected_volume(p, compare_with_deveria, comparison_month),
            ),
            "variance_pct":    format_variance_pct(
                resolve_actual_volume(p, selected_month),
                resolve_expected_volume(p, compare_with_deveria, comparison_month),
            ),
        }
        for p in pontos
    ]

    return {
        "total":       total,
        "total_vol":   total_vol,
        "total_valor": total_valor,
        "total_gc":    total_gc,
        "by_tipo":     by_tipo,
        "by_rota":     by_rota,
        "by_sit":      by_sit,
        "pontos":      pontos_out,
    }


@app.get("/api/analitico/xlsx")
def get_analitico_xlsx(
    db: Session = Depends(get_db),
    cidade: Optional[str] = Query(None),
    grupo: Optional[str] = Query(None),
    rota: Optional[str] = Query(None),
    tipo_faturamento: Optional[str] = Query(None),
    macro: Optional[str] = Query(None),
    gc: Optional[str] = Query(None),
    selected_month: Optional[int] = Query(None, ge=1, le=12),
    comparison_month: Optional[int] = Query(None, ge=1, le=12),
    compare_with_deveria: bool = Query(False),
    compare_month_legacy: Optional[int] = Query(None, alias="compare_month", ge=1, le=12),
):
    if selected_month is None and compare_month_legacy is not None:
        selected_month = compare_month_legacy
    if compare_with_deveria:
        comparison_month = None

    base_q = db.query(Ponto)
    if cidade:           base_q = base_q.filter(Ponto.cidade == cidade)
    if grupo:            base_q = base_q.filter(Ponto.cod_grupo == grupo)
    if rota:             base_q = base_q.filter(Ponto.rota == rota)
    if tipo_faturamento: base_q = base_q.filter(Ponto.tipo_faturamento == tipo_faturamento)
    if macro:            base_q = base_q.filter(Ponto.macro == macro)
    if gc:
        gc_norm = gc.strip().upper().replace('Ã', 'A').replace('Õ', 'O')
        if gc_norm == "SIM":
            base_q = base_q.filter(Ponto.gc.ilike("SIM"))
        elif gc_norm == "NAO":
            base_q = base_q.filter(~Ponto.gc.ilike("SIM"))

    pontos = base_q.order_by(Ponto.vol_fat.desc().nullslast()).all()
    pontos_out = build_analitico_rows(pontos, selected_month, comparison_month, compare_with_deveria)

    df = pd.DataFrame(pontos_out)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Analitico")
    output.seek(0)

    filename = f"analitico_{datetime.datetime.now():%Y-%m-%d}.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@app.get("/api/pontos/xlsx")
def get_pontos_xlsx(
    db: Session = Depends(get_db),
):
    """Exporta todo o banco de dados de pontos em Excel, com coluna adicional bairro."""
    result = db.execute(text("SELECT * FROM pontos")).mappings().all()
    rows = [dict(r) for r in result]
    df = pd.DataFrame(rows)

    if "bairro" not in df.columns:
        df["bairro"] = ""

    if "cidade" in df.columns and "bairro" in df.columns:
        cols = list(df.columns)
        cols.remove("bairro")
        cols.insert(cols.index("cidade") + 1, "bairro")
        df = df[cols]

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Pontos")
    output.seek(0)

    filename = f"pontos_{datetime.datetime.now():%Y-%m-%d}.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )

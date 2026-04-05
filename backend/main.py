import os
import io
import math
import datetime
import logging
import unicodedata
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
import pandas as pd

from database import engine, get_db, Base
from models import Ponto
from routers.top_clientes import router as top_clientes_router
from routers.db_viewer import router as db_viewer_router

logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB

Base.metadata.create_all(bind=engine)

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
    # Volume — actual: Vol_Fat__Águas_Fat_
    "VOL_FAT__AGUAS_FAT_": "vol_fat",
    "VOL_FAT__AGUAS_FAT": "vol_fat",
    "VOL_FAT": "vol_fat",
}


def normalize_col(name: str) -> str:
    """Normalize column name: uppercase, strip spaces, remove special chars."""
    normalized = unicodedata.normalize("NFD", str(name))
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    return normalized.upper().strip().replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_")


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

    df = df.rename(columns=rename_map)

    # Coerce numeric columns to float (they come as object/str with dtype=object)
    NUMERIC_FIELDS = [
        'cod_latitude', 'cod_longitude', 'sum_valor',
        'valor_d1', 'valor_d2', 'valor_in1', 'valor_in2', 'valor_a',
        'qtd_eco1', 'qtd_eco2', 'vol_fat',
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
            db.execute(text(
                "INSERT INTO pontos (num_ligacao, nom_cliente, categoria, cod_grupo, num_medidor, "
                "tipo_faturamento, cidade, macro, micro, referencia, sit_ligacao, is_grande, "
                "cod_latitude, cod_longitude, sum_valor, valor_d1, valor_d2, valor_in1, valor_in2, "
                "valor_a, qtd_eco1, qtd_eco2, vol_fat)"
                " VALUES (:num_ligacao, :nom_cliente, :categoria, :cod_grupo, :num_medidor, "
                ":tipo_faturamento, :cidade, :macro, :micro, :referencia, :sit_ligacao, :is_grande, "
                ":cod_latitude, :cod_longitude, :sum_valor, :valor_d1, :valor_d2, :valor_in1, :valor_in2, "
                ":valor_a, :qtd_eco1, :qtd_eco2, :vol_fat)"
            ), records)
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



@app.get("/api/pontos")
def get_pontos(
    db: Session = Depends(get_db),
    tipo_faturamento: Optional[str] = Query(None),
    cidade: Optional[str] = Query(None),
    macro: Optional[str] = Query(None),
    gc: Optional[str] = Query(None),  # "SIM" | "NAO"
    limit: int = Query(30000, le=100000),
    offset: int = Query(0),
):
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
    if gc == "SIM":
        query = query.filter(Ponto.is_grande.ilike("SIM"))
    elif gc == "NAO":
        query = query.filter(
            (Ponto.is_grande == None) | (~Ponto.is_grande.ilike("SIM"))
        )

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
                "referencia": p.referencia,
                "sit_ligacao": p.sit_ligacao,
                "vol_fat": p.vol_fat,
                "num_ligacao": p.num_ligacao,
                "categoria": p.categoria,
                "is_grande": p.is_grande,
                "sum_valor": p.sum_valor,
            }
            for p in pontos
        ],
    }


@app.get("/api/heatmap")
def get_heatmap(
    db: Session = Depends(get_db),
    limit: int = Query(50000, ge=1000, le=500000),
    cidade: Optional[str] = Query(None),
    vol_min: float = Query(0, ge=0),
):
    """Returns lat/lng/weight points for heatmap based on vol_fat.
    Supports filtering by cidade and minimum vol_fat threshold.
    Samples up to `limit` points ordered by ID descending.
    """
    from sqlalchemy import func as sqlfunc
    query = (
        db.query(Ponto.cod_latitude, Ponto.cod_longitude, Ponto.vol_fat)
        .filter(
            Ponto.cod_latitude.isnot(None),
            Ponto.cod_longitude.isnot(None),
            Ponto.vol_fat.isnot(None),
            Ponto.vol_fat > vol_min,
        )
    )
    if cidade:
        query = query.filter(Ponto.cidade.contains(cidade))
    pontos = query.order_by(Ponto.id.desc()).limit(limit).all()
    return [
        [float(p.cod_latitude), float(p.cod_longitude), float(p.vol_fat)]
        for p in pontos
    ]


@app.get("/api/filtros")
def get_filtros(db: Session = Depends(get_db)):
    """Returns unique values for filter dropdowns."""
    tipos = [r[0] for r in db.query(Ponto.tipo_faturamento).distinct().all() if r[0]]
    cidades = [r[0] for r in db.query(Ponto.cidade).distinct().order_by(Ponto.cidade).all() if r[0]]
    macros = [r[0] for r in db.query(Ponto.macro).distinct().order_by(Ponto.macro).all() if r[0]]
    return {"tipos_faturamento": tipos, "cidades": cidades, "macros": macros}


@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    from sqlalchemy import func as sqlfunc
    total = db.query(Ponto).count()
    com_coords = db.query(Ponto).filter(
        Ponto.cod_latitude.isnot(None), Ponto.cod_longitude.isnot(None)
    ).count()
    result = db.execute(
        text("SELECT tipo_faturamento, COUNT(*) as qtd, SUM(vol_fat) as total_vol FROM pontos GROUP BY tipo_faturamento ORDER BY qtd DESC")
    ).fetchall()
    by_tipo = [{"tipo": r[0] or "N/A", "qtd": r[1], "total_vol": r[2] or 0} for r in result]
    vol_fat_max_row = db.query(sqlfunc.max(Ponto.vol_fat)).filter(Ponto.vol_fat.isnot(None)).scalar()
    vol_fat_max = float(vol_fat_max_row) if vol_fat_max_row else 0
    return {"total": total, "com_coords": com_coords, "by_tipo": by_tipo, "vol_fat_max": vol_fat_max}


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

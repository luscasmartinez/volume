"""
Router: Database Viewer (CRUD)
-------------------------------
Developer-facing CRUD interface to inspect and manipulate any table in the database.

Endpoints
---------
GET    /api/db/tables                          — list all tables
GET    /api/db/{table}/columns                 — list columns of a table
GET    /api/db/{table}/rows                    — paginated rows
POST   /api/db/{table}/rows                    — create a row
PUT    /api/db/{table}/rows/{id}               — update a row by PK
DELETE /api/db/{table}/rows/{id}               — delete a row by PK
GET    /api/db/{table}/detail/{id}             — get single row by PK
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
import logging

from database import engine, get_db
from models import Ponto

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/db", tags=["db-viewer"])

# Table-to-model mapping
TABLE_MODELS = {
    "pontos": Ponto,
}

VALID_TABLES = set(TABLE_MODELS.keys())


def _safe_table(table: str) -> str:
    if table not in VALID_TABLES:
        raise HTTPException(status_code=400, detail=f"Tabela '{table}' nao suportada. Tabelas: {sorted(VALID_TABLES)}")
    return table


@router.get("/tables")
def list_tables(db: Session = Depends(get_db)):
    """Returns available tables with basic metadata."""
    inspector = inspect(engine)
    table_list = []
    for table_name in inspector.get_table_names():
        pk_info = inspector.get_pk_constraint(table_name)
        pk_cols = pk_info.get("constrained_columns", [])
        columns = inspector.get_columns(table_name)
        col_names = [c["name"] for c in columns]
        count = db.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
        table_list.append({
            "name": table_name,
            "column_count": len(col_names),
            "columns": col_names,
            "primary_key": pk_cols,
            "row_count": count,
        })
    return {"tables": table_list}


@router.get("/{table}/schema")
def get_schema(table: str, db: Session = Depends(get_db)):
    """Returns detailed column schema for a table."""
    _safe_table(table)
    inspector = inspect(engine)
    pk_info = inspector.get_pk_constraint(table)
    pk_cols = pk_info.get("constrained_columns", [])
    unique_cols = inspector.get_unique_constraints(table)
    idx_cols = inspector.get_indexes(table)
    return {
        "table": table,
        "primary_key": pk_cols,
        "unique_constraints": unique_cols,
        "indexes": idx_cols,
        "columns": inspector.get_columns(table),
    }


@router.get("/{table}/rows")
def get_rows(
    table: str,
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sort: Optional[str] = Query(None, description="Column to sort by"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    search: Optional[str] = Query(None, description="Search all string columns"),
):
    """Returns paginated rows from a table."""
    _safe_table(table)
    columns_result = text(f"PRAGMA table_info({table})")
    col_info = db.execute(columns_result).fetchall()
    col_names = [c[1] for c in col_info]
    pk_col = "id"  # convention for all managed tables

    base_query = f"SELECT * FROM `{table}`"
    params = {}

    where_clauses = []
    if search:
        # Search in text columns (non-numeric)
        text_cols = [c[1] for c in col_info if c[2] in ("TEXT", "VARCHAR", "CHARACTER")]
        if text_cols:
            search_terms = [f"`{c}` LIKE :search" for c in text_cols]
            where_clauses.append(f"({' OR '.join(search_terms)})")
            params["search"] = f"%{search}%"

    if where_clauses:
        base_query += " WHERE " + " AND ".join(where_clauses)

    sort_col = sort
    if sort_col and sort_col in col_names:
        base_query += f" ORDER BY `{sort_col}` {order.upper()}"
    else:
        base_query += f" ORDER BY `{pk_col}` DESC"

    count_query = f"SELECT COUNT(*) FROM ({base_query})"
    total = db.execute(text(count_query), params).scalar()

    base_query += " LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    rows = db.execute(text(base_query), params).fetchall()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "columns": col_names,
        "rows": [dict(r._mapping) for r in rows],
    }


@router.get("/{table}/detail/{row_id}")
def get_row(table: str, row_id: int, db: Session = Depends(get_db)):
    """Returns a single row by ID."""
    _safe_table(table)
    row = db.execute(text(f"SELECT * FROM `{table}` WHERE id = :id"), {"id": row_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Registro nao encontrado")
    return dict(row._mapping)


@router.post("/{table}/rows")
def create_row(
    table: str,
    data: dict,
    db: Session = Depends(get_db),
):
    """Creates a new row in the specified table."""
    _safe_table(table)

    # Validate columns exist
    col_info = db.execute(text(f"PRAGMA table_info({table})")).fetchall()
    valid_cols = {c[1] for c in col_info}
    unknown = set(data.keys()) - valid_cols - {"id"}
    if unknown:
        raise HTTPException(status_code=400, detail=f"Colunas invalidas: {sorted(unknown)}")

    # Remove 'id' if present (auto-increment)
    data.pop("id", None)

    if not data:
        raise HTTPException(status_code=400, detail="Nenhum fornado fornecido")

    cols = ", ".join(f"`{k}`" for k in data.keys())
    placeholders = ", ".join(f":{k}" for k in data.keys())
    sql = f"INSERT INTO `{table}` ({cols}) VALUES ({placeholders})"

    try:
        result = db.execute(text(sql), data)
        db.commit()
        return {
            "message": "Registro criado com sucesso",
            "id": result.lastrowid,
        }
    except Exception as e:
        db.rollback()
        logger.exception("Error creating row in %s", table)
        raise HTTPException(status_code=500, detail=f"Erro ao criar registro: {str(e)}")


@router.put("/{table}/rows/{row_id}")
def update_row(
    table: str,
    row_id: int,
    data: dict,
    db: Session = Depends(get_db),
):
    """Updates an existing row by ID."""
    _safe_table(table)

    col_info = db.execute(text(f"PRAGMA table_info({table})")).fetchall()
    valid_cols = {c[1] for c in col_info}
    unknown = set(data.keys()) - valid_cols - {"id"}
    if unknown:
        raise HTTPException(status_code=400, detail=f"Colunas invalidas: {sorted(unknown)}")

    # Remove 'id' from data (can't change PK)
    data.pop("id", None)

    if not data:
        raise HTTPException(status_code=400, detail="Nenhum fornado fornecido")

    set_clauses = ", ".join(f"`{k}` = :{k}" for k in data.keys())
    sql = f"UPDATE `{table}` SET {set_clauses} WHERE id = :id"
    data["id"] = row_id

    try:
        result = db.execute(text(sql), data)
        db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Registro nao encontrado")
        return {"message": "Registro atualizado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error updating row %d in %s", row_id, table)
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar registro: {str(e)}")


@router.delete("/{table}/rows/{row_id}")
def delete_row(table: str, row_id: int, db: Session = Depends(get_db)):
    """Deletes a row by ID."""
    _safe_table(table)
    try:
        result = db.execute(text(f"DELETE FROM `{table}` WHERE id = :id"), {"id": row_id})
        db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Registro nao encontrado")
        return {"message": "Registro excluido com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error deleting row %d from %s", row_id, table)
        raise HTTPException(status_code=500, detail=f"Erro ao excluir registro: {str(e)}")

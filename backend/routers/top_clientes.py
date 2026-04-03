"""
Router: Top Clients per City
------------------------------
Entry-point (HTTP layer). Validates query parameters, delegates to the
service layer, and serialises the response.

Route
-----
GET /api/top-clientes-por-cidade
  ?cidade=<str>   — optional exact city filter
  ?top_n=<int>    — how many clients per city (1–50, default 10)
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from services.top_clientes_service import buscar_top_clientes_por_cidade

router = APIRouter(prefix="/api", tags=["top-clientes"])


@router.get("/top-clientes-por-cidade")
def top_clientes_por_cidade(
    db: Session = Depends(get_db),
    cidade: Optional[str] = Query(
        None,
        max_length=200,
        description="Filter by exact city name",
    ),
    top_n: int = Query(
        10,
        ge=1,
        le=50,
        description="Number of clients to return per city (max 50)",
    ),
):
    """
    Returns the top N clients per city ranked by total billed value (sum_valor).

    Clients with multiple records (e.g. multiple billing periods) are
    aggregated so each num_ligacao appears only once per city.

    The query uses CTEs and the ROW_NUMBER() window function — no Python
    loops, all aggregation happens in the database engine.
    """
    return buscar_top_clientes_por_cidade(db, cidade=cidade, top_n=top_n)

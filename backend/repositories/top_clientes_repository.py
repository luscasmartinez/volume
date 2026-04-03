"""
Repository: Top Clients per City
---------------------------------
All data access lives here. Uses a single optimised SQL query with two CTEs:
  1. client_totals  — aggregate multiple rows per num_ligacao into one client record
  2. ranked         — apply ROW_NUMBER() window function partitioned by cidade

No Python loops are used; heavy lifting happens entirely in the database engine.
SQLite >= 3.25 (shipped with Python 3.8+) supports window functions natively.
"""

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

_TOP_N_MAX = 50

_SQL = text(
    """
    WITH client_totals AS (
        SELECT
            num_ligacao,
            nom_cliente,
            cidade,
            categoria,
            macro,
            micro,
            SUM(sum_valor)        AS total_valor,
            SUM(vol_fat)          AS total_vol,
            MAX(cod_latitude)     AS lat,
            MAX(cod_longitude)    AS lng
        FROM pontos
        WHERE sum_valor IS NOT NULL
          AND sum_valor > 0
          AND cidade     IS NOT NULL
          AND num_ligacao IS NOT NULL
          AND (:cidade IS NULL OR cidade = :cidade)
        GROUP BY num_ligacao, nom_cliente, cidade, categoria, macro, micro
    ),
    ranked AS (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY cidade
                   ORDER BY total_valor DESC
               ) AS rn
        FROM client_totals
    )
    SELECT
        num_ligacao,
        nom_cliente,
        cidade,
        categoria,
        macro,
        micro,
        ROUND(total_valor, 2)             AS total_valor,
        ROUND(COALESCE(total_vol, 0), 2)  AS total_vol,
        lat,
        lng,
        CAST(rn AS INTEGER)               AS posicao
    FROM ranked
    WHERE rn <= :top_n
    ORDER BY cidade, rn
    """
)


def get_top_clientes_por_cidade(
    db: Session,
    *,
    cidade: Optional[str] = None,
    top_n: int = 10,
) -> list:
    """
    Returns the top-N clients per city ranked by aggregated billed value.

    Parameters
    ----------
    db     : active SQLAlchemy session
    cidade : optional city name filter (exact match, case-sensitive)
    top_n  : number of clients to return per city (capped at _TOP_N_MAX)
    """
    safe_top_n = min(max(1, top_n), _TOP_N_MAX)
    rows = db.execute(
        _SQL,
        {"cidade": cidade or None, "top_n": safe_top_n},
    ).fetchall()
    return [dict(r._mapping) for r in rows]

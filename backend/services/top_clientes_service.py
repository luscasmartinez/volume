"""
Service: Top Clients per City
-------------------------------
Business-logic layer. Receives raw rows from the repository and shapes them
into the response contract consumed by the router and the frontend.

Responsibilities:
- Call the repository (no direct DB access here)
- Group rows by city into a structured response
- Apply any domain rules (e.g., percentage bar normalisation)
"""

from typing import Optional

from sqlalchemy.orm import Session

from repositories.top_clientes_repository import get_top_clientes_por_cidade


def buscar_top_clientes_por_cidade(
    db: Session,
    *,
    cidade: Optional[str] = None,
    top_n: int = 10,
) -> dict:
    """
    Return the top N clients per city grouped by city name.

    Each city entry carries a `max_valor` field so the frontend can render
    relative bar widths without a second pass.

    Response schema
    ---------------
    {
      "total_cidades": int,
      "top_n": int,
      "cidades": [
        {
          "cidade": str,
          "max_valor": float,
          "clientes": [
            {
              "posicao":     int,
              "num_ligacao": str | null,
              "nom_cliente": str | null,
              "categoria":   str | null,
              "macro":       str | null,
              "micro":       str | null,
              "total_valor": float,
              "total_vol":   float,
              "lat":         float | null,
              "lng":         float | null,
            }, ...
          ]
        }, ...
      ]
    }
    """
    rows = get_top_clientes_por_cidade(db, cidade=cidade, top_n=top_n)

    grouped: dict[str, list] = {}
    for row in rows:
        city = row["cidade"]
        if city not in grouped:
            grouped[city] = []
        grouped[city].append(
            {
                "posicao":     row["posicao"],
                "num_ligacao": row["num_ligacao"],
                "nom_cliente": row["nom_cliente"],
                "categoria":   row["categoria"],
                "macro":       row["macro"],
                "micro":       row["micro"],
                "total_valor": row["total_valor"],
                "total_vol":   row["total_vol"],
                "lat":         row["lat"],
                "lng":         row["lng"],
            }
        )

    cidades_list = [
        {
            "cidade":    city,
            # first client always has the highest value (ORDER BY total_valor DESC)
            "max_valor": clients[0]["total_valor"] if clients else 1,
            "clientes":  clients,
        }
        for city, clients in grouped.items()
    ]

    return {
        "total_cidades": len(cidades_list),
        "top_n":         top_n,
        "cidades":       cidades_list,
    }

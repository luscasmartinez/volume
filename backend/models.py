from sqlalchemy import Column, Integer, String, Float, DateTime, Index
from database import Base


class Ponto(Base):
    __tablename__ = "pontos"
    __table_args__ = (
        # Composite index for Top-10 window-function query (partition key + sort key)
        Index("ix_pontos_cidade_sum_valor", "cidade", "sum_valor"),
        # Individual indexes for common filter columns
        Index("ix_pontos_vol_fat",    "vol_fat"),
        Index("ix_pontos_num_ligacao", "num_ligacao"),
        Index("ix_pontos_macro",       "macro"),
        
    )

    id = Column(Integer, primary_key=True, index=True)
    num_ligacao = Column(String, nullable=True)
    nom_cliente = Column(String, nullable=True)
    categoria = Column(String, nullable=True)
    cod_grupo = Column(String, nullable=True)
    num_medidor = Column(String, nullable=True)
    tipo_faturamento = Column(String, nullable=True)
    cidade = Column(String, nullable=True)
    bairro = Column(String, nullable=True)
    macro = Column(String, nullable=True)
    micro = Column(String, nullable=True)
    referencia = Column(String, nullable=True)
    sit_ligacao = Column(String, nullable=True)
    cod_latitude = Column(Float, nullable=True)
    cod_longitude = Column(Float, nullable=True)
    is_grande = Column(String, nullable=True)
    sum_valor = Column(Float, nullable=True)
    valor_d1 = Column(Float, nullable=True)
    valor_d2 = Column(Float, nullable=True)
    valor_in1 = Column(Float, nullable=True)
    valor_in2 = Column(Float, nullable=True)
    valor_a = Column(Float, nullable=True)
    qtd_eco1 = Column(Float, nullable=True)
    qtd_eco2 = Column(Float, nullable=True)
    qtd_eco_totais = Column(Float, nullable=True)
    qtd_eco_res = Column(Float, nullable=True)
    qtd_eco_com = Column(Float, nullable=True)
    qtd_eco_ind = Column(Float, nullable=True)
    qtd_eco_out = Column(Float, nullable=True)
    qtd_eco_pub = Column(Float, nullable=True)
    vol_fat = Column(Float, nullable=True)
    volume_total = Column(Float, nullable=True)
    volume_01 = Column(Float, nullable=True)
    volume_02 = Column(Float, nullable=True)
    volume_03 = Column(Float, nullable=True)
    volume_04 = Column(Float, nullable=True)
    volume_05 = Column(Float, nullable=True)
    volume_06 = Column(Float, nullable=True)
    volume_07 = Column(Float, nullable=True)
    volume_08 = Column(Float, nullable=True)
    volume_09 = Column(Float, nullable=True)
    volume_10 = Column(Float, nullable=True)
    volume_11 = Column(Float, nullable=True)
    volume_12 = Column(Float, nullable=True)
    deriva_faturar = Column(Float, nullable=True)
    gc = Column(String, nullable=True)
    rota = Column(String, nullable=True)

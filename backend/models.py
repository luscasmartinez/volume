from sqlalchemy import Column, Integer, String, Float, DateTime
from database import Base


class Ponto(Base):
    __tablename__ = "pontos"

    id = Column(Integer, primary_key=True, index=True)
    num_ligacao = Column(String, nullable=True)
    nom_cliente = Column(String, nullable=True)
    categoria = Column(String, nullable=True)
    cod_grupo = Column(String, nullable=True)
    num_medidor = Column(String, nullable=True)
    tipo_faturamento = Column(String, nullable=True)
    cidade = Column(String, nullable=True)
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
    vol_fat = Column(Float, nullable=True)

import sys, pandas as pd, unicodedata, math, traceback
sys.path.insert(0, '.')
from database import SessionLocal, Base, engine
from models import Ponto
Base.metadata.create_all(bind=engine)

COLUMN_MAP = {
    'NUM_LIGACAO': 'num_ligacao', 'NOM_CLIENTE': 'nom_cliente',
    'CATEGORIA': 'categoria', 'COD_GRUPO': 'cod_grupo',
    'NUM_MEDIDOR': 'num_medidor', 'TIPO_FATURAMENTO': 'tipo_faturamento',
    'CIDADE': 'cidade', 'MACRO': 'macro', 'MICRO': 'micro',
    'REFERENCIA': 'referencia', 'SIT_LIG': 'sit_ligacao',
    'COD_LATITUDE': 'cod_latitude', 'COD_LONGITUDE': 'cod_longitude',
    'ISGRANDTOTALROWTOTAL': 'is_grande', 'SUMVALOR': 'sum_valor',
    'VALOR_DIRETAS_AGUA': 'valor_d1', 'VALOR_DIRETAS_ESGOTO': 'valor_d2',
    'VALOR_INDIRETAS__ESGOTO': 'valor_in1', 'VALOR_INDIRETAS_AGUA': 'valor_in2',
    'VALOR_ABATIMENTOS': 'valor_a',
    'QTD_ECONOMIAS_FAT_AGUA': 'qtd_eco1', 'QTD_ECONOMIAS_FAT_ESGOTO': 'qtd_eco2',
    'VOL_FAT__AGUAS_FAT_': 'vol_fat',
}

def nc(name):
    n = unicodedata.normalize('NFD', str(name))
    n = ''.join(c for c in n if unicodedata.category(c) != 'Mn')
    return n.upper().strip().replace(' ', '_').replace('(', '').replace(')', '').replace('-', '_')

def safe_val(val):
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except Exception:
        pass
    if hasattr(val, 'item'):
        return val.item()
    return val

# Create minimal test matching user's columns
df = pd.DataFrame({
    'NUM_LIGACAO': ['001'], 'NOM_CLIENTE': ['TESTE'], 'CATEGORIA': ['RES'],
    'COD_GRUPo': ['G1'], 'NUM_MEDIDOR': ['M1'], 'TIPO_FATURAMENTO': ['AGUA'],
    'CIDADE': ['CIDADE A'], 'MACRO': ['M1'], 'MICRO': ['MI1'],
    'REFERENCIA': ['REF1'], 'SIT_LIG': ['ATIVO'], 'COD_LATITUDE': [-23.5],
    'IsGrandTotalRowTotal': ['N'], 'SumVALOR': [100.0],
    'Valor_Diretas_Agua': [50.0], 'Valor_Diretas_Esgoto': [30.0],
    'Valor_Indiretas__Esgoto': [10.0], 'Valor_Indiretas_Agua': [5.0],
    'Valor_Abatimentos': [0.0], 'Qtd_Economias_Fat_Agua': [1],
    'Qtd_Economias_Fat_Esgoto': [1], 'Vol_Fat__Aguas_Fat_': [20.0],
})

df.columns = [nc(c) for c in df.columns]
print("Cols normalized:", list(df.columns))

rename_map = {}; already = set()
for col in df.columns:
    t = COLUMN_MAP.get(col)
    if t and t not in already:
        rename_map[col] = t
        already.add(t)

print("Rename map:", rename_map)
df.rename(columns=rename_map, inplace=True)
print("Cols after rename:", list(df.columns))

model_fields = {c.name for c in Ponto.__table__.columns} - {'id'}
print("Model fields:", sorted(model_fields))

db = SessionLocal()
try:
    db.query(Ponto).delete()
    db.commit()
    for _, row in df.iterrows():
        data = {f: safe_val(row[f] if f in row.index else None) for f in model_fields}
        db.add(Ponto(**data))
    db.commit()
    print("SUCESSO - 1 registro inserido")
except Exception as e:
    db.rollback()
    print("ERRO:")
    traceback.print_exc()
finally:
    db.close()

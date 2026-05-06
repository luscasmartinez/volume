# 💧 Volume Platform

Plataforma web para visualização geográfica de ligações de água/esgoto, com upload de planilha Excel, mapa interativo e mapa de calor por volume faturado.

---

## Pré-requisitos

- **Python 3.11+** instalado → [python.org](https://www.python.org/downloads/)
- **pip** disponível no terminal

---

## Instalação

### 1. Instalar as dependências

Abra o terminal na pasta raiz do projeto (`volume/`) e execute:

```bash
pip install -r requirements.txt
```

---

## Executar o servidor

### Opção A — Script automático (Windows)

Dê duplo clique no arquivo:

```
start.bat
```

### Opção B — Terminal manual

```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```
(adicionar filtro por referencia)
Aguarde a mensagem:

```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## Acessar a plataforma

Abra o navegador e acesse:

```
http://localhost:8000
```

---

## Como usar

### 1. Importar a planilha Excel

- No painel esquerdo, clique na área **"Clique ou arraste"** e selecione seu arquivo `.xlsx` ou `.xls`
- Ou arraste o arquivo diretamente para a área de upload
- Aguarde a confirmação de importação (os pontos aparecerão automaticamente no mapa)

> A planilha deve conter as colunas: `NUM_LIGACAO`, `NOM_CLIENTE`, `CATEGORIA`, `COD_GRUPO`, `NUM_MEDIDOR`, `TIPO_FATURAMENTO`, `CIDADE`, `MACRO`, `MICRO`, `REFERENCIA`, `SIT_LIGACAO`, `COD_LATITUDE`, `COD_LONGITUDE`, `ISGRANDECONSUMIDOR`, `SUMVALOR`, `VALOR_D1`, `VALOR_D2`, `VALOR_IN1`, `VALOR_IN2`, `VALOR_A`, `QTD_ECO1`, `QTD_ECO2`, `VOL_FAT__ÁGUAS_FAT_`

### 2. Navegar no mapa

| Ação | Como fazer |
|---|---|
| Mover o mapa | Clique e arraste |
| Zoom | Scroll do mouse ou botões `+`/`-` |
| Ver detalhes de um ponto | Clique sobre o marcador |
| Ajustar zoom para todos os pontos | Botão **"⊕ Ajustar mapa"** |
| Trocar estilo do mapa | Controle no canto inferior direito (Escuro / OSM / Satélite) |
### 4. Camadas GIS

- Coloque seus arquivos shapefile (`.shp`, `.dbf`, `.shx`, `.prj`) em `backend/ArcGis`
- O backend lê automaticamente os arquivos `.shp` presentes nessa pasta
- Use a seção **Camadas GIS** no painel esquerdo para ativar/desativar a exibição
- O shapefile é convertido para GeoJSON e renderizado no mapa Leaflet
- Suporte a pontos, linhas e polígonos com popups de atributos
### 3. Cores dos pontos (Tipo de Faturamento)

| Cor | Tipo |
|---|---|
| 🔴 Vermelho | AGUA |
| 🟢 Verde | AGUA E ESGOTO |
| 🔵 Azul | ESGOTO |
| 🟡 Amarelo / outras | Demais tipos |

### 4. Mapa de Calor (Volume Faturado)

Ativa a visualização de regiões com maior volume faturado (`Vol_Fat`):

- Clique no botão **"🔥 Mapa de Calor"** (canto superior direito do mapa), **ou**
- Use o toggle **"🔥 Mapa de calor"** no painel esquerdo

Gradiente de cores do mapa de calor:

```
🔵 Baixo → 🟢 Médio → 🟡 Alto → 🔴 Muito alto
```

### 5. Filtros

Use os seletores no painel esquerdo para filtrar por:
- **Tipo de Faturamento**
- **Cidade**
- **Macro Região**

Clique em **"Aplicar Filtros"** para atualizar o mapa. Use **"✕ Limpar filtros"** para remover todos os filtros.

### 6. Outras opções do painel

| Toggle | Função |
|---|---|
| Mostrar pontos | Exibe/oculta todos os marcadores |
| Agrupar marcadores | Ativa/desativa agrupamento (cluster) para melhor performance |
| Mapa de calor | Ativa/desativa o heatmap |

---

## Estrutura do projeto

```
volume/
├── backend/
│   ├── main.py          ← API FastAPI (endpoints de upload, pontos, heatmap, filtros)
│   ├── database.py      ← Configuração do banco SQLite
│   └── models.py        ← Modelo de dados ORM
├── frontend/
│   └── templates/
│       └── index.html   ← Interface web (mapa Leaflet + painel de controle)
├── requirements.txt     ← Dependências Python
├── start.bat            ← Script de inicialização (Windows)
└── volume.db            ← Banco SQLite (criado automaticamente ao iniciar)
```

---

## API Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/` | Interface web principal |
| `POST` | `/api/upload` | Upload e importação da planilha Excel |
| `GET` | `/api/pontos` | Lista de pontos com coordenadas (suporta filtros) |
| `GET` | `/api/heatmap` | Dados para o mapa de calor |
| `GET` | `/api/filtros` | Valores únicos para os dropdowns de filtro |
| `GET` | `/api/stats` | Estatísticas gerais e por tipo |

Documentação interativa da API disponível em:
```
http://localhost:8000/docs
```

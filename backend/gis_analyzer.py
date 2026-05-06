"""
GIS Data Analysis Module - GeoPandas Shapefile Reader & Analyzer
"""
import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import mapping

logger = logging.getLogger(__name__)


class GisAnalyzer:
    def __init__(self, shapefile_path: str):
        self.shapefile_path = shapefile_path
        self.gdf = None
        self.analysis_results = {}
        
    def load_data(self) -> bool:
        """Load shapefile with error handling for encoding."""
        try:
            encodings = ['utf-8', 'latin1', 'iso-8859-1']
            for encoding in encodings:
                try:
                    self.gdf = gpd.read_file(self.shapefile_path, encoding=encoding)
                    print(f"✓ Shapefile carregado com sucesso (encoding: {encoding})")
                    
                    if self.gdf.crs is None:
                        print("⚠ Aviso: CRS não está definido no shapefile")
                        return True
                    print(f"✓ CRS: {self.gdf.crs}")
                    return True
                except Exception as e:
                    continue
            
            print("✗ Erro: Não foi possível carregar o shapefile com nenhum encoding")
            return False
        except Exception as e:
            logger.exception(f"Erro ao carregar shapefile: {e}")
            print(f"✗ Erro: {e}")
            return False
    
    def inspect_data(self) -> Dict[str, Any]:
        """Perform complete data inspection."""
        if self.gdf is None:
            return {}
        
        print("\n" + "="*60)
        print("INSPEÇÃO COMPLETA DOS DADOS")
        print("="*60)
        
        # Dimensões
        n_rows, n_cols = self.gdf.shape
        print(f"\n📊 Dimensões: {n_rows} linhas × {n_cols} colunas")
        
        # CRS
        crs_info = str(self.gdf.crs) if self.gdf.crs else "Não definido"
        print(f"🌍 CRS: {crs_info}")
        
        # Colunas e tipos
        print(f"\n📋 Colunas ({len(self.gdf.columns)}):")
        for col in self.gdf.columns:
            dtype = self.gdf[col].dtype
            non_null = self.gdf[col].notna().sum()
            print(f"   • {col}: {dtype} ({non_null}/{n_rows} não-nulos)")
        
        # Geometrias
        geom_types = self.gdf.geometry.type.value_counts().to_dict()
        print(f"\n🔷 Tipos de Geometria:")
        for geom_type, count in geom_types.items():
            print(f"   • {geom_type}: {count}")
        
        # Bounding box
        bounds = self.gdf.total_bounds
        print(f"\n📍 Bounding Box:")
        print(f"   Minx: {bounds[0]:.4f}, Miny: {bounds[1]:.4f}")
        print(f"   Maxx: {bounds[2]:.4f}, Maxy: {bounds[3]:.4f}")
        
        # Nulos por coluna
        nulls = self.gdf.isnull().sum()
        cols_with_nulls = nulls[nulls > 0]
        if len(cols_with_nulls) > 0:
            print(f"\n⚠ Colunas com valores nulos:")
            for col, count in cols_with_nulls.items():
                print(f"   • {col}: {count}")
        else:
            print(f"\n✓ Nenhuma coluna com valores nulos")
        
        # Primeiras linhas
        print(f"\n📄 Primeiras 3 linhas:")
        print(self.gdf.head(3).to_string())
        
        # Estatísticas descritivas
        numeric_cols = self.gdf.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 0:
            print(f"\n📈 Estatísticas Descritivas (colunas numéricas):")
            print(self.gdf[numeric_cols].describe().to_string())
        
        # Duplicatas
        if len(self.gdf) > 0:
            total_duplicates = self.gdf.duplicated(subset=[col for col in self.gdf.columns if col != 'geometry']).sum()
            print(f"\n🔄 Duplicatas: {total_duplicates} linha(s) duplicada(s)")
        
        # Candidatos a chave
        print(f"\n🔑 Candidatos a chave (valores únicos):")
        key_candidates = []
        for col in self.gdf.columns:
            if col != 'geometry' and self.gdf[col].dtype == 'object':
                unique_count = self.gdf[col].nunique()
                if unique_count == n_rows:
                    key_candidates.append(col)
                    print(f"   ✓ {col}: {unique_count} valores únicos")
        
        if not key_candidates:
            print("   (Nenhuma coluna candidata encontrada)")
        
        self.analysis_results['inspection'] = {
            'shape': [n_rows, n_cols],
            'crs': crs_info,
            'geometry_types': geom_types,
            'bounds': bounds.tolist(),
            'null_columns': cols_with_nulls.to_dict() if len(cols_with_nulls) > 0 else {},
            'duplicates': int(total_duplicates) if len(self.gdf) > 0 else 0,
            'key_candidates': key_candidates,
        }
        
        return self.analysis_results['inspection']
    
    def process_geometry(self) -> Dict[str, Any]:
        """Process and calculate geometric properties."""
        if self.gdf is None or len(self.gdf) == 0:
            return {}
        
        print("\n" + "="*60)
        print("PROCESSAMENTO GEOMÉTRICO")
        print("="*60)
        
        # Validar CRS
        if self.gdf.crs is None:
            print("⚠ CRS não definido. Assumindo EPSG:4326")
            self.gdf = self.gdf.set_crs("EPSG:4326")
        
        # Reprojetar se necessário
        if self.gdf.crs.is_geographic:
            print(f"📍 CRS geográfico detectado: {self.gdf.crs}")
            target_crs = "EPSG:31983"  # SAD69 / UTM zone 23S
            print(f"🔄 Reprojetando para {target_crs}...")
            self.gdf = self.gdf.to_crs(target_crs)
            print(f"✓ Reprojeção concluída")
        else:
            print(f"✓ CRS métrico já definido: {self.gdf.crs}")
        
        # Calcular área e perímetro
        print(f"\n📐 Calculando área e perímetro...")
        self.gdf['area_m2'] = self.gdf.geometry.area
        self.gdf['perimeter_m'] = self.gdf.geometry.length
        
        print(f"✓ Colunas 'area_m2' e 'perimeter_m' adicionadas")
        
        # Estatísticas geométricas
        area_stats = self.gdf['area_m2'].describe()
        print(f"\n📊 Estatísticas de Área (m²):")
        print(f"   Mínima: {area_stats['min']:.2f}")
        print(f"   Média: {area_stats['mean']:.2f}")
        print(f"   Máxima: {area_stats['max']:.2f}")
        print(f"   Desvio padrão: {area_stats['std']:.2f}")
        
        perim_stats = self.gdf['perimeter_m'].describe()
        print(f"\n📊 Estatísticas de Perímetro (m):")
        print(f"   Mínimo: {perim_stats['min']:.2f}")
        print(f"   Médio: {perim_stats['mean']:.2f}")
        print(f"   Máximo: {perim_stats['max']:.2f}")
        print(f"   Desvio padrão: {perim_stats['std']:.2f}")
        
        self.analysis_results['geometry'] = {
            'crs_used': str(self.gdf.crs),
            'area_stats': area_stats.to_dict(),
            'perimeter_stats': perim_stats.to_dict(),
            'total_area_m2': float(self.gdf['area_m2'].sum()),
        }
        
        return self.analysis_results['geometry']
    
    def plot_static(self, output_path: Optional[str] = None) -> str:
        """Create static map visualization."""
        if self.gdf is None or len(self.gdf) == 0:
            print("✗ Sem dados para plotar")
            return None
        
        print("\n" + "="*60)
        print("VISUALIZAÇÃO ESTÁTICA")
        print("="*60)
        
        try:
            import matplotlib.pyplot as plt
            
            fig, ax = plt.subplots(figsize=(12, 10))
            
            if 'area_m2' in self.gdf.columns:
                self.gdf.plot(column='area_m2', ax=ax, alpha=0.7, edgecolor='k', legend=True, cmap='YlOrRd')
                ax.set_title("Shapefile - Colorido por Área (m²)", fontsize=14, fontweight='bold')
            else:
                self.gdf.plot(ax=ax, alpha=0.7, edgecolor='k')
                ax.set_title("Shapefile", fontsize=14, fontweight='bold')
            
            ax.set_xlabel("Longitude/UTM X")
            ax.set_ylabel("Latitude/UTM Y")
            plt.tight_layout()
            
            if output_path is None:
                output_path = "shapefile_map.png"
            
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            plt.close()
            
            print(f"✓ Mapa estático salvo em: {output_path}")
            return output_path
        except Exception as e:
            logger.exception(f"Erro ao plotar mapa estático: {e}")
            print(f"✗ Erro ao criar visualização: {e}")
            return None
    
    def plot_interactive(self, output_path: Optional[str] = None) -> str:
        """Create interactive folium map."""
        if self.gdf is None or len(self.gdf) == 0:
            print("✗ Sem dados para plotar")
            return None
        
        print("\n" + "="*60)
        print("VISUALIZAÇÃO INTERATIVA (FOLIUM)")
        print("="*60)
        
        try:
            import folium
            
            # Garantir que está em WGS84 para folium
            gdf_wgs84 = self.gdf.to_crs("EPSG:4326") if self.gdf.crs != "EPSG:4326" else self.gdf.copy()
            bounds = gdf_wgs84.total_bounds
            center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
            
            m = folium.Map(location=center, zoom_start=12, tiles="OpenStreetMap")
            
            # Adicionar GeoJSON com tooltips
            for idx, row in gdf_wgs84.iterrows():
                geometry = row.geometry
                properties = {k: str(v) for k, v in row.items() if k != 'geometry'}
                
                tooltip_text = "<br>".join([f"<b>{k}:</b> {v}" for k, v in properties.items()])
                
                if geometry.geom_type == 'Polygon':
                    coords = list(geometry.exterior.coords)
                    folium.Polygon(
                        locations=[[lat, lon] for lon, lat in coords],
                        color='orange',
                        fill=True,
                        fillColor='orange',
                        fillOpacity=0.3,
                        popup=folium.Popup(tooltip_text, max_width=300),
                    ).add_to(m)
                
                elif geometry.geom_type == 'LineString':
                    coords = list(geometry.coords)
                    folium.PolyLine(
                        locations=[[lat, lon] for lon, lat in coords],
                        color='blue',
                        weight=2,
                        popup=folium.Popup(tooltip_text, max_width=300),
                    ).add_to(m)
                
                elif geometry.geom_type == 'Point':
                    folium.CircleMarker(
                        location=[geometry.y, geometry.x],
                        radius=5,
                        color='red',
                        fill=True,
                        fillOpacity=0.7,
                        popup=folium.Popup(tooltip_text, max_width=300),
                    ).add_to(m)
            
            if output_path is None:
                output_path = "shapefile_map.html"
            
            m.save(output_path)
            print(f"✓ Mapa interativo salvo em: {output_path}")
            return output_path
        except Exception as e:
            logger.exception(f"Erro ao plotar mapa interativo: {e}")
            print(f"✗ Erro ao criar visualização: {e}")
            return None
    
    def export_data(self, output_dir: str = ".") -> Dict[str, str]:
        """Export data to GeoJSON and CSV."""
        if self.gdf is None or len(self.gdf) == 0:
            print("✗ Sem dados para exportar")
            return {}
        
        print("\n" + "="*60)
        print("EXPORTAÇÃO DE DADOS")
        print("="*60)
        
        output_files = {}
        
        try:
            # Converter para WGS84 para GeoJSON
            gdf_wgs84 = self.gdf.to_crs("EPSG:4326") if self.gdf.crs != "EPSG:4326" else self.gdf.copy()
            
            # Exportar GeoJSON
            geojson_path = os.path.join(output_dir, "shapefile.geojson")
            gdf_wgs84.to_file(geojson_path, driver='GeoJSON')
            print(f"✓ GeoJSON salvo em: {geojson_path}")
            output_files['geojson'] = geojson_path
            
            # Exportar CSV (sem geometria)
            csv_path = os.path.join(output_dir, "shapefile_data.csv")
            gdf_no_geom = self.gdf.drop(columns=['geometry'])
            gdf_no_geom.to_csv(csv_path, index=False, encoding='utf-8')
            print(f"✓ CSV salvo em: {csv_path}")
            output_files['csv'] = csv_path
            
        except Exception as e:
            logger.exception(f"Erro ao exportar dados: {e}")
            print(f"✗ Erro ao exportar: {e}")
        
        return output_files
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all analysis."""
        summary = {
            'shapefile': os.path.basename(self.shapefile_path),
            'inspection': self.analysis_results.get('inspection', {}),
            'geometry': self.analysis_results.get('geometry', {}),
        }
        return summary
    
    def run_complete_analysis(self, output_dir: str = ".") -> Dict[str, Any]:
        """Execute complete analysis workflow."""
        print("\n" + "="*80)
        print("ANÁLISE COMPLETA DE SHAPEFILE - GEOPANDAS")
        print("="*80)
        
        if not self.load_data():
            return None
        
        self.inspect_data()
        self.process_geometry()
        
        try:
            self.plot_static(os.path.join(output_dir, "shapefile_map.png"))
        except:
            pass
        
        try:
            self.plot_interactive(os.path.join(output_dir, "shapefile_map.html"))
        except:
            pass
        
        self.export_data(output_dir)
        
        print("\n" + "="*80)
        print("✓ ANÁLISE COMPLETA FINALIZADA")
        print("="*80)
        
        return self.get_summary()


def analyze_gis_folder(folder_path: str) -> Dict[str, Dict]:
    """Analyze all shapefiles in a folder."""
    results = {}
    
    if not os.path.isdir(folder_path):
        print(f"✗ Pasta não encontrada: {folder_path}")
        return results
    
    shapefiles = list(Path(folder_path).glob("*.shp"))
    
    if not shapefiles:
        print(f"⚠ Nenhum shapefile encontrado em: {folder_path}")
        return results
    
    for shp_file in shapefiles:
        print(f"\n📂 Analisando: {shp_file.name}")
        analyzer = GisAnalyzer(str(shp_file))
        results[shp_file.stem] = analyzer.run_complete_analysis(folder_path)
    
    return results

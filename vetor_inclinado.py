#!/usr/bin/env python3
"""
Gerador Vetorial Inclinado: SVG / DXF → FullControl G-code Tridimensional Inclinado

Lê uma geometria de um arquivo vetorial (SVG nativo em Python puro ou DXF via ezdxf),
centraliza e escala o polígono de forma paramétrica no centro da mesa de impressão,
e gera uma peça tridimensional (pirâmide, cone ou vaso complexo) com:
  1. Base sólida com preenchimento concêntrico espiral contínuo e alternado.
  2. Paredes contínuas (Vase Mode) com inclinação tridimensional dinâmica baseada no ângulo.
  3. Proteção e encerramento seguro no ápice (Apex Check).

Dependências:
    pip install shapely
    pip install ezdxf (opcional, necessário apenas para arquivos DXF)
"""

import argparse
import math
import config_impressora
import re
import sys
import glob
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import fullcontrol as fc
from shapely.geometry import Polygon, LineString, MultiLineString, MultiPolygon
from shapely.ops import unary_union, polygonize, linemerge
from shapely import affinity


def gerar_passos_vetor(config):
    # --- Extração de Parâmetros da Configuração ---
    VETOR_ARQUIVO = config.get('vetor_arquivo', "no-celta.dxf")
    MODO_LINHA_UNICA = config.get('modo_linha_unica', True)
    largura_desejada_x = config.get('largura_x', 100.0)
    x_centro = config.get('x_centro', 180.0)
    y_centro = config.get('y_centro', 45.0)
    z_max_desejado = config.get('z_max_desejado', 100.0)
    angulo_parede = config.get('angulo_parede', 80.0)
    resolucao_mm = config.get('resolucao_mm', config_impressora.resolucao_mm)
    zonas_camadas = config.get('zonas_camadas', [
        {'camada_inicio': 0, 'num_perimetros': 0, 'infill_percent': 100.0, 'infill_pattern': 'concentric', 'fluxo_perimetro': 90.0, 'fluxo_infill': 100.0, 'espiral': False},
        {'camada_inicio': 4, 'num_perimetros': 1, 'infill_percent': 0.0, 'infill_pattern': 'concentric', 'fluxo_perimetro': 100.0, 'fluxo_infill': 100.0, 'espiral': True}
    ])
    largura_extrusao = config.get('largura_extrusao', 3.0)
    altura_camada = config.get('altura_camada', 1.0)
    transicao_vaso_z_offset = config.get('transicao_vaso_z_offset', 0.5)
    transicao_vaso_fluxo = config.get('transicao_vaso_fluxo', 85.0)
    wipe_final_ativo = config.get('wipe_final_ativo', True)
    wipe_final_distancia = config.get('wipe_final_distancia', 6.0)
    wipe_final_subida_z = config.get('wipe_final_subida_z', 0.5)
    priming_ativo = config.get('priming_ativo', True)
    priming_inicial_qtd = config.get('priming_inicial_qtd', 3.0)
    priming_inicial_vel = config.get('priming_inicial_vel', 2.0)
    priming_inicio_perimetro = config.get('priming_inicio_perimetro', True)
    priming_perimetro_inicio_qtd = config.get('priming_perimetro_inicio_qtd', 2.0)
    priming_perimetro_inicio_vel = config.get('priming_perimetro_inicio_vel', 2.0)
    priming_fim_perimetro = config.get('priming_fim_perimetro', True)
    priming_perimetro_fim_qtd = config.get('priming_perimetro_fim_qtd', 2.0)
    priming_perimetro_fim_vel = config.get('priming_perimetro_fim_vel', 2.0)
    priming_inicio_infill = config.get('priming_inicio_infill', True)
    priming_infill_inicio_qtd = config.get('priming_infill_inicio_qtd', 2.0)
    priming_infill_inicio_vel = config.get('priming_infill_inicio_vel', 2.0)
    priming_fim_infill = config.get('priming_fim_infill', True)
    priming_infill_fim_qtd = config.get('priming_infill_fim_qtd', 2.0)
    priming_infill_fim_vel = config.get('priming_infill_fim_vel', 2.0)
    NUM_CAMADAS_BASE_MACICA = int(config.get('num_camadas_base_macica', 4))
    sobreposicao_infill = config.get('sobreposicao_infill', 1.0)
    velocidade_impressao = config.get('velocidade_impressao', config_impressora.velocidade_impressao) * 60.0
    aceleracao_impressao = int(config.get('aceleracao_impressao', config_impressora.aceleracao_impressao))
    velocidade_primeira_camada = config.get('velocidade_primeira_camada', config_impressora.velocidade_primeira_camada) * 60.0
    aceleracao_primeira_camada = int(config.get('aceleracao_primeira_camada', config_impressora.aceleracao_primeira_camada))
    velocidade_travel = config.get('velocidade_travel', config_impressora.velocidade_travel) * 60.0
    # 2. PARSER DE ARQUIVOS VETORIAIS (SVG Nativo & DXF)
    # ==============================================================================

    def parse_svg_path(d_string):
        """Tokeniza e interpreta a string d de um path SVG em pontos 2D."""
        # Expressão regular para capturar comandos e floats
        tokens = re.findall(r'([A-Za-z])|([-+]?\d*\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+(?:[eE][-+]?\d+)?)', d_string)
        tokens_limpos = []
        for t in tokens:
            if t[0]:
                tokens_limpos.append(t[0])
            elif t[1]:
                tokens_limpos.append(float(t[1]))

        pontos = []
        x_at, y_at = 0.0, 0.0
        x_start, y_start = 0.0, 0.0
        idx = 0
        last_cmd = None

        while idx < len(tokens_limpos):
            token = tokens_limpos[idx]
            if isinstance(token, str):
                cmd = token
                idx += 1
            else:
                cmd = last_cmd

            if cmd == 'M':
                x_at = tokens_limpos[idx]
                y_at = tokens_limpos[idx+1]
                idx += 2
                x_start, y_start = x_at, y_at
                pontos.append((x_at, y_at))
                last_cmd = 'L'
            elif cmd == 'm':
                x_at += tokens_limpos[idx]
                y_at += tokens_limpos[idx+1]
                idx += 2
                x_start, y_start = x_at, y_at
                pontos.append((x_at, y_at))
                last_cmd = 'l'
            elif cmd == 'L':
                x_at = tokens_limpos[idx]
                y_at = tokens_limpos[idx+1]
                idx += 2
                pontos.append((x_at, y_at))
                last_cmd = 'L'
            elif cmd == 'l':
                x_at += tokens_limpos[idx]
                y_at += tokens_limpos[idx+1]
                idx += 2
                pontos.append((x_at, y_at))
                last_cmd = 'l'
            elif cmd == 'H':
                x_at = tokens_limpos[idx]
                idx += 1
                pontos.append((x_at, y_at))
                last_cmd = 'H'
            elif cmd == 'h':
                x_at += tokens_limpos[idx]
                idx += 1
                pontos.append((x_at, y_at))
                last_cmd = 'h'
            elif cmd == 'V':
                y_at = tokens_limpos[idx]
                idx += 1
                pontos.append((x_at, y_at))
                last_cmd = 'V'
            elif cmd == 'v':
                y_at += tokens_limpos[idx]
                idx += 1
                pontos.append((x_at, y_at))
                last_cmd = 'v'
            elif cmd in ('C', 'c'):
                if cmd == 'C':
                    x1, y1 = tokens_limpos[idx], tokens_limpos[idx+1]
                    x2, y2 = tokens_limpos[idx+2], tokens_limpos[idx+3]
                    x_end, y_end = tokens_limpos[idx+4], tokens_limpos[idx+5]
                else:
                    x1, y1 = x_at + tokens_limpos[idx], y_at + tokens_limpos[idx+1]
                    x2, y2 = x_at + tokens_limpos[idx+2], y_at + tokens_limpos[idx+3]
                    x_end, y_end = x_at + tokens_limpos[idx+4], y_at + tokens_limpos[idx+5]
                idx += 6

                # Aproximação linear da Curva Bézier Cúbica
                n_seg = 15
                for step in range(1, n_seg + 1):
                    t = step / n_seg
                    bx = (1-t)**3 * x_at + 3*(1-t)**2 * t * x1 + 3*(1-t) * t**2 * x2 + t**3 * x_end
                    by = (1-t)**3 * y_at + 3*(1-t)**2 * t * y1 + 3*(1-t) * t**2 * y2 + t**3 * y_end
                    pontos.append((bx, by))
                x_at, y_at = x_end, y_end
                last_cmd = cmd
            elif cmd in ('Q', 'q'):
                if cmd == 'Q':
                    x1, y1 = tokens_limpos[idx], tokens_limpos[idx+1]
                    x_end, y_end = tokens_limpos[idx+2], tokens_limpos[idx+3]
                else:
                    x1, y1 = x_at + tokens_limpos[idx], y_at + tokens_limpos[idx+1]
                    x_end, y_end = x_at + tokens_limpos[idx+2], y_at + tokens_limpos[idx+3]
                idx += 4

                # Aproximação linear da Curva Bézier Quadrática
                n_seg = 10
                for step in range(1, n_seg + 1):
                    t = step / n_seg
                    bx = (1-t)**2 * x_at + 2*(1-t) * t * x1 + t**2 * x_end
                    by = (1-t)**2 * y_at + 2*(1-t) * t * y1 + t**2 * y_end
                    pontos.append((bx, by))
                x_at, y_at = x_end, y_end
                last_cmd = cmd
            elif cmd in ('Z', 'z'):
                if math.hypot(x_at - x_start, y_at - y_start) > 0.01:
                    pontos.append((x_start, y_start))
                x_at, y_at = x_start, y_start
                last_cmd = None
            else:
                # Comando não implementado (e.g. Arco Elíptico)
                idx += 1

        return pontos


    def ler_geometria_svg(filepath):
        """Lê um arquivo SVG nativamente e extrai a maior geometria (polígono ou linha)."""
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
        except Exception as e:
            print(f"ERRO ao ler o arquivo SVG {filepath}: {e}")
            sys.exit(1)

        namespaces = {'svg': 'http://www.w3.org/2000/svg'}
        ET.register_namespace('', 'http://www.w3.org/2000/svg')

        # Encontrar todas as tags geométricas do SVG
        elementos = []
        for tag in ('path', 'polygon', 'polyline', 'rect', 'circle'):
            elementos.extend(root.findall(f'.//{tag}'))
            elementos.extend(root.findall(f'.//svg:{tag}', namespaces))

        caminhos = []
        for elem in elementos:
            tag_name = elem.tag.split('}')[-1]
            pontos_elem = []

            if tag_name == 'path':
                d_str = elem.attrib.get('d', '')
                pontos_elem = parse_svg_path(d_str)
            elif tag_name in ('polygon', 'polyline'):
                pts_str = elem.attrib.get('points', '')
                coords = [float(v) for v in re.findall(r'[-+]?\d*\.\d+|[-+]?\d+', pts_str)]
                for i in range(0, len(coords), 2):
                    if i + 1 < len(coords):
                        pontos_elem.append((coords[i], coords[i+1]))
                if pontos_elem and tag_name == 'polygon':
                    pontos_elem.append(pontos_elem[0])
            elif tag_name == 'rect':
                rx = float(elem.attrib.get('x', 0))
                ry = float(elem.attrib.get('y', 0))
                w = float(elem.attrib.get('width', 0))
                h = float(elem.attrib.get('height', 0))
                pontos_elem = [(rx, ry), (rx + w, ry), (rx + w, ry + h), (rx, ry + h), (rx, ry)]
            elif tag_name == 'circle':
                cx = float(elem.attrib.get('cx', 0))
                cy = float(elem.attrib.get('cy', 0))
                r = float(elem.attrib.get('r', 0))
                for i in range(65):
                    ang = (i / 64) * 2 * math.pi
                    pontos_elem.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))

            if MODO_LINHA_UNICA:
                if len(pontos_elem) >= 2:
                    caminhos.append(LineString(pontos_elem))
            else:
                if len(pontos_elem) >= 3:
                    caminhos.append(Polygon(pontos_elem))

        if not caminhos:
            print(f"ERRO: Nenhuma geometria valida encontrada no arquivo SVG: {filepath}")
            sys.exit(1)

        if MODO_LINHA_UNICA:
            return max(caminhos, key=lambda l: l.length)
        else:
            return max(caminhos, key=lambda p: p.area)


    def ler_geometria_dxf(filepath):
        """Lê um arquivo DXF usando ezdxf e extrai a maior geometria (linha ou polígono)."""
        try:
            import ezdxf
            from ezdxf.path import make_path
        except ImportError:
            print("\n" + "="*60)
            print("  ERRO: Para ler arquivos DXF, voce precisa instalar a biblioteca ezdxf!")
            print("  Por favor, execute o comando abaixo no terminal de sua maquina:")
            print("     pip install ezdxf")
            print("="*60 + "\n")
            sys.exit(1)

        try:
            doc = ezdxf.readfile(filepath)
        except Exception as e:
            print(f"ERRO ao ler o arquivo DXF {filepath}: {e}")
            sys.exit(1)

        msp = doc.modelspace()
        segmentos = []

        for entity in msp:
            tag_name = entity.dxftype()
            if tag_name in ('LINE', 'LWPOLYLINE', 'POLYLINE', 'ARC', 'CIRCLE'):
                try:
                    path = make_path(entity)
                    # Discretiza a curva usando resolucao_mm
                    pts = [(p.x, p.y) for p in path.flattening(distance=resolucao_mm)]
                    if len(pts) >= 2:
                        segmentos.append(LineString(pts))
                except Exception as e:
                    # Fallback em caso de erro na discretização do path
                    if tag_name == 'LINE':
                        start = entity.dxf.start
                        end = entity.dxf.end
                        segmentos.append(LineString([(start.x, start.y), (end.x, end.y)]))
                    elif tag_name in ('LWPOLYLINE', 'POLYLINE'):
                        pts = [(v[0], v[1]) for v in entity.vertices()]
                        if len(pts) >= 2:
                            segmentos.append(LineString(pts))

        if not segmentos:
            print(f"ERRO: Nenhuma entidade linear/poligonal encontrada no arquivo DXF: {filepath}")
            sys.exit(1)

        merged = linemerge(segmentos)

        if MODO_LINHA_UNICA:
            if merged.is_empty:
                print("ERRO: Nao foi possivel ler a linha do DXF.")
                sys.exit(1)
            if hasattr(merged, 'geoms'):
                return max(merged.geoms, key=lambda l: l.length)
            return merged
        else:
            # Unifica e tenta polygonizar
            union_lines = unary_union(segmentos)
            poligonos = list(polygonize(union_lines))

            if not poligonos:
                print(f"ERRO: Nenhum loop fechado (poligono) foi formado pelas entidades no DXF: {filepath}")
                sys.exit(1)

            return max(poligonos, key=lambda p: p.area)


    def obter_poligono_vetorial(filepath):
        """Identifica a extensão do arquivo e extrai a geometria base."""
        ext = Path(filepath).suffix.lower()
        if ext == '.svg':
            print(f"-> Lendo arquivo SVG nativamente: {filepath}")
            return ler_geometria_svg(filepath)
        elif ext == '.dxf':
            print(f"-> Lendo arquivo DXF via ezdxf: {filepath}")
            return ler_geometria_dxf(filepath)
        else:
            print(f"ERRO: Extensao de arquivo nao suportada: {ext} (Use .svg ou .dxf)")
            sys.exit(1)


    # ==============================================================================
    # 3. TRATAMENTO GEOMÉTRICO (CENTRALIZAÇÃO E DIMENSIONAMENTO)
    # ==============================================================================

    poligono_cru = obter_poligono_vetorial(VETOR_ARQUIVO)

    # 1. Obter bounding box do vetor original
    minx, miny, maxx, maxy = poligono_cru.bounds
    largura_original_x = maxx - minx

    # 2. Calcular fator de escala para corresponder à largura X desejada
    fator_escala = largura_desejada_x / largura_original_x if largura_original_x > 0 else 1.0

    # 3. Escalar o polígono proporcionalmente em relação ao seu próprio centroide
    poligono_escalado = affinity.scale(poligono_cru, xfact=fator_escala, yfact=fator_escala, origin=poligono_cru.centroid)

    # 4. Transladar para que o centro geométrico final coincida exatamente com (x_centro, y_centro)
    deslocamento_x = x_centro - poligono_escalado.centroid.x
    deslocamento_y = y_centro - poligono_escalado.centroid.y
    poligono_base = affinity.translate(poligono_escalado, xoff=deslocamento_x, yoff=deslocamento_y)

    # Garante validade do polígono (apenas se não for linha única)
    if not MODO_LINHA_UNICA:
        if not poligono_base.is_valid:
            poligono_base = poligono_base.buffer(0)
        if isinstance(poligono_base, MultiPolygon):
            poligono_base = max(poligono_base.geoms, key=lambda p: p.area)

    # 5. Se estiver em MODO_LINHA_UNICA e com base maciça ativa, gera a silhueta unificada de fundo
    if MODO_LINHA_UNICA:
        # Engrossa a linha para unificar
        area_engrossada = poligono_base.buffer(largura_extrusao / 2)
        if hasattr(area_engrossada, 'exterior') and area_engrossada.exterior is not None:
            silhueta_base = Polygon(area_engrossada.exterior)
        elif isinstance(area_engrossada, MultiPolygon):
            maior_geom = max(area_engrossada.geoms, key=lambda p: p.area)
            silhueta_base = Polygon(maior_geom.exterior)
        else:
            silhueta_base = area_engrossada

        # Garante validade
        if not silhueta_base.is_valid:
            silhueta_base = silhueta_base.buffer(0)
    else:
        NUM_CAMADAS_BASE_MACICA = 0
        silhueta_base = poligono_base

    print("=" * 60)
    print(f"-> Geometria vetorial processada com sucesso!")
    if MODO_LINHA_UNICA:
        print(f"-> Comprimento nominal do traco celta: {poligono_base.length:.2f} mm")
        print(f"-> Area da base solida macica (silhueta): {silhueta_base.area:.2f} mm2")
    else:
        print(f"-> Area nominal da peca: {poligono_base.area:.2f} mm2")
    print(f"-> Bounding Box final: {[f'{v:.2f}' for v in poligono_base.bounds]}")
    print(f"-> Centro geometrico (Centroide): X={poligono_base.centroid.x:.2f} Y={poligono_base.centroid.y:.2f}")
    print("=" * 60)


    # ==============================================================================
    # 4. FUNÇÕES DE TRAJETÓRIA E CONEXÃO CONTÍNUA
    # ==============================================================================

    recuo = largura_extrusao / 2
    num_camadas = math.ceil(z_max_desejado / altura_camada)

    def obter_zona(camada):
        zona_ativa = zonas_camadas[0]
        for zona in zonas_camadas:
            if camada >= zona['camada_inicio']:
                zona_ativa = zona
        return zona_ativa


    def get_last_point(steps):
        for step in reversed(steps):
            if hasattr(step, 'x') and step.x is not None:
                return step.x, step.y
        return x_centro, y_centro


    def adicionar_caminho_seguro(steps, pts, tipo=None):
        if not pts: return
        if tipo == 'perimetro':
            steps.append(fc.ManualGcode(text="; --- PERIMETRO START ---"))
        elif tipo == 'infill':
            steps.append(fc.ManualGcode(text="; --- INFILL START ---"))

        lx, ly = get_last_point(steps)
        dist = math.hypot(pts[0].x - lx, pts[0].y - ly)
        if dist > 0.5:
            steps.append(fc.Extruder(on=False))
            steps.append(pts[0])
            steps.append(fc.Extruder(on=True))
            steps.extend(pts[1:])
        else:
            steps.extend(pts)

        if tipo == 'perimetro':
            steps.append(fc.ManualGcode(text="; --- PERIMETRO END ---"))
        elif tipo == 'infill':
            steps.append(fc.ManualGcode(text="; --- INFILL END ---"))


    def orientar_caminho(pts, start_x, start_y):
        if not pts: return pts
        dist_start = math.hypot(pts[0].x - start_x, pts[0].y - start_y)
        dist_end = math.hypot(pts[-1].x - start_x, pts[-1].y - start_y)
        if dist_end < dist_start:
            pts.reverse()
        return pts


    def polygon_to_points(polygon, z, res_mm=1.0):
        coords = list(polygon.exterior.coords)
        pts = []
        for i in range(len(coords) - 1):
            x1, y1 = coords[i]
            x2, y2 = coords[i+1]
            dist = math.hypot(x2 - x1, y2 - y1)
            if dist > res_mm * 2:
                num_seg = max(1, int(math.ceil(dist / res_mm)))
                for j in range(num_seg):
                    t = j / num_seg
                    px = x1 + t * (x2 - x1)
                    py = y1 + t * (y2 - y1)
                    pts.append(fc.Point(x=px, y=py, z=z))
            else:
                pts.append(fc.Point(x=x1, y=y1, z=z))
        pts.append(fc.Point(x=pts[0].x, y=pts[0].y, z=z))
        return pts


    def gerar_perimetros_poligonais(num_perim, poligono_camada, z, espessura, start_x, start_y):
        pts_totais = []
        lx, ly = start_x, start_y

        for p in range(num_perim):
            if p == 0:
                offset = recuo
            else:
                offset = recuo + p * espessura

            poly_offset = poligono_camada.buffer(-offset)
            if poly_offset.is_empty:
                break
            if isinstance(poly_offset, MultiPolygon):
                poly_offset = max(poly_offset.geoms, key=lambda p: p.area)

            pts_perim = polygon_to_points(poly_offset, z, resolucao_mm)
            pts_perim = orientar_caminho(pts_perim, lx, ly)
            pts_totais.extend(pts_perim)
            if pts_perim:
                lx, ly = pts_totais[-1].x, pts_totais[-1].y

        return pts_totais


    def gerar_infill_concentrico_poligonal(poligono_camada, z, num_perimetros, largura_extrusao, sobreposicao=0.5):
        espacamento = largura_extrusao * 0.82
        if num_perimetros > 0:
            offset_base = recuo + num_perimetros * espacamento - sobreposicao
        else:
            offset_base = recuo

        aneis = []
        offset = offset_base

        while True:
            poly_ring = poligono_camada.buffer(-offset)
            if poly_ring.is_empty:
                break
            if isinstance(poly_ring, MultiPolygon):
                poly_ring = max(poly_ring.geoms, key=lambda p: p.area)
            if poly_ring.area < 1.0:
                break
            pts = polygon_to_points(poly_ring, z, resolucao_mm)
            if len(pts) >= 3:
                aneis.append(pts)
            offset += espacamento

        return aneis


    def rotacionar_anel(anel, px, py):
        if len(anel) < 3: return anel
        loop = anel[:-1]
        dists = [math.hypot(p.x - px, p.y - py) for p in loop]
        idx = dists.index(min(dists))
        rotacionado = loop[idx:] + loop[:idx]
        rotacionado.append(fc.Point(x=rotacionado[0].x, y=rotacionado[0].y, z=rotacionado[0].z))
        return rotacionado


    def gerar_espiral_concentrica_poligonal(aneis, start_x, start_y, out_to_in=True, centroid_x=0.0, centroid_y=0.0, espacamento=2.85):
        """Conecta múltiplos anéis concêntricos em uma única espiral poligonal contínua de Arquimedes."""
        if not aneis:
            return []
        aneis_validos = [a for a in aneis if len(a) >= 3]
        if not aneis_validos:
            return []

        if not out_to_in:
            aneis_validos.reverse()

        pts_espiral = []
        lx, ly = start_x, start_y
        cx, cy = centroid_x, centroid_y

        n_aneis = len(aneis_validos)

        for i in range(n_aneis):
            anel_atual = rotacionar_anel(aneis_validos[i], lx, ly)
            n_pts = len(anel_atual)

            # --- CASO 1: DE FORA PARA DENTRO ---
            if out_to_in:
                if i == n_aneis - 1:
                    # O último anel (mais interno) espira continuamente até o centroide (escala 1.0 a 0.0) para fechar o miolo
                    start_j = 0
                    if len(pts_espiral) > 0 and math.hypot(pts_espiral[-1].x - anel_atual[0].x, pts_espiral[-1].y - anel_atual[0].y) < 1e-4:
                        start_j = 1
                    for j in range(start_j, n_pts):
                        p = anel_atual[j]
                        t = j / (n_pts - 1) if n_pts > 1 else 1.0
                        dx = p.x - cx
                        dy = p.y - cy
                        factor = 1.0 - t
                        rx = cx + dx * factor
                        ry = cy + dy * factor
                        pts_espiral.append(fc.Point(x=rx, y=ry, z=p.z))
                    lx, ly = pts_espiral[-1].x, pts_espiral[-1].y
                else:
                    # Anéis intermediários encolhem linearmente
                    start_j = 0
                    if i > 0 and len(pts_espiral) > 0:
                        p0 = anel_atual[0]
                        dx0 = p0.x - cx
                        dy0 = p0.y - cy
                        rx0 = cx + dx0
                        ry0 = cy + dy0
                        if math.hypot(pts_espiral[-1].x - rx0, pts_espiral[-1].y - ry0) < 1e-4:
                            start_j = 1
                    for j in range(start_j, n_pts):
                        p = anel_atual[j]
                        t = j / (n_pts - 1) if n_pts > 1 else 1.0
                        dx = p.x - cx
                        dy = p.y - cy
                        d = math.hypot(dx, dy)
                        if d < 0.1:
                            pts_espiral.append(p)
                            continue
                        factor = 1.0 - t * (espacamento / d)
                        rx = cx + dx * factor
                        ry = cy + dy * factor
                        pts_espiral.append(fc.Point(x=rx, y=ry, z=p.z))
                    lx, ly = pts_espiral[-1].x, pts_espiral[-1].y

            # --- CASO 2: DE DENTRO PARA FORA ---
            else:
                if i == 0:
                    # O primeiro anel (mais interno) inicia no centroide e expande até o anel nominal (escala 0.0 a 1.0) para preencher o miolo
                    for j in range(n_pts):
                        p = anel_atual[j]
                        t = j / (n_pts - 1) if n_pts > 1 else 1.0
                        dx = p.x - cx
                        dy = p.y - cy
                        factor = t
                        rx = cx + dx * factor
                        ry = cy + dy * factor
                        pts_espiral.append(fc.Point(x=rx, y=ry, z=p.z))
                    lx, ly = pts_espiral[-1].x, pts_espiral[-1].y
                else:
                    # Todos os demais anéis intermediários e externos expandem continuamente do raio anterior (d - espacamento) ao raio nominal (d)
                    start_j = 0
                    if len(pts_espiral) > 0:
                        p0 = anel_atual[0]
                        dx0 = p0.x - cx
                        dy0 = p0.y - cy
                        d0 = math.hypot(dx0, dy0)
                        if d0 >= 0.1:
                            factor0 = (1.0 - espacamento / d0)
                            rx0 = cx + dx0 * factor0
                            ry0 = cy + dy0 * factor0
                            if math.hypot(pts_espiral[-1].x - rx0, pts_espiral[-1].y - ry0) < 1e-4:
                                start_j = 1
                    for j in range(start_j, n_pts):
                        p = anel_atual[j]
                        t = j / (n_pts - 1) if n_pts > 1 else 1.0
                        dx = p.x - cx
                        dy = p.y - cy
                        d = math.hypot(dx, dy)
                        if d < 0.1:
                            pts_espiral.append(p)
                            continue
                        factor = (1.0 - espacamento / d) + t * (espacamento / d)
                        rx = cx + dx * factor
                        ry = cy + dy * factor
                        pts_espiral.append(fc.Point(x=rx, y=ry, z=p.z))
                    lx, ly = pts_espiral[-1].x, pts_espiral[-1].y

        return pts_espiral


    def gerar_espiral_helicoidal_vaso(poligono_camada, z_inicio, z_fim, start_x, start_y):
        """Gera um perímetro helicoidal contínuo (Vase Mode) subindo Z de forma constante."""
        pts_nominais = polygon_to_points(poligono_camada, z_inicio, resolucao_mm)
        pts_nominais = rotacionar_anel(pts_nominais, start_x, start_y)

        pts_espirais = []
        n_pts = len(pts_nominais)
        for i in range(n_pts):
            p = pts_nominais[i]
            t = i / (n_pts - 1) if n_pts > 1 else 1.0
            z_atual = z_inicio + t * (z_fim - z_inicio)
            pts_espirais.append(fc.Point(x=p.x, y=p.y, z=z_atual))

        return pts_espirais


    # ==============================================================================
    # 5. CONSTRUÇÃO DO G-CODE EM CAMADAS INCLINADAS
    # ==============================================================================
    # --- Controle Extra de Infill ---

    # --- Velocidades (mm/min) ---

    steps = []
    steps.append(fc.Printer(print_speed=velocidade_primeira_camada, travel_speed=velocidade_travel))
    if aceleracao_primeira_camada > 0:
        steps.append(fc.ManualGcode(text=f"M201 X{aceleracao_primeira_camada} Y{aceleracao_primeira_camada}"))
    steps.append(fc.ExtrusionGeometry(area_model='rectangle', width=largura_extrusao, height=altura_camada))

    # Calcular o travel inicial para a primeira camada
    camada_init = obter_zona(0)
    num_perim_init = camada_init.get('num_perimetros', 1)

    # Encontra a primeira camada onde o vaso helicoidal inicia para referência Z
    camada_inicio_vaso = 3
    for zona in zonas_camadas:
        if zona.get('espiral', False):
            camada_inicio_vaso = zona['camada_inicio']
            break
    z_ref_vaso = camada_inicio_vaso * altura_camada

    if MODO_LINHA_UNICA:
        z_ref_vaso = NUM_CAMADAS_BASE_MACICA * altura_camada
        # Primeira camada (Z = altura_camada)
        linha_1 = poligono_base
        if angulo_parede != 90.0:
            delta_r_1 = (altura_camada - z_ref_vaso) / math.tan(math.radians(angulo_parede))
            r_0 = largura_desejada_x / 2
            fator_1 = 1.0 - (delta_r_1 / r_0) if r_0 > 0 else 1.0
            if NUM_CAMADAS_BASE_MACICA > 0:
                linha_1 = affinity.scale(silhueta_base, xfact=fator_1, yfact=fator_1, origin=silhueta_base.centroid)
            else:
                linha_1 = affinity.scale(poligono_base, xfact=fator_1, yfact=fator_1, origin=poligono_base.centroid)
        else:
            if NUM_CAMADAS_BASE_MACICA > 0:
                linha_1 = silhueta_base

        if NUM_CAMADAS_BASE_MACICA > 0:
            # Começa no perímetro externo da silhueta
            pts_perim_1 = gerar_perimetros_poligonais(1, linha_1, altura_camada, largura_extrusao * 0.95, x_centro - largura_desejada_x/2, y_centro)
            start_pt = pts_perim_1[0] if pts_perim_1 else fc.Point(x=x_centro, y=y_centro, z=altura_camada)
        else:
            # Começa no primeiro ponto da linha única
            coords = list(linha_1.coords)
            start_pt = fc.Point(x=coords[0][0], y=coords[0][1], z=altura_camada)

        steps.append(fc.Extruder(on=False))
        steps.append(fc.Point(x=start_pt.x, y=start_pt.y, z=altura_camada))
        steps.append(fc.Extruder(on=True))
    else:
        # Primeira camada de Z
        z_1 = altura_camada
        if angulo_parede != 90.0:
            buffer_offset_1 = - (z_1 - z_ref_vaso) / math.tan(math.radians(angulo_parede))
        else:
            buffer_offset_1 = 0.0

        if num_perim_init == 0:
            buffer_offset_1 += 2 * (largura_extrusao * 0.95)

        poligono_1 = poligono_base
        if not math.isclose(buffer_offset_1, 0.0):
            poligono_1 = poligono_base.buffer(buffer_offset_1)
            if isinstance(poligono_1, MultiPolygon):
                poligono_1 = max(poligono_1.geoms, key=lambda p: p.area)

        # Iniciar na primeira quina externa
        primeiro_perim = gerar_perimetros_poligonais(min(1, num_perim_init), poligono_1, altura_camada, largura_extrusao * 0.95, x_centro - largura_desejada_x/2, y_centro)
        if primeiro_perim:
            start_pt = primeiro_perim[0]
            steps.append(fc.Extruder(on=False))
            steps.append(fc.Point(x=start_pt.x, y=start_pt.y, z=altura_camada))
            steps.append(fc.Extruder(on=True))
        else:
            # Se num_perim_init == 0, tenta infill
            aneis_1 = gerar_infill_concentrico_poligonal(poligono_1, altura_camada, 0, largura_extrusao, sobreposicao_infill)
            pts_infill_1 = gerar_espiral_concentrica_poligonal(aneis_1, x_centro - largura_desejada_x/2, y_centro, out_to_in=True, centroid_x=x_centro, centroid_y=y_centro, espacamento=largura_extrusao * 0.95)
            if pts_infill_1:
                start_pt = pts_infill_1[0]
                steps.append(fc.Extruder(on=False))
                steps.append(fc.Point(x=start_pt.x, y=start_pt.y, z=altura_camada))
                steps.append(fc.Extruder(on=True))

    ultimo_era_espiral = False
    # --- LOOP DE CAMADAS ---
    for camada in range(num_camadas):
        if camada == 1:
            steps.append(fc.ManualGcode(text=f"; --- RESTAURANDO VELOCIDADE NORMAL (CAMADA 2) ---"))
            steps.append(fc.Printer(print_speed=velocidade_impressao, travel_speed=velocidade_travel))
            if aceleracao_impressao > 0:
                steps.append(fc.ManualGcode(text=f"M201 X{aceleracao_impressao} Y{aceleracao_impressao}"))

        z_atual = altura_camada + (camada * altura_camada)
        eh_par = (camada % 2 == 0)

        if MODO_LINHA_UNICA:
            # Define se esta camada é da base sólida maciça de fundo ou do nó celta de linha única
            if camada < NUM_CAMADAS_BASE_MACICA:
                # --- MODO BASE SÓLIDA MACIÇA NA LINHA ÚNICA (Opção A) ---
                # Calcular o deslocamento de inclinação radial
                if angulo_parede != 90.0:
                    delta_r = (z_atual - z_ref_vaso) / math.tan(math.radians(angulo_parede))
                else:
                    delta_r = 0.0

                r_0 = largura_desejada_x / 2
                fator_escala_z = 1.0 - (delta_r / r_0) if r_0 > 0 else 1.0

                silhueta_camada = affinity.scale(silhueta_base, xfact=fator_escala_z, yfact=fator_escala_z, origin=silhueta_base.centroid)

                # Geramos 1 perímetro de vedação externa e o infill concêntrico sólido
                pts_perim = gerar_perimetros_poligonais(1, silhueta_camada, z_atual, largura_extrusao * 0.95, get_last_point(steps)[0], get_last_point(steps)[1])
                aneis = gerar_infill_concentrico_poligonal(silhueta_camada, z_atual, 1, largura_extrusao, sobreposicao_infill)

                out_to_in = (camada % 2 == 0)
                lx, ly = get_last_point(steps)

                # Alternância de fluxo (infill/perímetro e fora-dentro/dentro-fora) para conexão contínua
                if not out_to_in:
                    # Dentro para fora: Infill primeiro, depois Perímetro
                    pts_infill = gerar_espiral_concentrica_poligonal(
                        aneis, lx, ly, out_to_in=False,
                        centroid_x=silhueta_camada.centroid.x,
                        centroid_y=silhueta_camada.centroid.y,
                        espacamento=largura_extrusao * 0.82
                    )
                    if pts_infill:
                        adicionar_caminho_seguro(steps, pts_infill, tipo='infill')
                        lx, ly = get_last_point(steps)

                    pts_perim_atual = gerar_perimetros_poligonais(1, silhueta_camada, z_atual, largura_extrusao * 0.95, lx, ly)
                    if pts_perim_atual:
                        adicionar_caminho_seguro(steps, pts_perim_atual, tipo='perimetro')
                else:
                    # Fora para dentro: Perímetro primeiro, depois Infill
                    if pts_perim:
                        adicionar_caminho_seguro(steps, pts_perim, tipo='perimetro')
                        lx, ly = get_last_point(steps)

                    pts_infill = gerar_espiral_concentrica_poligonal(
                        aneis, lx, ly, out_to_in=True,
                        centroid_x=silhueta_camada.centroid.x,
                        centroid_y=silhueta_camada.centroid.y,
                        espacamento=largura_extrusao * 0.82
                    )
                    if pts_infill:
                        adicionar_caminho_seguro(steps, pts_infill, tipo='infill')
                continue
            else:
                # --- MODO LINHA ÚNICA CONTÍNUA (Corpo do Nó Celta) ---
                # Aplica a variação dimensional radial de Z e a escala na geometria de linha
                if angulo_parede != 90.0:
                    delta_r = (z_atual - z_ref_vaso) / math.tan(math.radians(angulo_parede))
                else:
                    delta_r = 0.0

                r_0 = largura_desejada_x / 2
                fator_escala_z = 1.0 - (delta_r / r_0) if r_0 > 0 else 1.0

                # Apex Check
                if fator_escala_z <= 0.05:
                    steps.append(fc.ManualGcode(text=f"; --- APICE ALCANCADO: Parando na camada {camada} (Z={z_atual}mm) devido ao afunilamento total ---"))
                    print(f"-> Apice alcancado na camada {camada} (Z={z_atual}mm) devido ao afunilamento total!")
                    break

                linha_camada = affinity.scale(poligono_base, xfact=fator_escala_z, yfact=fator_escala_z, origin=poligono_base.centroid)

                # Converte a geometria Shapely para pontos FullControl
                pts_linha = []
                coords = list(linha_camada.coords)
                for c in coords:
                    pts_linha.append(fc.Point(x=c[0], y=c[1], z=z_atual))

                # Otimiza o início para conexões sem travels internos
                if linha_camada.is_ring and len(pts_linha) >= 3:
                    start_x, start_y = get_last_point(steps)
                    pts_linha = rotacionar_anel(pts_linha, start_x, start_y)
                else:
                    start_x, start_y = get_last_point(steps)
                    pts_linha = orientar_caminho(pts_linha, start_x, start_y)

                adicionar_caminho_seguro(steps, pts_linha)
                continue

        zona_ativa = obter_zona(camada)
        num_perimetros = zona_ativa.get('num_perimetros', 1)
        infill_percent = zona_ativa.get('infill_percent', 0.0)
        infill_pattern = zona_ativa.get('infill_pattern', 'zigzag')
        fluxo_perim_atual = zona_ativa.get('fluxo_perimetro', 100.0)
        fluxo_infill_atual = zona_ativa.get('fluxo_infill', 100.0)
        espiral = zona_ativa.get('espiral', False)

        # 1. Calcular o buffer offset de inclinação da camada atual
        if angulo_parede != 90.0:
            buffer_offset = - (z_atual - z_ref_vaso) / math.tan(math.radians(angulo_parede))
        else:
            buffer_offset = 0.0

        # Se num_perimetros == 0 nas camadas sólidas, expande a base em 2 perímetros extras
        if num_perimetros == 0:
            buffer_offset += 2 * (largura_extrusao * 0.95)

        poligono_camada = poligono_base
        if not math.isclose(buffer_offset, 0.0):
            poligono_camada = poligono_base.buffer(buffer_offset)

        # --- VERIFICAÇÃO DE FECHAMENTO DO ÁPICE (Apex Check) ---
        if poligono_camada.is_empty or poligono_camada.area < (largura_extrusao * 2)**2:
            steps.append(fc.ManualGcode(text=f"; --- APICE ALCANCADO: Parando na camada {camada} (Z={z_atual}mm) devido ao afunilamento total ---"))
            print(f"-> Apice alcancado na camada {camada} (Z={z_atual}mm) devido ao afunilamento total da geometria!")
            break

        if isinstance(poligono_camada, MultiPolygon):
            poligono_camada = max(poligono_camada.geoms, key=lambda p: p.area)

        # --- MODO ESPIRAL CONTÍNUA (Vase Mode) ---
        if espiral:
            steps.append(fc.ManualGcode(text="; --- ESPIRAL START ---"))

            # Identifica se é a camada de transição (primeira camada do vasemode)
            eh_transicao_vaso = not ultimo_era_espiral
            ultimo_era_espiral = True

            if eh_transicao_vaso:
                z_inicio = z_atual - altura_camada + transicao_vaso_z_offset
                fluxo_atual = transicao_vaso_fluxo
            else:
                z_inicio = z_atual - altura_camada
                fluxo_atual = fluxo_perim_atual

            steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_atual)}"))
            start_x, start_y = get_last_point(steps)
            pts_espiral = gerar_espiral_helicoidal_vaso(poligono_camada, z_inicio, z_atual, start_x, start_y)
            adicionar_caminho_seguro(steps, pts_espiral)
            continue
        else:
            ultimo_era_espiral = False
            steps.append(fc.ManualGcode(text="; --- ESPIRAL END ---"))

        # --- MODO TRADICIONAL DISCRETO (Base Sólida) ---
        if camada > 0:
            lx, ly = get_last_point(steps)
            steps.append(fc.Extruder(on=False))
            steps.append(fc.Point(x=lx, y=ly, z=z_atual))
            steps.append(fc.Extruder(on=True))

        # Alternar ordem de impressão do Infill concêntrico entre fora-dentro e dentro-fora
        out_to_in = (camada % 2 == 0)

        # 1. Se for de dentro para fora, imprime o Infill primeiro e os Perímetros depois
        if not out_to_in:
            # Infill Concêntrico
            if infill_percent > 0 and infill_pattern == 'concentric':
                steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_infill_atual)}"))
                aneis = gerar_infill_concentrico_poligonal(poligono_camada, z_atual, num_perimetros, largura_extrusao, sobreposicao_infill)
                lx, ly = get_last_point(steps)
                pts_infill = gerar_espiral_concentrica_poligonal(
                    aneis, lx, ly, out_to_in=False,
                    centroid_x=poligono_camada.centroid.x,
                    centroid_y=poligono_camada.centroid.y,
                    espacamento=largura_extrusao * 0.95
                )
                if pts_infill:
                    adicionar_caminho_seguro(steps, pts_infill, tipo='infill')

            # Perímetros
            if num_perimetros > 0:
                steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_perim_atual)}"))
                lx, ly = get_last_point(steps)
                pts_perim = gerar_perimetros_poligonais(num_perimetros, poligono_camada, z_atual, largura_extrusao * 0.95, lx, ly)
                adicionar_caminho_seguro(steps, pts_perim, tipo='perimetro')

        # 2. Se for de fora para dentro, imprime os Perímetros primeiro e o Infill depois
        else:
            # Perímetros
            if num_perimetros > 0:
                steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_perim_atual)}"))
                lx, ly = get_last_point(steps)
                pts_perim = gerar_perimetros_poligonais(num_perimetros, poligono_camada, z_atual, largura_extrusao * 0.95, lx, ly)
                adicionar_caminho_seguro(steps, pts_perim, tipo='perimetro')

            # Infill Concêntrico
            if infill_percent > 0 and infill_pattern == 'concentric':
                steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_infill_atual)}"))
                aneis = gerar_infill_concentrico_poligonal(poligono_camada, z_atual, num_perimetros, largura_extrusao, sobreposicao_infill)
                lx, ly = get_last_point(steps)
                pts_infill = gerar_espiral_concentrica_poligonal(
                    aneis, lx, ly, out_to_in=True,
                    centroid_x=poligono_camada.centroid.x,
                    centroid_y=poligono_camada.centroid.y,
                    espacamento=largura_extrusao * 0.95
                )
                if pts_infill:
                    adicionar_caminho_seguro(steps, pts_infill, tipo='infill')

    # --- Aplicação do Wipe Final (Limpeza/Arrasto do Bico) ---
    if wipe_final_ativo:
        # Encontra os dois últimos pontos de extrusão para determinar a direção
        pontos_extrusao = []
        for step in reversed(steps):
            if hasattr(step, 'x') and step.x is not None:
                pontos_extrusao.append(step)
                if len(pontos_extrusao) == 2:
                    break
        if len(pontos_extrusao) == 2:
            p_last, p_prev = pontos_extrusao[0], pontos_extrusao[1]
            dx = p_last.x - p_prev.x
            dy = p_last.y - p_prev.y
            d = math.hypot(dx, dy)
            if d > 0.1:
                x_wipe = p_last.x - (dx / d) * wipe_final_distancia
                y_wipe = p_last.y - (dy / d) * wipe_final_distancia
                z_wipe = p_last.z + wipe_final_subida_z
                steps.append(fc.Extruder(on=False))
                steps.append(fc.Point(x=x_wipe, y=y_wipe, z=z_wipe))
                steps.append(fc.ManualGcode(text="; --- WIPE FINAL EXECUTADO ---"))

    steps.append(fc.Extruder(on=False))

    # ==============================================================================
    # 6. GERAÇÃO E PÓS-PROCESSAMENTO DO G-CODE
    # ==============================================================================

    return steps

if __name__ == "__main__":
    config_teste = {
        "vetor_arquivo": "no-celta.dxf",
        "modo_linha_unica": True,
        "num_camadas_base_macica": 2
    }
    passos = gerar_passos_vetor(config_teste)
    import fullcontrol as fc
    fc.transform(passos, "gcode", fc.GcodeControls(printer_name="Community/Cliever CL2Pro", save_as="vetor_inclinado_solido", initialization_data={"primer": "no_primer", "dia_feed": 1.75, "extrusion_width": 3.0, "extrusion_height": 1.0}))
    print("\nG-code gerado como vetor_inclinado_solido.gcode")

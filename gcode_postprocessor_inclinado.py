#!/usr/bin/env python3
"""
Pós-Processador Inclinado: PrusaSlicer G-code → FullControl Base Sólida Inclinada

Lê um G-code de vase mode (PrusaSlicer), extrai o contorno da primeira camada,
gera uma base sólida via FullControl com infill + perímetros configuráveis,
adaptando radialmente as dimensões de cada camada de base para acompanhar 
o ângulo de parede da peça (pirâmides, cones, vasos expansivos),
e mescla os dois G-codes com ajuste de Z.

Uso:
    python gcode_postprocessor_inclinado.py input.gcode --z-ref 1.5 --camadas-base 3 --angulo-parede 80.0

Dependências:
    pip install shapely
"""

import argparse
import math
import re
import sys
import glob
import os
from pathlib import Path

import fullcontrol as fc
from shapely.geometry import Polygon, LineString, MultiLineString, MultiPolygon
from shapely.ops import unary_union
from shapely import affinity

# ==============================================================================
# CONFIGURAÇÃO PADRÃO
# ==============================================================================
# Ajuste as variáveis abaixo para configurar o comportamento padrão do script.

# --- Arquivo de Entrada ---
INPUT_GCODE = "Copo-Hexagono-torcido.gcode"  # Caminho do G-code de entrada do PrusaSlicer (vase mode)
OUTPUT_GCODE = ""                            # Caminho do arquivo de saída (deixe vazio para gerar {input}_com_base.gcode)

# --- Parâmetros Geométricos da Base ---
Z_REF = 2.0                                  # Altura Z máxima para extrair o contorno da base (mm)
CAMADAS_BASE = 2                             # Número de camadas sólidas da base
ALTURA_CAMADA = 2.0                          # Altura (espessura) de cada camada da base (mm)
LARGURA_EXTRUSAO = 3.0                       # Largura do filete de extrusão (mm)
NUM_PERIMETROS = 0                           # Número de perímetros na base (0 = apenas preenchimento)
ANGULO_PAREDE = 90.0                         # Ângulo da parede (graus) (90 = vertical, <90 = afunila para dentro, >90 = expande para fora)

# --- Preenchimento (Infill) ---
INFILL_PATTERN = "concentric"                # Padrão de infill: 'zigzag' ou 'concentric'
ANGULO_INFILL = 45.0                         # Ângulo base do infill em graus

# --- Parâmetros de Impressão ---
VELOCIDADE = 600.0                           # Velocidade de impressão da base (mm/min)
FLUXO = 100                                  # Fluxo de extrusão da base (%)
PRINTER_PROFILE = "Community/Cliever CL2Pro" # Perfil da impressora no FullControl


# ==============================================================================
# MÓDULO 1: PARSER DE G-CODE (PrusaSlicer)
# ==============================================================================

def detectar_modo_extrusao(filepath):
    """Detecta se o arquivo G-code usa extrusão absoluta (M82) ou relativa (M83)."""
    modo = 'absolute'
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            for _ in range(300):
                line = f.readline()
                if not line:
                    break
                stripped = line.strip()
                if not stripped or stripped.startswith(';'):
                    continue
                if ';' in stripped:
                    stripped = stripped[:stripped.index(';')].strip()
                tokens = stripped.split()
                if 'M82' in tokens:
                    modo = 'absolute'
                elif 'M83' in tokens:
                    modo = 'relative'
    except Exception as e:
        print(f"Aviso ao detectar modo de extrusao: {e}. Usando 'absolute' por padrao.")
    return modo


def parse_gcode_line(line):
    """Extrai coordenadas de uma linha G-code G0 ou G1."""
    stripped = line.strip()
    if not stripped or stripped.startswith(';'):
        return None
    if ';' in stripped:
        stripped = stripped[:stripped.index(';')].strip()
    match = re.match(r'^G([01])\s', stripped)
    if not match:
        return None
    coords = {'G': int(match.group(1))}
    for axis in ['X', 'Y', 'Z', 'E', 'F']:
        m = re.search(rf'{axis}([-\d.]+)', stripped)
        if m:
            coords[axis] = float(m.group(1))
    return coords


def parse_gcode_file(filepath):
    """Parseia um arquivo G-code do PrusaSlicer."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        all_lines = f.readlines()
    
    idx_start = None
    idx_end = None
    for i, line in enumerate(all_lines):
        stripped = line.strip()
        if stripped == ';STARTGCODE':
            idx_start = i
        elif stripped == ';ENDGCODE':
            idx_end = i
            break
            
    if idx_start is None:
        header_lines = []
        body_lines = all_lines
        footer_lines = []
    elif idx_end is None:
        header_lines = all_lines[:idx_start + 1]
        body_lines = all_lines[idx_start + 1:]
        footer_lines = []
    else:
        header_lines = all_lines[:idx_start + 1]
        body_lines = all_lines[idx_start + 1:idx_end]
        footer_lines = all_lines[idx_end:]
        
    idx_first_print = None
    for i, line in enumerate(body_lines):
        coords = parse_gcode_line(line)
        if coords and 'E' in coords and coords['E'] > 0:
            idx_first_print = i
            break
            
    if idx_first_print is not None and idx_first_print > 0:
        header_lines = header_lines + body_lines[:idx_first_print]
        body_lines = body_lines[idx_first_print:]
        
    primeiro_ponto = None
    z_atual = 0
    x_atual = None
    y_atual = None
    e_total = 0
    
    for line in body_lines:
        coords = parse_gcode_line(line)
        if coords is None:
            continue
        if 'Z' in coords:
            z_atual = coords['Z']
        if 'X' in coords:
            x_atual = coords['X']
        if 'Y' in coords:
            y_atual = coords['Y']
        if 'E' in coords and coords['E'] > 0:
            e_total += coords['E']
            if primeiro_ponto is None and e_total > 0 and x_atual is not None and y_atual is not None:
                primeiro_ponto = (x_atual, y_atual, z_atual)
                
    return header_lines, body_lines, footer_lines, primeiro_ponto


# ==============================================================================
# MÓDULO 2: EXTRATOR DE CONTORNO
# ==============================================================================

def extrair_contorno(body_lines, z_referencia):
    """Extrai os pontos do contorno (perímetro) até z_referencia."""
    pontos = []
    z_atual = 0
    x_atual = None
    y_atual = None
    
    for line in body_lines:
        coords = parse_gcode_line(line)
        if coords is None:
            continue
        if 'Z' in coords:
            z_atual = coords['Z']
            if z_atual > z_referencia + 0.01:
                break
        if 'X' in coords:
            x_atual = coords['X']
        if 'Y' in coords:
            y_atual = coords['Y']
        if (z_atual <= z_referencia + 0.01 and 
            'E' in coords and coords['E'] > 0 and
            x_atual is not None and y_atual is not None):
            pontos.append((x_atual, y_atual))
            
    if len(pontos) < 3:
        print(f"ERRO: Apenas {len(pontos)} pontos encontrados abaixo de Z={z_referencia}mm.")
        sys.exit(1)
        
    pontos_limpos = [pontos[0]]
    for p in pontos[1:]:
        if math.hypot(p[0] - pontos_limpos[-1][0], p[1] - pontos_limpos[-1][1]) > 0.01:
            pontos_limpos.append(p)
            
    if math.hypot(pontos_limpos[0][0] - pontos_limpos[-1][0], 
                  pontos_limpos[0][1] - pontos_limpos[-1][1]) > 0.1:
        pontos_limpos.append(pontos_limpos[0])
        
    try:
        poligono = Polygon(pontos_limpos)
        if not poligono.is_valid:
            poligono = poligono.buffer(0)
        if poligono.is_empty:
            print("ERRO: O polígono extraído é vazio após correção.")
            sys.exit(1)
        if isinstance(poligono, MultiPolygon):
            poligono = max(poligono.geoms, key=lambda p: p.area)
    except Exception as e:
        print(f"ERRO ao criar polígono: {e}")
        sys.exit(1)
        
    print(f"  Contorno extraido: {len(pontos_limpos)} pontos")
    print(f"  Area do contorno: {poligono.area:.1f} mm2")
    print(f"  Bounding box: {[f'{v:.1f}' for v in poligono.bounds]}")
    
    return poligono, pontos_limpos


# ==============================================================================
# MÓDULO 3: GERADOR DE BASE SÓLIDA (FullControl + Shapely)
# ==============================================================================

def get_last_point(steps):
    """Retorna as últimas coordenadas (x, y) da lista de steps."""
    for step in reversed(steps):
        if hasattr(step, 'x') and step.x is not None:
            return step.x, step.y
    return 0, 0


def adicionar_caminho_seguro(steps, pts):
    """Adiciona pontos à lista, fazendo travel se necessário."""
    if not pts:
        return
    lx, ly = get_last_point(steps)
    dist = math.hypot(pts[0].x - lx, pts[0].y - ly)
    if dist > 0.5:
        steps.append(fc.Extruder(on=False))
        steps.append(pts[0])
        steps.append(fc.Extruder(on=True))
        steps.extend(pts[1:])
    else:
        steps.extend(pts)


def orientar_caminho(pts, start_x, start_y):
    """Orienta a lista de pontos para começar mais perto da posição atual."""
    if not pts:
        return pts
    dist_start = math.hypot(pts[0].x - start_x, pts[0].y - start_y)
    dist_end = math.hypot(pts[-1].x - start_x, pts[-1].y - start_y)
    if dist_end < dist_start:
        pts.reverse()
    return pts


def alinhar_perimetro_com_slicer(pontos_perimetro, ponto_inicio_slicer):
    """Rotaciona a lista de pontos do perímetro para que o ÚLTIMO ponto
    seja o mais próximo possível do primeiro ponto do G-code do slicer.
    """
    if len(pontos_perimetro) < 3:
        return pontos_perimetro
    sx, sy = ponto_inicio_slicer
    loop = pontos_perimetro[:-1]
    dists = [math.hypot(p.x - sx, p.y - sy) for p in loop]
    idx_mais_proximo = dists.index(min(dists))
    idx_inicio = (idx_mais_proximo + 1) % len(loop)
    rotacionado = loop[idx_inicio:] + loop[:idx_inicio]
    rotacionado.append(fc.Point(x=rotacionado[0].x, y=rotacionado[0].y, z=rotacionado[0].z))
    return rotacionado


def polygon_to_points(polygon, z, resolucao_mm=1.0):
    """Converte um polígono Shapely em lista de fc.Point."""
    coords = list(polygon.exterior.coords)
    pts = []
    
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        dist = math.hypot(x2 - x1, y2 - y1)
        
        if dist > resolucao_mm * 2:
            num_seg = max(1, int(math.ceil(dist / resolucao_mm)))
            for j in range(num_seg):
                t = j / num_seg
                px = x1 + t * (x2 - x1)
                py = y1 + t * (y2 - y1)
                pts.append(fc.Point(x=px, y=py, z=z))
        else:
            pts.append(fc.Point(x=x1, y=y1, z=z))
            
    pts.append(fc.Point(x=pts[0].x, y=pts[0].y, z=z))
    return pts


def gerar_perimetros(poligono, z, num_perimetros, largura_extrusao, resolucao_mm=1.0):
    """Gera perímetros concêntricos usando Shapely buffer negativo."""
    perimetros = []
    for p in range(num_perimetros):
        if p == 0:
            offset = largura_extrusao / 2
        else:
            offset = largura_extrusao / 2 + p * (largura_extrusao * 0.95)
            
        poly_offset = poligono.buffer(-offset)
        if poly_offset.is_empty:
            break
        if isinstance(poly_offset, MultiPolygon):
            poly_offset = max(poly_offset.geoms, key=lambda p: p.area)
            
        pts = polygon_to_points(poly_offset, z, resolucao_mm)
        if len(pts) >= 3:
            perimetros.append(pts)
    return perimetros


def gerar_infill_zigzag(poligono, z, num_perimetros, largura_extrusao, 
                         angulo_graus, sobreposicao=0.5):
    """Gera infill zigzag dentro do polígono usando scanlines + Shapely intersection."""
    if num_perimetros > 0:
        offset_infill = largura_extrusao / 2 + (num_perimetros - 1) * (largura_extrusao * 0.95)
        offset_infill = offset_infill + largura_extrusao / 2 - sobreposicao
    else:
        offset_infill = largura_extrusao / 2 - sobreposicao
        
    poly_infill = poligono.buffer(-max(0, offset_infill))
    if poly_infill.is_empty:
        return []
    if isinstance(poly_infill, MultiPolygon):
        poly_infill = max(poly_infill.geoms, key=lambda p: p.area)
        
    espacamento = largura_extrusao * 0.95
    minx, miny, maxx, maxy = poly_infill.bounds
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2
    
    theta = -angulo_graus
    poly_rotated = affinity.rotate(poly_infill, theta, origin=(cx, cy))
    rminx, rminy, rmaxx, rmaxy = poly_rotated.bounds
    
    pts = []
    y_current = math.ceil(rminy / espacamento) * espacamento
    flip = False
    
    while y_current <= rmaxy + 1e-5:
        scan_line = LineString([(rminx - 1, y_current), (rmaxx + 1, y_current)])
        intersection = poly_rotated.intersection(scan_line)
        
        segments = []
        if isinstance(intersection, LineString) and not intersection.is_empty:
            segments.append(intersection)
        elif isinstance(intersection, MultiLineString):
            segments.extend(intersection.geoms)
            
        for seg in segments:
            if seg.is_empty or seg.length < 0.1:
                continue
            seg_coords = list(seg.coords)
            if flip:
                seg_coords.reverse()
            for sx, sy in seg_coords:
                dx = sx - cx
                dy = sy - cy
                angle_rad = math.radians(angulo_graus)
                rx = cx + dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
                ry = cy + dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
                pts.append(fc.Point(x=rx, y=ry, z=z))
                
        y_current += espacamento
        flip = not flip
        
    return pts


def gerar_infill_concentrico(poligono, z, num_perimetros, largura_extrusao, 
                              sobreposicao=0.5, resolucao_mm=1.0):
    """Gera infill concêntrico usando Shapely buffer iterativo."""
    if num_perimetros > 0:
        offset_base = largura_extrusao / 2 + (num_perimetros - 1) * (largura_extrusao * 0.95)
        offset_base = offset_base + largura_extrusao / 2 - sobreposicao
    else:
        offset_base = largura_extrusao / 2 - sobreposicao
        
    espacamento = largura_extrusao * 0.95
    aneis = []
    offset = offset_base + espacamento
    
    while True:
        poly_ring = poligono.buffer(-offset)
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
    """Rotaciona a lista de pontos de um loop fechado para iniciar no ponto mais próximo de (px, py)."""
    if len(anel) < 3:
        return anel
    loop = anel[:-1]
    dists = [math.hypot(p.x - px, p.y - py) for p in loop]
    idx = dists.index(min(dists))
    rotacionado = loop[idx:] + loop[:idx]
    rotacionado.append(fc.Point(x=rotacionado[0].x, y=rotacionado[0].y, z=rotacionado[0].z))
    return rotacionado


def gerar_espiral_concentrica_poligonal(aneis, start_x, start_y, out_to_in=True, centroid_x=0.0, centroid_y=0.0, largura_extrusao=3.0):
    """Conecta múltiplos anéis concêntricos em uma única espiral poligonal contínua de Arquimedes."""
    if not aneis:
        return []
    aneis_validos = [a for a in aneis if len(a) >= 3]
    if not aneis_validos:
        return []
        
    # Inverter a ordem dos anéis se a impressão for de dentro para fora
    if not out_to_in:
        aneis_validos.reverse()
        
    pts_espiral = []
    lx, ly = start_x, start_y
    cx, cy = centroid_x, centroid_y
    espacamento = largura_extrusao * 0.95
    
    for i in range(len(aneis_validos)):
        # Rotaciona o anel atual para começar o mais próximo possível do ponto final anterior
        anel_atual = rotacionar_anel(aneis_validos[i], lx, ly)
        n_pts = len(anel_atual)
        
        # Se for a última volta da espiral, imprimimos por completo sem encolher/expandir mais
        if i == len(aneis_validos) - 1:
            pts_espiral.extend(anel_atual)
            lx, ly = anel_atual[-1].x, anel_atual[-1].y
        else:
            # Transiciona continuamente ao longo de toda a volta (espiral de Arquimedes poligonal)
            for j in range(n_pts):
                p = anel_atual[j]
                t = j / (n_pts - 1) if n_pts > 1 else 1.0
                
                dx = p.x - cx
                dy = p.y - cy
                d = math.hypot(dx, dy)
                if d < 0.1:
                    pts_espiral.append(p)
                    continue
                    
                # Encolhe se for de fora para dentro, expande se for de dentro para fora
                if out_to_in:
                    factor = 1.0 - t * (espacamento / d)
                else:
                    factor = 1.0 + t * (espacamento / d)
                    
                rx = cx + dx * factor
                ry = cy + dy * factor
                pts_espiral.append(fc.Point(x=rx, y=ry, z=p.z))
                
            lx, ly = pts_espiral[-1].x, pts_espiral[-1].y
            
    return pts_espiral


def gerar_base_solida(poligono, args, primeiro_ponto_slicer):
    """Gera a base sólida completa via FullControl com compensação de ângulo de parede."""
    steps = []
    
    # Inicialização
    steps.append(fc.Printer(print_speed=args.velocidade, travel_speed=3000))
    steps.append(fc.ManualGcode(text="M204 P500 T500"))
    steps.append(fc.ExtrusionGeometry(
        area_model='rectangle', 
        width=args.largura_extrusao, 
        height=args.altura_camada
    ))
    
    # Purga
    steps.append(fc.ManualGcode(text="; --- PURGA PERSONALIZADA ---"))
    steps.append(fc.ManualGcode(text="G1 E25 F100 ; Purga"))
    steps.append(fc.ManualGcode(text="G92 E0.0"))
    steps.append(fc.ManualGcode(text=f"M221 S{args.fluxo}"))
    
    z_offset = args.camadas_base * args.altura_camada
    
    # Calcular o polígono da primeira camada para o travel inicial
    z_atual_1 = args.altura_camada
    if math.isclose(args.angulo_parede, 90.0) or args.angulo_parede <= 0:
        buffer_offset_1 = 0.0
    else:
        theta_rad = math.radians(args.angulo_parede)
        buffer_offset_1 = (z_offset - z_atual_1) / math.tan(theta_rad)
        
    # Se num_perimetros == 0, expandimos a primeira camada da base sólida em 1 perímetro extra
    if args.num_perimetros == 0:
        buffer_offset_1 += args.largura_extrusao * 0.95
        
    poligono_camada_1 = poligono
    if not math.isclose(buffer_offset_1, 0.0):
        poligono_camada_1 = poligono.buffer(buffer_offset_1)
        if isinstance(poligono_camada_1, MultiPolygon):
            poligono_camada_1 = max(poligono_camada_1.geoms, key=lambda p: p.area)
            
    # Travel para o início do primeiro perímetro/infill
    primeiro_perim = gerar_perimetros(poligono_camada_1, args.altura_camada, 
                                       min(1, args.num_perimetros), 
                                       args.largura_extrusao)
    if primeiro_perim and primeiro_perim[0]:
        start_pt = primeiro_perim[0][0]
        steps.append(fc.Extruder(on=False))
        steps.append(fc.Point(x=start_pt.x, y=start_pt.y, z=args.altura_camada))
        steps.append(fc.Extruder(on=True))
    else:
        # Se não houver perímetros, tentar o infill
        pts_infill_1 = []
        if args.infill_pattern == 'zigzag':
            pts_infill_1 = gerar_infill_zigzag(
                poligono_camada_1, args.altura_camada, args.num_perimetros, args.largura_extrusao,
                args.angulo_infill, sobreposicao=0.5
            )
        elif args.infill_pattern == 'concentric':
            aneis_1 = gerar_infill_concentrico(
                poligono_camada_1, args.altura_camada, args.num_perimetros, args.largura_extrusao,
                sobreposicao=0.5
            )
            # A primeira camada da base sólida (camada 0) sempre inicia de fora para dentro (out_to_in = True)
            pts_infill_1 = gerar_espiral_concentrica_poligonal(
                aneis_1, 0, 0, out_to_in=True,
                centroid_x=poligono_camada_1.centroid.x,
                centroid_y=poligono_camada_1.centroid.y,
                largura_extrusao=args.largura_extrusao
            )
        
        if pts_infill_1:
            start_pt = pts_infill_1[0]
            steps.append(fc.Extruder(on=False))
            steps.append(fc.Point(x=start_pt.x, y=start_pt.y, z=args.altura_camada))
            steps.append(fc.Extruder(on=True))
            
    # Gerar cada camada da base
    for camada in range(args.camadas_base):
        z_atual = args.altura_camada + (camada * args.altura_camada)
        eh_par = (camada % 2 == 0)
        eh_ultima_camada = (camada == args.camadas_base - 1)
        
        # Calcular o buffer offset para a inclinação da parede nesta camada
        if math.isclose(args.angulo_parede, 90.0) or args.angulo_parede <= 0:
            buffer_offset = 0.0
        else:
            theta_rad = math.radians(args.angulo_parede)
            buffer_offset = (z_offset - z_atual) / math.tan(theta_rad)
            
        # Se num_perimetros == 0, expandimos a base sólida em 1 perímetro extra
        if args.num_perimetros == 0:
            buffer_offset += args.largura_extrusao * 0.95
            
        poligono_camada = poligono
        if not math.isclose(buffer_offset, 0.0):
            poligono_camada = poligono.buffer(buffer_offset)
            if poligono_camada.is_empty:
                print(f"  [Aviso] Camada {camada} (Z={z_atual}mm) encolheu completamente e foi pulada (buffer_offset={buffer_offset:.2f}mm).")
                continue
            if isinstance(poligono_camada, MultiPolygon):
                poligono_camada = max(poligono_camada.geoms, key=lambda p: p.area)
                
        # Subir Z se não for a primeira camada
        if camada > 0:
            lx, ly = get_last_point(steps)
            steps.append(fc.Extruder(on=False))
            steps.append(fc.Point(x=lx, y=ly, z=z_atual))
            steps.append(fc.Extruder(on=True))
            
        # --- PERÍMETROS ---
        if args.num_perimetros > 0:
            perimetros = gerar_perimetros(poligono_camada, z_atual, args.num_perimetros, 
                                          args.largura_extrusao)
            
            for i, pts_perim in enumerate(perimetros):
                eh_perim_externo_ultima = (eh_ultima_camada and i == 0)
                if eh_perim_externo_ultima and primeiro_ponto_slicer:
                    pts_perim = alinhar_perimetro_com_slicer(
                        pts_perim, 
                        (primeiro_ponto_slicer[0], primeiro_ponto_slicer[1])
                    )
                lx, ly = get_last_point(steps)
                pts_perim = orientar_caminho(pts_perim, lx, ly)
                adicionar_caminho_seguro(steps, pts_perim)
                
        # --- INFILL ---
        angulo_atual = args.angulo_infill if eh_par else -args.angulo_infill
        
        if args.infill_pattern == 'zigzag':
            pts_infill = gerar_infill_zigzag(
                poligono_camada, z_atual, args.num_perimetros, args.largura_extrusao,
                angulo_atual, sobreposicao=0.5
            )
            lx, ly = get_last_point(steps)
            pts_infill = orientar_caminho(pts_infill, lx, ly)
            adicionar_caminho_seguro(steps, pts_infill)
            
        elif args.infill_pattern == 'concentric':
            # Alterna a direção da espiral entre fora-dentro (True) e dentro-fora (False) a cada camada
            out_to_in = (camada % 2 == 0)
            
            aneis = gerar_infill_concentrico(
                poligono_camada, z_atual, args.num_perimetros, args.largura_extrusao,
                sobreposicao=0.5
            )
            lx, ly = get_last_point(steps)
            pts_infill = gerar_espiral_concentrica_poligonal(
                aneis, lx, ly, out_to_in=out_to_in,
                centroid_x=poligono_camada.centroid.x,
                centroid_y=poligono_camada.centroid.y,
                largura_extrusao=args.largura_extrusao
            )
            if pts_infill:
                adicionar_caminho_seguro(steps, pts_infill)
                
    steps.append(fc.Extruder(on=False))
    return steps


# ==============================================================================
# MÓDULO 4: MESCLADOR DE G-CODES
# ==============================================================================

def ajustar_z_gcode(body_lines, z_offset):
    """Adiciona z_offset a todas as coordenadas Z nas linhas do corpo do G-code."""
    resultado = []
    for line in body_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(';'):
            resultado.append(line)
            continue
        if re.match(r'^G[01]\s', stripped):
            m = re.search(r'Z([-\d.]+)', stripped)
            if m:
                z_original = float(m.group(1))
                z_novo = z_original + z_offset
                line = re.sub(r'Z[-\d.]+', f'Z{z_novo:.3f}', line)
        resultado.append(line)
    return resultado


def mesclar_gcodes(steps_base, body_lines_slicer, footer_lines_slicer, 
                    z_offset, args, modo_extrusao):
    """Gera o G-code final mesclado."""
    relative_e = (modo_extrusao == 'relative')
    
    gcode_base = fc.transform(steps_base, 'gcode', fc.GcodeControls(
        printer_name=args.printer,
        initialization_data={
            'primer': 'no_primer',
            'dia_feed': 1.75,
            'extrusion_width': args.largura_extrusao,
            'extrusion_height': args.altura_camada,
            'relative_e': relative_e
        }
    ))
    
    body_ajustado = ajustar_z_gcode(body_lines_slicer, z_offset)
    linhas_base = gcode_base.split('\n')
    
    idx_end_base = None
    for i, line in enumerate(linhas_base):
        if line.strip() == ';ENDGCODE':
            idx_end_base = i
            break
            
    if idx_end_base is not None:
        linhas_base_corpo = linhas_base[:idx_end_base]
    else:
        linhas_base_corpo = linhas_base
        
    linhas_base_corpo.append('')
    linhas_base_corpo.append('; ============================================')
    linhas_base_corpo.append('; TRANSICAO: Base FullControl -> Paredes Slicer')
    linhas_base_corpo.append(f'; Z offset aplicado: +{z_offset:.3f} mm')
    linhas_base_corpo.append(f'; Angulo de parede configurado: {args.angulo_parede:.1f} graus')
    linhas_base_corpo.append(f'; Restaurando modo de extrusao do slicer: {modo_extrusao.upper()}')
    linhas_base_corpo.append('; ============================================')
    
    if modo_extrusao == 'absolute':
        linhas_base_corpo.append('M82 ; modo de extrusao absoluta')
    else:
        linhas_base_corpo.append('M83 ; modo de extrusao relativa')
        
    linhas_base_corpo.append('G92 E0.0 ; resetar extrusor')
    linhas_base_corpo.append('')
    
    corpo_slicer = ''.join(body_ajustado)
    footer = ''.join(footer_lines_slicer)
    gcode_final = '\n'.join(linhas_base_corpo) + '\n' + corpo_slicer + footer
    return gcode_final


# ==============================================================================
# MÓDULO 5: PÓS-PROCESSAMENTO (limpeza de comentários longos)
# ==============================================================================

def limpar_gcode(gcode_text):
    """Remove comentários desnecessários para compatibilidade com firmware."""
    linhas = gcode_text.split('\n')
    linhas_limpas = []
    
    for linha in linhas:
        linha = linha.rstrip('\r\n')
        if ';' in linha and not linha.lstrip().startswith(';'):
            linha = linha[:linha.index(';')].rstrip()
        elif linha.lstrip().startswith(';'):
            stripped = linha.strip()
            if stripped in (';STARTGCODE', ';ENDGCODE') or stripped.startswith('; ==='):
                pass
            elif stripped.startswith('; TRANSICAO') or stripped.startswith('; Z') or stripped.startswith('; Restaurando') or stripped.startswith('; Angulo'):
                pass
            else:
                continue
        if linha:
            linhas_limpas.append(linha)
            
    return '\n'.join(linhas_limpas) + '\n'


# ==============================================================================
# MÓDULO 6: CLI (argparse)
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Pós-processador Inclinado: Adiciona base sólida inclinada (FullControl) a G-code vase mode (PrusaSlicer)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python gcode_postprocessor_inclinado.py vaso.gcode --z-ref 1.5 --camadas-base 3 --angulo-parede 80.0
  python gcode_postprocessor_inclinado.py vaso.gcode --z-ref 1.5 --camadas-base 2 --infill-pattern concentric --angulo-parede 105.0
        """
    )
    
    parser.add_argument('input', type=str, nargs='?', default=INPUT_GCODE,
                        help=f'Caminho do G-code do PrusaSlicer (vase mode) (default: {INPUT_GCODE if INPUT_GCODE else "Nenhum"})')
    
    parser.add_argument('--z-ref', type=float, default=Z_REF,
                        help=f'Altura Z de referência para extrair o contorno (mm) (default: {Z_REF})')
    
    parser.add_argument('--camadas-base', type=int, default=CAMADAS_BASE,
                        help=f'Número de camadas sólidas na base (default: {CAMADAS_BASE})')
    
    parser.add_argument('--largura-extrusao', type=float, default=LARGURA_EXTRUSAO,
                        help=f'Largura do filete de extrusão (mm) (default: {LARGURA_EXTRUSAO})')
    
    parser.add_argument('--altura-camada', type=float, default=ALTURA_CAMADA,
                        help=f'Altura de cada camada da base (mm) (default: {ALTURA_CAMADA})')
    
    parser.add_argument('--num-perimetros', type=int, default=NUM_PERIMETROS,
                        help=f'Número de perímetros na base (0 = só infill) (default: {NUM_PERIMETROS})')
    
    parser.add_argument('--angulo-parede', type=float, default=ANGULO_PAREDE,
                        help=f'Angulo de parede da peca em graus (90 = vertical, <90 = afunila para dentro, >90 = expande para fora) (default: {ANGULO_PAREDE})')
    
    parser.add_argument('--infill-pattern', type=str, default=INFILL_PATTERN,
                        choices=['zigzag', 'concentric'],
                        help=f'Padrão de preenchimento da base (default: {INFILL_PATTERN})')
    
    parser.add_argument('--angulo-infill', type=float, default=ANGULO_INFILL,
                        help=f'Ângulo base do infill em graus (default: {ANGULO_INFILL})')
    
    parser.add_argument('--velocidade', type=float, default=VELOCIDADE,
                        help=f'Velocidade de impressão da base em mm/min (default: {VELOCIDADE})')
    
    parser.add_argument('--fluxo', type=int, default=FLUXO,
                        help=f'Fluxo de extrusão em %% (default: {FLUXO})')
    
    parser.add_argument('--output', type=str, default=None if not OUTPUT_GCODE else OUTPUT_GCODE,
                        help=f'Caminho do arquivo de saída (default: {OUTPUT_GCODE if OUTPUT_GCODE else "{input}_com_base.gcode"})')
    
    parser.add_argument('--printer', type=str, default=PRINTER_PROFILE,
                        help=f'Perfil de impressora FullControl (default: {PRINTER_PROFILE})')
    
    args = parser.parse_args()
    
    if not args.input:
        print("\n" + "="*60)
        print("  ERRO: Nenhum arquivo G-code de entrada foi fornecido!")
        print("="*60)
        print("Você pode fornecer o arquivo de duas formas:")
        print("  1. Configurando a variável 'INPUT_GCODE' no topo deste script Python.")
        print("  2. Passando o caminho do arquivo por linha de comando:")
        print("     python gcode_postprocessor_inclinado.py seu_arquivo.gcode")
        print("\nPara ver todas as opções disponíveis, use:")
        print("     python gcode_postprocessor_inclinado.py --help")
        print("="*60)
        sys.exit(1)
        
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERRO: Arquivo de entrada não encontrado: {args.input}")
        sys.exit(1)
        
    if args.output is None:
        args.output = str(input_path.with_suffix('')) + '_com_base_inclinada.gcode'
        
    modo_extrusao = detectar_modo_extrusao(args.input)
    
    print("=" * 60)
    print("  Pos-Processador Inclinado: PrusaSlicer -> FullControl Base Solida")
    print("=" * 60)
    print(f"\n  Arquivo de entrada: {args.input}")
    print(f"  Modo de extrusao:   {modo_extrusao.upper()}")
    print(f"  Z referencia:       {args.z_ref} mm")
    print(f"  Camadas da base:    {args.camadas_base}")
    print(f"  Largura extrusao:   {args.largura_extrusao} mm")
    print(f"  Altura camada:      {args.altura_camada} mm")
    print(f"  Perimetros:         {args.num_perimetros}")
    print(f"  Angulo de parede:   {args.angulo_parede} graus")
    print(f"  Infill:             {args.infill_pattern}")
    print(f"  Angulo infill:      {args.angulo_infill} graus")
    print(f"  Velocidade:         {args.velocidade} mm/min")
    print(f"  Fluxo:              {args.fluxo}%")
    print(f"  Impressora:         {args.printer}")
    print()
    
    # Etapa 1: Parsear G-code
    print("[1/5] Parseando G-code do PrusaSlicer...")
    header, body, footer, primeiro_ponto = parse_gcode_file(args.input)
    print(f"  Header: {len(header)} linhas")
    print(f"  Corpo:  {len(body)} linhas")
    print(f"  Footer: {len(footer)} linhas")
    if primeiro_ponto:
        print(f"  Primeiro ponto de extrusao: X={primeiro_ponto[0]:.2f} Y={primeiro_ponto[1]:.2f} Z={primeiro_ponto[2]:.2f}")
    else:
        print("  AVISO: Nenhum ponto de extrusao encontrado!")
        
    # Etapa 2: Extrair contorno
    print(f"\n[2/5] Extraindo contorno (Z <= {args.z_ref} mm)...")
    poligono, pontos_contorno = extrair_contorno(body, args.z_ref)
    
    # Etapa 3: Gerar base sólida
    print(f"\n[3/5] Gerando base solida inclinada ({args.camadas_base} camadas)...")
    steps_base = gerar_base_solida(poligono, args, primeiro_ponto)
    print(f"  Steps FullControl gerados: {len(steps_base)}")
    
    # Etapa 4: Mesclar G-codes
    z_offset = args.camadas_base * args.altura_camada
    print(f"\n[4/5] Mesclando G-codes (Z offset: +{z_offset:.1f} mm)...")
    gcode_final = mesclar_gcodes(steps_base, body, footer, z_offset, args, modo_extrusao)
    
    # Etapa 5: Limpeza e salvamento
    print(f"\n[5/5] Limpando e salvando...")
    gcode_final = limpar_gcode(gcode_final)
    
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(gcode_final)
        
    num_linhas = gcode_final.count('\n')
    print(f"\n  [OK] G-code salvo: {args.output}")
    print(f"  [OK] Total de linhas: {num_linhas}")
    print(f"  [OK] Altura da base: {z_offset:.1f} mm")
    print(f"  [OK] Altura total estimada: {z_offset + (primeiro_ponto[2] if primeiro_ponto else 0):.1f} mm+")
    print("\n" + "=" * 60)
    print("  Concluido com sucesso!")
    print("=" * 60)


if __name__ == '__main__':
    main()

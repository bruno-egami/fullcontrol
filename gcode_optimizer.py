#!/usr/bin/env python3
"""
Otimizador de G-code: PrusaSlicer → Percurso Otimizado (FullControl Principles)

Lê um G-code gerado pelo PrusaSlicer (sem vase mode, 1+ perímetro, sem infill),
extrai as geometrias dos perímetros por camada, e gera um novo G-code com:
  - Percurso otimizado (contínuo, sem retracts, mínimo travel)
  - Perímetros e infill customizáveis
  - Mesmas alturas de camada do slicer original

Requisitos do G-code de entrada:
  - PrusaSlicer com "Verbose G-code" habilitado (Print Settings > Output options)
  - Arc fitting desabilitado (apenas segmentos lineares G0/G1)
  - Recomendado: 1 perímetro, 0 infill (o otimizador regenera perímetros/infill)

Uso:
    python gcode_optimizer.py modelo.gcode
    python gcode_optimizer.py modelo.gcode --num-perimetros 2 --infill-pattern concentric
    python gcode_optimizer.py modelo.gcode --infill-pattern zigzag --angulo-infill 45

Dependências:
    pip install shapely
"""

import argparse
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional

from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from shapely import affinity

# ==============================================================================
# CONFIGURAÇÃO PADRÃO
# ==============================================================================
# Ajuste estas variáveis para configurar o comportamento padrão do script.
# Todos os valores podem ser sobrescritos pela linha de comando.

# --- Arquivo de Entrada ---
INPUT_GCODE = ""                     # Caminho do G-code de entrada (PrusaSlicer)
OUTPUT_GCODE = ""                    # Caminho de saída (vazio = {input}_otimizado.gcode)

# --- Parâmetros de Extrusão ---
LARGURA_EXTRUSAO = 3.0               # Largura do filete de extrusão (mm)
ALTURA_CAMADA = 0.0                  # Altura de camada (mm). 0 = auto-detect do G-code
DIAMETRO_FILAMENTO = 1.75            # Diâmetro do filamento/pistão (mm)
NUM_PERIMETROS = 1                   # Número total de perímetros (>= 1 = o original + extras)

# --- Infill ---
INFILL_PATTERN = "none"              # Padrão: 'none', 'concentric', 'zigzag'
INFILL_PERCENT = 100.0               # Densidade do infill (%)
ANGULO_INFILL = 45.0                 # Ângulo base do infill zigzag (graus)
SOBREPOSICAO_INFILL = 0.5            # Sobreposição infill↔perímetro (mm)

# --- Velocidades ---
VELOCIDADE = 600.0                   # Velocidade de impressão (mm/min)
VELOCIDADE_TRAVEL = 3000.0           # Velocidade de travel (mm/min)

# --- Fluxo ---
FLUXO = 100                          # Fluxo de extrusão (%)

# --- Priming (Clay DIW) ---
PRIMING_ATIVO = True                 # Habilita priming automático após travels
PRIMING_QUANTIDADE = 10.0            # Quantidade extra de material (mm)
PRIMING_VELOCIDADE = 100.0           # Velocidade de priming (mm/min)



# ==============================================================================
# ESTRUTURAS DE DADOS
# ==============================================================================

@dataclass
class Contorno:
    """Um contorno (perímetro) extraído do G-code."""
    pontos: List[Tuple[float, float]]  # [(x, y), ...]
    tipo: str = "external_perimeter"
    fechado: bool = False

@dataclass
class Camada:
    """Informações de uma camada extraída do G-code."""
    z: float
    altura: float = 0.0               # Delta Z em relação à camada anterior
    contornos: List[Contorno] = field(default_factory=list)


# ==============================================================================
# MÓDULO 1: PARSER DE G-CODE PRUSASLICER
# ==============================================================================

def parse_gcode_line(line):
    """Extrai coordenadas de uma linha G-code G0 ou G1.

    Returns:
        dict com chaves possíveis: 'G', 'X', 'Y', 'Z', 'E', 'F'
        ou None se não for uma linha de movimento.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith(';'):
        return None

    # Remove comentários inline
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


def detectar_modo_extrusao(lines):
    """Detecta se o G-code usa extrusão absoluta (M82) ou relativa (M83).

    Busca nas primeiras 300 linhas. Retorna 'absolute' ou 'relative'.
    """
    modo = 'relative'  # padrão PrusaSlicer
    for line in lines[:300]:
        stripped = line.strip()
        if stripped.startswith(';'):
            continue
        if ';' in stripped:
            stripped = stripped[:stripped.index(';')].strip()
        tokens = stripped.split()
        if 'M82' in tokens:
            modo = 'absolute'
        elif 'M83' in tokens:
            modo = 'relative'
    return modo


def detectar_parametros_slicer(lines):
    """Detecta parâmetros do slicer a partir dos comentários do G-code.

    PrusaSlicer adiciona configurações como:
        ; layer_height = 0.2
        ; nozzle_diameter = 0.4
        ; filament_diameter = 1.75

    Returns:
        dict com parâmetros detectados.
    """
    params_raw = {}
    # PrusaSlicer coloca configurações nas últimas ~200 linhas
    for line in lines[-300:]:
        stripped = line.strip()
        if not stripped.startswith(';'):
            continue
        m = re.match(r'^;\s*([\w_]+)\s*=\s*(.+)$', stripped)
        if m:
            params_raw[m.group(1).strip()] = m.group(2).strip()

    result = {}

    # Extrair parâmetros específicos
    for key, dest in [
        ('layer_height', 'altura_camada'),
        ('first_layer_height', 'primeira_camada_altura'),
    ]:
        if key in params_raw:
            try:
                result[dest] = float(params_raw[key])
            except ValueError:
                pass

    # Largura de extrusão (preferir extrusion_width sobre nozzle_diameter)
    if 'extrusion_width' in params_raw:
        val = params_raw['extrusion_width']
        if '%' not in val:
            try:
                result['largura_extrusao'] = float(val)
            except ValueError:
                pass
    elif 'nozzle_diameter' in params_raw:
        try:
            result['largura_extrusao'] = float(params_raw['nozzle_diameter'])
        except ValueError:
            pass

    if 'filament_diameter' in params_raw:
        try:
            result['diametro_filamento'] = float(params_raw['filament_diameter'])
        except ValueError:
            pass

    return result


def extrair_header_body_footer(all_lines):
    """Extrai header, body (camadas imprimíveis) e footer do G-code.

    Suporta:
      1. Marcadores ;STARTGCODE / ;ENDGCODE (configuração customizada do usuário)
      2. Marcadores ;LAYER_CHANGE (PrusaSlicer verbose padrão)
      3. Fallback: detecção por primeira/última extrusão

    Returns:
        (header_lines, body_lines, footer_lines)
    """
    idx_startgcode = None
    idx_endgcode = None
    idx_first_layer = None

    for i, line in enumerate(all_lines):
        stripped = line.strip()
        if stripped == ';STARTGCODE' and idx_startgcode is None:
            idx_startgcode = i
        elif stripped == ';ENDGCODE' and idx_endgcode is None:
            idx_endgcode = i
        elif stripped == ';LAYER_CHANGE' and idx_first_layer is None:
            idx_first_layer = i

    # --- Estratégia 1: ;STARTGCODE / ;ENDGCODE ---
    if idx_startgcode is not None:
        header_end = idx_startgcode + 1

        # Incluir comandos de inicialização (G28, M83, etc.) no header
        # Tudo até o primeiro G1 com E > 0 pertence ao header
        for i in range(header_end, len(all_lines)):
            coords = parse_gcode_line(all_lines[i])
            if coords and 'E' in coords and coords['E'] > 0:
                header_end = i
                break

        if idx_endgcode is not None:
            return all_lines[:header_end], all_lines[header_end:idx_endgcode], all_lines[idx_endgcode:]
        else:
            return all_lines[:header_end], all_lines[header_end:], []

    # --- Estratégia 2: ;LAYER_CHANGE ---
    if idx_first_layer is not None:
        # Footer: tudo após a última extrusão
        idx_last_ext = len(all_lines)
        for i in range(len(all_lines) - 1, idx_first_layer, -1):
            coords = parse_gcode_line(all_lines[i])
            if coords and 'E' in coords:
                idx_last_ext = i + 1
                break

        return (all_lines[:idx_first_layer],
                all_lines[idx_first_layer:idx_last_ext],
                all_lines[idx_last_ext:])

    # --- Estratégia 3: Fallback ---
    idx_first_ext = 0
    idx_last_ext = len(all_lines)

    for i, line in enumerate(all_lines):
        coords = parse_gcode_line(line)
        if coords and 'E' in coords and coords.get('E', 0) > 0:
            idx_first_ext = i
            break

    for i in range(len(all_lines) - 1, -1, -1):
        coords = parse_gcode_line(all_lines[i])
        if coords and 'E' in coords:
            idx_last_ext = i + 1
            break

    return all_lines[:idx_first_ext], all_lines[idx_first_ext:idx_last_ext], all_lines[idx_last_ext:]


def extrair_camadas(body_lines, modo_extrusao):
    """Extrai camadas estruturadas do corpo do G-code.

    Usa marcadores ;LAYER_CHANGE se disponíveis, caso contrário detecta
    mudanças de Z. Agrupa segmentos de extrusão em contornos, separados
    por movimentos de travel (G0).

    Args:
        body_lines: linhas do corpo do G-code
        modo_extrusao: 'absolute' ou 'relative'

    Returns:
        List[Camada]
    """
    camadas = []

    # Estado de rastreamento
    z_atual = 0.0
    x_atual = 0.0
    y_atual = 0.0
    e_anterior = 0.0

    # Acumuladores da camada corrente
    contorno_atual_pontos = []
    contornos_camada = []
    z_camada = 0.0
    ponto_inicio_contorno = None  # posição do último G0 (início do próximo contorno)

    # Tipo de extrusão atual (do marcador ;TYPE:)
    tipo_atual = "external_perimeter"

    # Tipos a ignorar (não fazem parte da geometria principal)
    tipos_ignorar = {'skirt', 'skirt/brim', 'brim',
                     'support_material', 'support_material_interface',
                     'wipe_tower', 'custom'}
    tipo_ignorar_ativo = False

    # Detectar se há marcadores verbose
    tem_markers = any(';LAYER_CHANGE' in line for line in body_lines[:200])
    layer_started = False

    def finalizar_contorno():
        """Salva o contorno atual se tiver pontos suficientes."""
        nonlocal contorno_atual_pontos, ponto_inicio_contorno
        if len(contorno_atual_pontos) >= 3:
            # Verificar se é loop fechado
            d = math.hypot(
                contorno_atual_pontos[-1][0] - contorno_atual_pontos[0][0],
                contorno_atual_pontos[-1][1] - contorno_atual_pontos[0][1]
            )
            fechado = d < 1.0  # tolerância 1mm

            contornos_camada.append(Contorno(
                pontos=list(contorno_atual_pontos),
                tipo=tipo_atual,
                fechado=fechado
            ))
        contorno_atual_pontos = []
        ponto_inicio_contorno = None

    def finalizar_camada():
        """Salva a camada atual."""
        nonlocal contornos_camada
        finalizar_contorno()
        if contornos_camada:
            # Calcular altura da camada
            if camadas:
                altura = z_camada - camadas[-1].z
                if altura <= 0.001:
                    altura = camadas[-1].altura  # Repetir altura anterior
            else:
                altura = z_camada  # Primeira camada

            camadas.append(Camada(
                z=z_camada,
                altura=max(0.01, altura),
                contornos=list(contornos_camada),
            ))
        contornos_camada = []

    for line in body_lines:
        stripped = line.strip()

        # --- Marcadores PrusaSlicer ---
        if stripped.startswith(';TYPE:'):
            tipo_str = stripped[6:].strip().lower().replace(' ', '_')
            if tipo_str in tipos_ignorar:
                tipo_ignorar_ativo = True
                finalizar_contorno()
            else:
                tipo_ignorar_ativo = False
                tipo_atual = tipo_str
            continue

        if stripped == ';LAYER_CHANGE':
            if layer_started:
                finalizar_camada()
            layer_started = True
            continue

        if stripped.startswith(';Z:'):
            try:
                z_camada = float(stripped[3:])
            except ValueError:
                pass
            continue

        if stripped.startswith(';HEIGHT:'):
            continue  # Informativo; Z é rastreado pelos movimentos

        # Ignorar outros comentários
        if stripped.startswith(';'):
            continue

        # --- Parse de movimento ---
        coords = parse_gcode_line(stripped)
        if coords is None:
            continue

        # Atualizar Z
        if 'Z' in coords:
            novo_z = coords['Z']
            # Fallback: detectar mudança de camada por Z (sem markers verbose)
            if not tem_markers and abs(novo_z - z_atual) > 0.001 and layer_started:
                finalizar_camada()
                z_camada = novo_z
            z_atual = novo_z
            z_camada = z_atual
            if not layer_started:
                layer_started = True

        # Atualizar posição
        if 'X' in coords:
            x_atual = coords['X']
        if 'Y' in coords:
            y_atual = coords['Y']

        # Ignorar tipos não desejados (skirt, brim, suporte)
        if tipo_ignorar_ativo:
            continue

        # Determinar se está extrudando
        is_extruding = False
        if 'E' in coords:
            if modo_extrusao == 'relative':
                is_extruding = coords['E'] > 0.0001
            else:
                is_extruding = coords['E'] > e_anterior + 0.0001
                e_anterior = coords['E']

        # --- Processar movimento ---
        if coords['G'] == 0:
            # G0 = travel → finalizar contorno atual e registrar posição
            finalizar_contorno()
            ponto_inicio_contorno = (x_atual, y_atual)

        elif coords['G'] == 1:
            if is_extruding and ('X' in coords or 'Y' in coords):
                # G1 com extrusão → adicionar ao contorno
                if not contorno_atual_pontos and ponto_inicio_contorno is not None:
                    # Início de novo contorno: incluir ponto de origem (do G0)
                    contorno_atual_pontos.append(ponto_inicio_contorno)
                    ponto_inicio_contorno = None
                contorno_atual_pontos.append((x_atual, y_atual))
            elif not is_extruding and ('X' in coords or 'Y' in coords):
                # G1 sem extrusão (travel disfarçado ou wipe) → quebrar contorno
                finalizar_contorno()
                ponto_inicio_contorno = (x_atual, y_atual)

    # Finalizar última camada
    if layer_started:
        finalizar_camada()

    return camadas


# ==============================================================================
# MÓDULO 2: CONVERSÃO PARA GEOMETRIA SHAPELY
# ==============================================================================

def contorno_para_polygon(contorno):
    """Converte um Contorno em um Shapely Polygon.

    Fecha o contorno se necessário e corrige auto-interseções.
    Returns:
        Shapely Polygon ou None se inválido.
    """
    if len(contorno.pontos) < 3:
        return None

    pontos = list(contorno.pontos)

    # Garantir fechamento
    d = math.hypot(pontos[-1][0] - pontos[0][0], pontos[-1][1] - pontos[0][1])
    if d > 0.01:
        pontos.append(pontos[0])

    try:
        poly = Polygon(pontos)
        if not poly.is_valid:
            poly = poly.buffer(0)  # Corrige auto-interseções
        if poly.is_empty:
            return None
        if isinstance(poly, MultiPolygon):
            poly = max(poly.geoms, key=lambda p: p.area)
        return poly
    except Exception:
        return None


def contornos_para_polygons(contornos):
    """Converte todos os contornos de uma camada em Shapely Polygons.

    Filtra artefatos pequenos (area < 1 mm²).
    """
    polygons = []
    for c in contornos:
        poly = contorno_para_polygon(c)
        if poly is not None and poly.area > 1.0:
            polygons.append(poly)
    return polygons


# ==============================================================================
# MÓDULO 3: OTIMIZADOR DE PERCURSO (TSP GREEDY)
# ==============================================================================

def ponto_mais_proximo_idx(coords, px, py):
    """Encontra o índice do ponto mais próximo de (px, py) em coords."""
    if not coords:
        return 0
    dists = [math.hypot(c[0] - px, c[1] - py) for c in coords]
    return dists.index(min(dists))


def rotacionar_coords(coords, idx):
    """Rotaciona uma lista de coordenadas fechada para iniciar no índice idx.

    A lista deve ser fechada (último = primeiro). Retorna lista fechada.
    """
    if len(coords) < 3:
        return coords
    loop = coords[:-1]  # Remover ponto de fechamento
    if idx >= len(loop):
        idx = 0
    rotated = loop[idx:] + loop[:idx]
    rotated.append(rotated[0])  # Re-fechar
    return rotated


def ordenar_contornos_tsp(polygons, start_x, start_y):
    """Ordena polígonos usando TSP nearest-neighbor para minimizar travel.

    Para cada polígono, rotaciona os vértices para que o início seja
    o ponto mais próximo da posição atual do bico.

    Args:
        polygons: Lista de Shapely Polygon
        start_x, start_y: Posição atual do bico

    Returns:
        Lista de listas de coordenadas (uma por polígono, em ordem otimizada)
    """
    if not polygons:
        return []

    remaining = list(range(len(polygons)))
    ordered = []
    cx, cy = start_x, start_y

    while remaining:
        # Encontrar o polígono com o ponto mais próximo da posição atual
        best_remaining_idx = None
        best_dist = float('inf')
        best_vertex_idx = 0

        for i, poly_idx in enumerate(remaining):
            poly = polygons[poly_idx]
            coords = list(poly.exterior.coords)[:-1]
            for j, (px, py) in enumerate(coords):
                d = math.hypot(px - cx, py - cy)
                if d < best_dist:
                    best_dist = d
                    best_remaining_idx = i
                    best_vertex_idx = j

        poly_idx = remaining[best_remaining_idx]
        poly = polygons[poly_idx]
        coords = list(poly.exterior.coords)

        # Rotacionar para iniciar no vértice mais próximo
        rotated = rotacionar_coords(coords, best_vertex_idx)
        ordered.append(rotated)

        # Atualizar posição para o último ponto deste polígono
        cx, cy = rotated[-2]  # -2 porque -1 é o ponto de fechamento duplicado
        remaining.pop(best_remaining_idx)

    return ordered


def otimizar_camada(polygons, start_x, start_y, inverter_direcao=False):
    """Otimiza o percurso de uma camada inteira.

    Args:
        polygons: Lista de Shapely Polygon
        start_x, start_y: Posição atual do bico
        inverter_direcao: Se True, inverte a direção dos contornos (CW↔CCW)

    Returns:
        Lista de listas de coordenadas otimizadas
    """
    if not polygons:
        return []

    ordered = ordenar_contornos_tsp(polygons, start_x, start_y)

    if inverter_direcao:
        result = []
        for coords in ordered:
            start = coords[0]
            # Inverter mas manter o mesmo ponto de início
            reversed_coords = [start] + coords[-2:0:-1] + [start]
            result.append(reversed_coords)
        return result

    return ordered


# ==============================================================================
# MÓDULO 4: GERADOR DE PERÍMETROS E INFILL EXTRAS
# ==============================================================================

def interpolar_pontos(coords, resolucao_mm=1.0):
    """Interpola pontos em uma lista de coordenadas para curvas mais suaves.

    Segmentos maiores que 2× resolução são subdivididos.
    """
    resultado = []
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        dist = math.hypot(x2 - x1, y2 - y1)
        if dist > resolucao_mm * 2:
            n = max(1, int(math.ceil(dist / resolucao_mm)))
            for j in range(n):
                t = j / n
                resultado.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1)))
        else:
            resultado.append((x1, y1))
    resultado.append(coords[-1])
    return resultado


def gerar_perimetros_para_contorno(polygon, num_perimetros, largura_extrusao,
                                    resolucao_mm=1.0):
    """Gera N perímetros concêntricos a partir do contorno extraído.

    O primeiro perímetro segue o contorno original (do slicer).
    Perímetros adicionais são offsets internos.

    Args:
        polygon: Shapely Polygon (contorno original do slicer)
        num_perimetros: Número total de perímetros (>= 1)
        largura_extrusao: Largura do filete (mm)

    Returns:
        Lista de listas de coordenadas [(x,y), ...] — do externo ao interno
    """
    perimetros = []

    # Perímetro 0 = contorno original (já está no polygon)
    coords = list(polygon.exterior.coords)
    if len(coords) >= 3:
        perimetros.append(interpolar_pontos(coords, resolucao_mm))

    # Perímetros extras (offsets internos)
    for p in range(1, num_perimetros):
        offset = p * (largura_extrusao * 0.95)  # Espaçamento entre centros
        poly_offset = polygon.buffer(-offset)

        if poly_offset.is_empty:
            break
        if isinstance(poly_offset, MultiPolygon):
            poly_offset = max(poly_offset.geoms, key=lambda g: g.area)

        coords = list(poly_offset.exterior.coords)
        if len(coords) >= 3:
            perimetros.append(interpolar_pontos(coords, resolucao_mm))

    return perimetros


def calcular_regiao_infill(polygon, num_perimetros, largura_extrusao,
                            sobreposicao=0.5):
    """Calcula o polígono da região de infill (após todos os perímetros).

    Returns:
        Shapely Polygon ou None se não houver espaço para infill.
    """
    if num_perimetros > 0:
        # O infill começa após o perímetro mais interno
        offset = (num_perimetros - 0.5) * largura_extrusao * 0.95 - sobreposicao
    else:
        offset = 0

    if offset > 0:
        region = polygon.buffer(-offset)
    else:
        region = polygon

    if region.is_empty:
        return None
    if isinstance(region, MultiPolygon):
        region = max(region.geoms, key=lambda g: g.area)
    if region.area < 1.0:
        return None
    return region


def gerar_infill_zigzag(poly_infill, largura_extrusao, angulo_graus,
                         infill_percent=100.0):
    """Gera infill zigzag dentro de um polígono usando scanlines rotacionadas.

    Args:
        poly_infill: Shapely Polygon (região de infill)
        largura_extrusao: Largura do filete (mm)
        angulo_graus: Ângulo das linhas de infill
        infill_percent: Densidade do infill (%)

    Returns:
        Lista de (x, y) — caminho zigzag contínuo
    """
    if poly_infill is None or poly_infill.is_empty:
        return []

    # Espaçamento baseado na porcentagem
    espacamento = largura_extrusao * 0.95 * (100.0 / max(1.0, infill_percent))

    minx, miny, maxx, maxy = poly_infill.bounds
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2

    # Rotacionar polígono (scanlines ficam horizontais)
    theta = -angulo_graus
    poly_rotated = affinity.rotate(poly_infill, theta, origin=(cx, cy))
    rminx, rminy, rmaxx, rmaxy = poly_rotated.bounds

    # Gerar scanlines horizontais
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

            # Rotacionar de volta ao sistema original
            angle_rad = math.radians(angulo_graus)
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            for sx, sy in seg_coords:
                dx = sx - cx
                dy = sy - cy
                rx = cx + dx * cos_a - dy * sin_a
                ry = cy + dx * sin_a + dy * cos_a
                pts.append((rx, ry))

        y_current += espacamento
        flip = not flip

    return pts


def gerar_infill_concentrico(poly_infill, largura_extrusao, infill_percent=100.0,
                              resolucao_mm=1.0):
    """Gera anéis concêntricos dentro de um polígono.

    Returns:
        Lista de listas de coordenadas (anéis, do externo ao interno)
    """
    if poly_infill is None or poly_infill.is_empty:
        return []

    espacamento = largura_extrusao * 0.95 * (100.0 / max(1.0, infill_percent))
    aneis = []
    offset = espacamento

    while True:
        poly_ring = poly_infill.buffer(-offset)

        if poly_ring.is_empty:
            break
        if isinstance(poly_ring, MultiPolygon):
            poly_ring = max(poly_ring.geoms, key=lambda g: g.area)
        if poly_ring.area < 1.0:
            break

        coords = list(poly_ring.exterior.coords)
        if len(coords) >= 3:
            aneis.append(interpolar_pontos(coords, resolucao_mm))

        offset += espacamento

    return aneis


def rotacionar_anel_coords(anel, px, py):
    """Rotaciona coordenadas de um anel fechado para iniciar perto de (px, py)."""
    if len(anel) < 3:
        return anel
    loop = anel[:-1]
    dists = [math.hypot(c[0] - px, c[1] - py) for c in loop]
    idx = dists.index(min(dists))
    rotated = loop[idx:] + loop[:idx]
    rotated.append(rotated[0])
    return rotated


def gerar_espiral_concentrica(aneis, start_x, start_y):
    """Conecta anéis concêntricos em uma espiral contínua (Arquimedes poligonal).

    Usa transições suaves por perfil cossenoide (S-curve) entre anéis.

    Returns:
        Lista de (x, y) — percurso contínuo em espiral
    """
    if not aneis:
        return []

    aneis_validos = [a for a in aneis if len(a) >= 3]
    if not aneis_validos:
        return []

    pts_espiral = []
    lx, ly = start_x, start_y

    for i in range(len(aneis_validos)):
        anel_atual = rotacionar_anel_coords(aneis_validos[i], lx, ly)

        if i == 0 or i == len(aneis_validos) - 1:
            # Primeiro e último anel: imprimir completo
            if i > 0 and len(pts_espiral) > 0 and math.hypot(pts_espiral[-1][0] - anel_atual[0][0], pts_espiral[-1][1] - anel_atual[0][1]) < 1e-4:
                pts_espiral.extend(anel_atual[1:])
            else:
                pts_espiral.extend(anel_atual)
            lx, ly = anel_atual[-1]
        else:
            n_atual = len(anel_atual)
            if n_atual < 8:
                if len(pts_espiral) > 0 and math.hypot(pts_espiral[-1][0] - anel_atual[0][0], pts_espiral[-1][1] - anel_atual[0][1]) < 1e-4:
                    pts_espiral.extend(anel_atual[1:])
                else:
                    pts_espiral.extend(anel_atual)
                lx, ly = anel_atual[-1]
                continue

            # Transição suave a 75% do anel
            ponto_corte = int(n_atual * 0.75)
            if len(pts_espiral) > 0 and math.hypot(pts_espiral[-1][0] - anel_atual[0][0], pts_espiral[-1][1] - anel_atual[0][1]) < 1e-4:
                pts_espiral.extend(anel_atual[1:ponto_corte])
            else:
                pts_espiral.extend(anel_atual[:ponto_corte])

            p_rampa = anel_atual[ponto_corte]
            anel_proximo = rotacionar_anel_coords(
                aneis_validos[i + 1], p_rampa[0], p_rampa[1]
            )

            n_rampa = n_atual - ponto_corte
            for j in range(n_rampa):
                t = j / (n_rampa - 1) if n_rampa > 1 else 1.0
                t_suave = (1.0 - math.cos(math.pi * t)) / 2.0
                p_at = anel_atual[ponto_corte + j]
                p_pr = anel_proximo[0]

                rx = (1 - t_suave) * p_at[0] + t_suave * p_pr[0]
                ry = (1 - t_suave) * p_at[1] + t_suave * p_pr[1]
                pts_espiral.append((rx, ry))

            lx, ly = pts_espiral[-1]

    return pts_espiral


# ==============================================================================
# MÓDULO 5: GERADOR DE G-CODE DIRETO
# ==============================================================================

def calcular_e(x1, y1, x2, y2, largura_ext, altura_camada, diametro_fil=1.75):
    """Calcula o valor de extrusão E para um movimento de (x1,y1) a (x2,y2).

    Usa o modelo retangular de seção transversal (width × height).
    E = distância × (largura × altura) / (π × (d_filamento/2)²)
    """
    distancia = math.hypot(x2 - x1, y2 - y1)
    if distancia < 0.001:
        return 0.0
    area_secao = largura_ext * altura_camada
    area_filamento = math.pi * (diametro_fil / 2) ** 2
    return distancia * area_secao / area_filamento


def gerar_gcode_paths(paths, z, args, e_acumulado=0.0):
    """Gera linhas de G-code para uma sequência de paths em uma camada.

    Args:
        paths: Lista de listas de (x, y) — cada sublista é um percurso contíguo
        z: Altura Z da camada
        args: Argumentos CLI (velocidade, largura_extrusao, etc.)
        e_acumulado: Total de E acumulado (para modo absoluto)

    Returns:
        (linhas_gcode, e_acumulado, ultimo_x, ultimo_y)
    """
    lines = []
    relative_e = (args.modo_extrusao == 'relative')
    fluxo_mult = args.fluxo / 100.0

    lx, ly = None, None

    for path in paths:
        if not path or len(path) < 2:
            continue

        # Travel para o início deste path
        if lx is not None:
            dist = math.hypot(path[0][0] - lx, path[0][1] - ly)
            if dist > 0.3:
                lines.append(
                    f"G0 F{args.velocidade_travel:.0f} "
                    f"X{path[0][0]:.3f} Y{path[0][1]:.3f}"
                )
                if args.priming_ativo:
                    if relative_e:
                        lines.append(f"G1 E{args.priming_quantidade:.5f} F{args.priming_velocidade:.0f} ; Priming apos travel")
                    else:
                        e_acumulado += args.priming_quantidade
                        lines.append(f"G1 E{e_acumulado:.5f} F{args.priming_velocidade:.0f} ; Priming apos travel")
        else:
            # Primeiro path da camada: travel com Z
            lines.append(
                f"G0 F{args.velocidade_travel:.0f} "
                f"X{path[0][0]:.3f} Y{path[0][1]:.3f} Z{z:.4f}"
            )
            if args.priming_ativo:
                if relative_e:
                    lines.append(f"G1 E{args.priming_quantidade:.5f} F{args.priming_velocidade:.0f} ; Priming inicial de camada")
                else:
                    e_acumulado += args.priming_quantidade
                    lines.append(f"G1 E{e_acumulado:.5f} F{args.priming_velocidade:.0f} ; Priming inicial de camada")

        lx, ly = path[0]

        # Movimentos de extrusão
        f_set = False
        for i in range(1, len(path)):
            x, y = path[i]
            e = calcular_e(lx, ly, x, y, args.largura_extrusao,
                           args.altura_camada_atual, args.diametro_filamento) * fluxo_mult

            if e < 0.00001:
                continue

            if relative_e:
                if not f_set:
                    lines.append(
                        f"G1 F{args.velocidade:.0f} "
                        f"X{x:.3f} Y{y:.3f} E{e:.5f}"
                    )
                    f_set = True
                else:
                    lines.append(f"G1 X{x:.3f} Y{y:.3f} E{e:.5f}")
            else:
                e_acumulado += e
                if not f_set:
                    lines.append(
                        f"G1 F{args.velocidade:.0f} "
                        f"X{x:.3f} Y{y:.3f} E{e_acumulado:.5f}"
                    )
                    f_set = True
                else:
                    lines.append(f"G1 X{x:.3f} Y{y:.3f} E{e_acumulado:.5f}")

            lx, ly = x, y

    return lines, e_acumulado, lx, ly


def orientar_path(path, lx, ly):
    """Orienta o path para começar mais perto de (lx, ly) — inverte se necessário."""
    if not path or len(path) < 2:
        return path
    d_start = math.hypot(path[0][0] - lx, path[0][1] - ly)
    d_end = math.hypot(path[-1][0] - lx, path[-1][1] - ly)
    if d_end < d_start:
        return list(reversed(path))
    return path


def gerar_gcode_completo(camadas, header_lines, footer_lines, args):
    """Gera o G-code completo otimizado.

    Estrutura: header original + body otimizado + footer original

    Args:
        camadas: Lista de Camada com geometria extraída
        header_lines: Header original do PrusaSlicer
        footer_lines: Footer original do PrusaSlicer
        args: Argumentos CLI

    Returns:
        str: G-code completo
    """
    output_lines = []

    # --- Header original ---
    for line in header_lines:
        output_lines.append(line.rstrip('\r\n'))

    # --- Cabeçalho do otimizador ---
    output_lines.append('')
    output_lines.append('; ============================================')
    output_lines.append('; G-code otimizado por gcode_optimizer.py')
    output_lines.append(f'; Camadas processadas: {len(camadas)}')
    output_lines.append(f'; Perimetros: {args.num_perimetros}')
    output_lines.append(f'; Infill: {args.infill_pattern} ({args.infill_percent}%)')
    output_lines.append(f'; Largura extrusao: {args.largura_extrusao} mm')
    output_lines.append(f'; Velocidade: {args.velocidade} mm/min')
    output_lines.append(f'; Fluxo: {args.fluxo}%')
    output_lines.append('; ============================================')
    output_lines.append('')

    # Garantir modo de extrusão correto e resetar E
    if args.modo_extrusao == 'relative':
        output_lines.append('M83')
    else:
        output_lines.append('M82')
    output_lines.append('G92 E0.0')
    output_lines.append(f'M221 S{args.fluxo}')
    output_lines.append('')

    e_acumulado = 0.0
    lx, ly = 0.0, 0.0

    total_travels = 0
    total_extrusions = 0

    for idx_camada, camada in enumerate(camadas):
        direcao_inversa = (idx_camada % 2 == 1)
        args.altura_camada_atual = camada.altura if camada.altura > 0 else args.altura_camada

        output_lines.append(
            f'; --- CAMADA {idx_camada} | Z={camada.z:.3f} | '
            f'H={args.altura_camada_atual:.2f} | '
            f'contornos={len(camada.contornos)} ---'
        )

        # Converter contornos extraídos em polígonos Shapely
        polygons = contornos_para_polygons(camada.contornos)

        if not polygons:
            output_lines.append('; (camada vazia)')
            continue

        # Otimizar ordem dos contornos (TSP greedy)
        contornos_otimizados = otimizar_camada(
            polygons, lx, ly, direcao_inversa
        )

        # Para cada contorno otimizado: gerar perímetros + infill
        todas_paths = []

        for coords_contorno in contornos_otimizados:
            poly = Polygon(coords_contorno)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                continue
            if isinstance(poly, MultiPolygon):
                poly = max(poly.geoms, key=lambda g: g.area)

            # --- INFILL (impresso primeiro para melhor qualidade de superfície) ---
            if args.infill_pattern != 'none' and args.infill_percent > 0:
                poly_infill = calcular_regiao_infill(
                    poly, args.num_perimetros, args.largura_extrusao,
                    args.sobreposicao_infill
                )

                if poly_infill is not None:
                    angulo = (args.angulo_infill if not direcao_inversa
                              else args.angulo_infill + 90)

                    if args.infill_pattern == 'zigzag':
                        pts_infill = gerar_infill_zigzag(
                            poly_infill, args.largura_extrusao,
                            angulo, args.infill_percent
                        )
                        if pts_infill:
                            pts_infill = orientar_path(pts_infill, lx, ly)
                            todas_paths.append(pts_infill)
                            lx, ly = pts_infill[-1]

                    elif args.infill_pattern == 'concentric':
                        aneis = gerar_infill_concentrico(
                            poly_infill, args.largura_extrusao,
                            args.infill_percent
                        )
                        if aneis:
                            pts_espiral = gerar_espiral_concentrica(aneis, lx, ly)
                            if pts_espiral:
                                todas_paths.append(pts_espiral)
                                lx, ly = pts_espiral[-1]

            # --- PERÍMETROS (interno → externo para melhor superfície) ---
            if args.num_perimetros > 0:
                perimetros = gerar_perimetros_para_contorno(
                    poly, args.num_perimetros, args.largura_extrusao
                )
                # Imprimir de dentro para fora (inverter ordem)
                for p_coords in reversed(perimetros):
                    p_rotated = rotacionar_anel_coords(p_coords, lx, ly)
                    todas_paths.append(p_rotated)
                    if p_rotated:
                        lx, ly = p_rotated[-1]
            else:
                # Sem perímetros extras: usar contorno original
                c_rotated = rotacionar_anel_coords(list(coords_contorno), lx, ly)
                todas_paths.append(c_rotated)
                if c_rotated:
                    lx, ly = c_rotated[-1]

        # Gerar G-code para esta camada
        gcode_lines, e_acumulado, lx_new, ly_new = gerar_gcode_paths(
            todas_paths, camada.z, args, e_acumulado
        )
        if lx_new is not None:
            lx, ly = lx_new, ly_new

        # Estatísticas
        for gl in gcode_lines:
            if gl.startswith('G0'):
                total_travels += 1
            elif gl.startswith('G1'):
                total_extrusions += 1

        output_lines.extend(gcode_lines)
        output_lines.append('')

    # --- Estatísticas finais ---
    output_lines.append('; ============================================')
    output_lines.append(
        f'; Estatisticas: {total_extrusions} extrusoes, {total_travels} travels'
    )
    output_lines.append('; ============================================')
    output_lines.append('')

    # --- Footer original ---
    for line in footer_lines:
        output_lines.append(line.rstrip('\r\n'))

    return '\n'.join(output_lines) + '\n'


# ==============================================================================
# MÓDULO 6: LIMPEZA DE G-CODE
# ==============================================================================

def limpar_gcode(gcode_text):
    """Remove comentários desnecessários para compatibilidade com firmware.

    Preserva marcadores de seção e informações do otimizador.
    """
    linhas = gcode_text.split('\n')
    linhas_limpas = []

    # Prefixos de comentários a preservar
    prefixos_manter = (
        ';STARTGCODE', ';ENDGCODE',
        '; ===', '; ---',
        '; G-code otimizado', '; Camadas', '; Perimetros',
        '; Infill', '; Largura', '; Velocidade', '; Fluxo',
        '; Estatisticas', '; (camada',
    )

    for linha in linhas:
        linha = linha.rstrip('\r\n')

        if ';' in linha and not linha.lstrip().startswith(';'):
            # Remover comentários inline
            linha = linha[:linha.index(';')].rstrip()
        elif linha.lstrip().startswith(';'):
            stripped = linha.strip()
            if any(stripped.startswith(p) for p in prefixos_manter):
                pass  # Manter
            else:
                continue  # Remover

        if linha:
            linhas_limpas.append(linha)

    return '\n'.join(linhas_limpas) + '\n'


# ==============================================================================
# MÓDULO 7: CLI (INTERFACE DE LINHA DE COMANDO)
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            'Otimizador de G-code: PrusaSlicer → '
            'Percurso Otimizado (FullControl Principles)'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python gcode_optimizer.py modelo.gcode
  python gcode_optimizer.py modelo.gcode --num-perimetros 2 --infill-pattern concentric
  python gcode_optimizer.py modelo.gcode --infill-pattern zigzag --angulo-infill 45
  python gcode_optimizer.py modelo.gcode --velocidade 1200 --fluxo 95 --verbose

Requisitos do G-code de entrada (PrusaSlicer):
  - "Verbose G-code" habilitado (Print Settings > Output options)
  - Arc fitting desabilitado
  - Recomendado: 1 perímetro, 0 infill
        """
    )

    parser.add_argument(
        'input', type=str, nargs='?', default=INPUT_GCODE,
        help='G-code de entrada do PrusaSlicer'
    )
    parser.add_argument(
        '--output', type=str,
        default=None if not OUTPUT_GCODE else OUTPUT_GCODE,
        help='Arquivo de saída (default: {input}_otimizado.gcode)'
    )
    parser.add_argument(
        '--num-perimetros', type=int, default=NUM_PERIMETROS,
        help=f'Número total de perímetros (default: {NUM_PERIMETROS})'
    )
    parser.add_argument(
        '--infill-pattern', type=str, default=INFILL_PATTERN,
        choices=['none', 'concentric', 'zigzag'],
        help=f'Padrão de infill (default: {INFILL_PATTERN})'
    )
    parser.add_argument(
        '--infill-percent', type=float, default=INFILL_PERCENT,
        help=f'Densidade do infill em %% (default: {INFILL_PERCENT})'
    )
    parser.add_argument(
        '--angulo-infill', type=float, default=ANGULO_INFILL,
        help=f'Ângulo base do infill zigzag em graus (default: {ANGULO_INFILL})'
    )
    parser.add_argument(
        '--largura-extrusao', type=float, default=LARGURA_EXTRUSAO,
        help=f'Largura do filete de extrusão em mm (default: {LARGURA_EXTRUSAO})'
    )
    parser.add_argument(
        '--altura-camada', type=float, default=ALTURA_CAMADA,
        help=f'Altura de camada em mm; 0 = auto-detect (default: {ALTURA_CAMADA})'
    )
    parser.add_argument(
        '--diametro-filamento', type=float, default=DIAMETRO_FILAMENTO,
        help=f'Diâmetro do filamento/pistão em mm (default: {DIAMETRO_FILAMENTO})'
    )
    parser.add_argument(
        '--velocidade', type=float, default=VELOCIDADE,
        help=f'Velocidade de impressão em mm/min (default: {VELOCIDADE})'
    )
    parser.add_argument(
        '--velocidade-travel', type=float, default=VELOCIDADE_TRAVEL,
        help=f'Velocidade de travel em mm/min (default: {VELOCIDADE_TRAVEL})'
    )
    parser.add_argument(
        '--fluxo', type=int, default=FLUXO,
        help=f'Fluxo de extrusão em %% (default: {FLUXO})'
    )
    parser.add_argument(
        '--sobreposicao-infill', type=float, default=SOBREPOSICAO_INFILL,
        help=f'Sobreposição infill↔perímetro em mm (default: {SOBREPOSICAO_INFILL})'
    )
    parser.add_argument(
        '--no-clean', action='store_true', default=False,
        help='Não limpar comentários do G-code (útil para debug)'
    )
    parser.add_argument(
        '--no-priming', action='store_true', default=False,
        help='Desabilita o priming automático após travels'
    )
    parser.add_argument(
        '--priming-quantidade', type=float, default=PRIMING_QUANTIDADE,
        help=f'Quantidade extra de extrusão para priming em mm (default: {PRIMING_QUANTIDADE})'
    )
    parser.add_argument(
        '--priming-velocidade', type=float, default=PRIMING_VELOCIDADE,
        help=f'Velocidade de extrusão do priming em mm/min (default: {PRIMING_VELOCIDADE})'
    )
    parser.add_argument(
        '--verbose', action='store_true', default=False,
        help='Logging detalhado'
    )

    args = parser.parse_args()

    # --- Validação ---
    if not args.input:
        print("\n" + "=" * 60)
        print("  ERRO: Nenhum arquivo G-code de entrada foi fornecido!")
        print("=" * 60)
        print("Você pode fornecer o arquivo de duas formas:")
        print("  1. Configurando a variável 'INPUT_GCODE' no topo deste script.")
        print("  2. Passando o caminho por linha de comando:")
        print("     python gcode_optimizer.py seu_arquivo.gcode")
        print("\nPara ver todas as opções:")
        print("     python gcode_optimizer.py --help")
        print("=" * 60)
        sys.exit(1)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERRO: Arquivo não encontrado: {args.input}")
        sys.exit(1)

    if args.output is None:
        args.output = str(input_path.with_suffix('')) + '_otimizado.gcode'

    # --- Leitura ---
    with open(args.input, 'r', encoding='utf-8', errors='replace') as f:
        all_lines = f.readlines()

    # --- Detecção automática ---
    args.modo_extrusao = detectar_modo_extrusao(all_lines)
    params_slicer = detectar_parametros_slicer(all_lines)

    # Auto-detect altura de camada
    if args.altura_camada == 0:
        if 'altura_camada' in params_slicer:
            args.altura_camada = params_slicer['altura_camada']
        else:
            args.altura_camada = 2.0  # Fallback (padrão CL2Pro)

    # Auto-detect diâmetro do filamento
    if 'diametro_filamento' in params_slicer:
        args.diametro_filamento = params_slicer['diametro_filamento']

    # Altura de camada atual (será atualizada por camada)
    args.altura_camada_atual = args.altura_camada
    args.priming_ativo = not args.no_priming

    # --- Banner ---
    print("=" * 60)
    print("  Otimizador G-code: PrusaSlicer -> FullControl Principles")
    print("=" * 60)
    print(f"\n  Arquivo de entrada:    {args.input}")
    print(f"  Modo de extrusao:      {args.modo_extrusao.upper()}")
    print(f"  Perimetros:            {args.num_perimetros}")
    print(f"  Infill:                {args.infill_pattern} ({args.infill_percent}%)")
    print(f"  Largura extrusao:      {args.largura_extrusao} mm")
    print(f"  Altura camada:         {args.altura_camada} mm")
    print(f"  Diametro filamento:    {args.diametro_filamento} mm")
    print(f"  Velocidade:            {args.velocidade} mm/min")
    print(f"  Velocidade travel:     {args.velocidade_travel} mm/min")
    print(f"  Fluxo:                 {args.fluxo}%")
    print(f"  Priming ativo:         {args.priming_ativo} (Qtd: {args.priming_quantidade}mm | Vel: {args.priming_velocidade}mm/min)")
    if params_slicer:
        print(f"  Parametros do slicer:  {params_slicer}")
    print()

    # --- Etapa 1: Extrair header/body/footer ---
    print("[1/5] Extraindo header/body/footer...")
    header, body, footer = extrair_header_body_footer(all_lines)
    print(f"  Header: {len(header)} linhas")
    print(f"  Body:   {len(body)} linhas")
    print(f"  Footer: {len(footer)} linhas")

    # --- Etapa 2: Extrair camadas ---
    print(f"\n[2/5] Extraindo camadas e contornos...")
    camadas = extrair_camadas(body, args.modo_extrusao)
    print(f"  Camadas encontradas: {len(camadas)}")

    total_contornos = sum(len(c.contornos) for c in camadas)
    total_pontos = sum(
        sum(len(ct.pontos) for ct in c.contornos) for c in camadas
    )
    print(f"  Total de contornos:  {total_contornos}")
    print(f"  Total de pontos:     {total_pontos}")

    if args.verbose:
        for i, cam in enumerate(camadas):
            n_pts = sum(len(c.pontos) for c in cam.contornos)
            tipos = set(c.tipo for c in cam.contornos)
            print(
                f"    Camada {i:>3d}: Z={cam.z:>8.3f} H={cam.altura:.3f} "
                f"contornos={len(cam.contornos):>2d} pontos={n_pts:>5d} "
                f"tipos={tipos}"
            )

    if not camadas:
        print("\nERRO: Nenhuma camada encontrada no G-code.")
        print("Verifique se o G-code foi gerado com 'Verbose G-code' habilitado")
        print("no PrusaSlicer (Print Settings > Output options).")
        sys.exit(1)

    # --- Etapa 3: Gerar G-code otimizado ---
    print(f"\n[3/5] Gerando G-code otimizado ({len(camadas)} camadas)...")
    gcode_final = gerar_gcode_completo(camadas, header, footer, args)

    # --- Etapa 4: Limpeza ---
    if not args.no_clean:
        print(f"\n[4/5] Limpando G-code...")
        gcode_final = limpar_gcode(gcode_final)
    else:
        print(f"\n[4/5] Limpeza desabilitada (--no-clean)")

    # --- Etapa 5: Salvar ---
    print(f"\n[5/5] Salvando...")
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(gcode_final)

    num_linhas = gcode_final.count('\n')

    # Contar estatísticas do otimizado
    n_g0 = sum(1 for l in gcode_final.split('\n') if l.strip().startswith('G0'))
    n_g1 = sum(1 for l in gcode_final.split('\n') if l.strip().startswith('G1'))

    # Contar estatísticas do original
    n_g0_orig = sum(1 for l in body if l.strip().startswith('G0'))
    n_g1_orig = sum(1 for l in body if l.strip().startswith('G1'))

    print(f"\n  [OK] G-code salvo: {args.output}")
    print(f"  [OK] Total de linhas: {num_linhas}")
    print(f"  [OK] Camadas: {len(camadas)}")

    print(f"\n  Comparacao (body):")
    print(f"    Original  -> G0 (travel): {n_g0_orig:>6} | "
          f"G1 (extrusao): {n_g1_orig:>6}")
    print(f"    Otimizado -> G0 (travel): {n_g0:>6} | "
          f"G1 (extrusao): {n_g1:>6}")

    if n_g0_orig > 0:
        reducao = ((n_g0_orig - n_g0) / n_g0_orig) * 100
        print(f"    Reducao de travels: {reducao:.1f}%")

    print("\n" + "=" * 60)
    print("  Concluido com sucesso!")
    print("=" * 60)


if __name__ == '__main__':
    main()

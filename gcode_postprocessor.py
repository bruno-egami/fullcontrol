#!/usr/bin/env python3
"""
Pós-Processador: PrusaSlicer G-code → FullControl Base Sólida

Lê um G-code de vase mode (PrusaSlicer), extrai o contorno da primeira camada,
gera uma base sólida via FullControl com infill + perímetros configuráveis,
e mescla os dois G-codes com ajuste de Z.

Uso:
    python gcode_postprocessor.py input.gcode --z-ref 1.5 --camadas-base 3

Dependências:
    pip install shapely
"""

import argparse
import math
import re
import sys
from pathlib import Path

import fullcontrol as fc
from shapely.geometry import Polygon, LineString, MultiLineString, MultiPolygon
from shapely.ops import unary_union
from shapely import affinity

# ==============================================================================
# CONFIGURAÇÃO PADRÃO
# ==============================================================================
# Ajuste as variáveis abaixo para configurar o comportamento padrão do script.
# Se você executar 'python gcode_postprocessor.py' sem nenhum argumento,
# o script usará estes valores padrão. Você também pode sobrescrever qualquer
# um desses valores passando argumentos pela linha de comando.
# Exemplo: python gcode_postprocessor.py --z-ref 1.5

# --- Arquivo de Entrada ---
INPUT_GCODE = "Copo-Hexagono-torcido.gcode"  # Caminho do G-code de entrada do PrusaSlicer (vase mode)
OUTPUT_GCODE = ""                            # Caminho do arquivo de saída (deixe vazio para gerar {input}_com_base.gcode)

# --- Parâmetros Geométricos da Base ---
Z_REF = 2.0                                  # Altura Z máxima para extrair o contorno da base (mm)
CAMADAS_BASE = 2                             # Número de camadas sólidas da base
ALTURA_CAMADA = 2.0                          # Altura (espessura) de cada camada da base (mm)
LARGURA_EXTRUSAO = 3.0                       # Largura do filete de extrusão (mm)
NUM_PERIMETROS = 0                           # Número de perímetros na base (0 = apenas preenchimento)

# --- Preenchimento (Infill) ---
INFILL_PATTERN = "concentric"                    # Padrão de infill: 'zigzag' ou 'concentric'
ANGULO_INFILL = 45.0                         # Ângulo base do infill em graus

# --- Parâmetros de Impressão ---
VELOCIDADE = 600.0                           # Velocidade de impressão da base (mm/min)
FLUXO = 100                                  # Fluxo de extrusão da base (%)
PRINTER_PROFILE = "Community/Cliever CL2Pro" # Perfil da impressora no FullControl


# ==============================================================================
# MÓDULO 1: PARSER DE G-CODE (PrusaSlicer)
# ==============================================================================

def detectar_modo_extrusao(filepath):
    """Detecta se o arquivo G-code usa extrusão absoluta (M82) ou relativa (M83).
    
    A busca é feita nas primeiras linhas do arquivo, ignorando comentários.
    Retorna:
        str: 'absolute' ou 'relative'
    """
    modo = 'absolute'  # padrão para a maioria dos slicers
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            # Lê apenas as primeiras 300 linhas (onde a inicialização costuma estar)
            for _ in range(300):
                line = f.readline()
                if not line:
                    break
                
                stripped = line.strip()
                # Ignorar comentários puros
                if not stripped or stripped.startswith(';'):
                    continue
                
                # Remover comentários inline
                if ';' in stripped:
                    stripped = stripped[:stripped.index(';')].strip()
                
                # Procurar por M82 ou M83 isolados como comandos
                tokens = stripped.split()
                if 'M82' in tokens:
                    modo = 'absolute'
                elif 'M83' in tokens:
                    modo = 'relative'
    except Exception as e:
        print(f"Aviso ao detectar modo de extrusao: {e}. Usando 'absolute' por padrao.")
        
    return modo


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


def parse_gcode_file(filepath):
    """Parseia um arquivo G-code do PrusaSlicer.
    
    Returns:
        tuple: (header_lines, body_lines, footer_lines, primeiro_ponto_extrusion)
        - header_lines: linhas até ;STARTGCODE (inclusive) + inicialização
        - body_lines: linhas do corpo (movimentos de impressão)
        - footer_lines: linhas a partir de ;ENDGCODE
        - primeiro_ponto_extrusion: (x, y, z) do primeiro movimento com extrusão
    """
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        all_lines = f.readlines()
    
    # Encontrar marcadores do PrusaSlicer
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
        # Sem marcador explicito - trata tudo como corpo
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
    
    # Separar comandos de inicializacao do corpo real de impressao.
    # Tudo antes do primeiro movimento de impressao (G0/G1 com E) e parte do header.
    # Isso evita duplicar G28, M106, etc. na mesclagem.
    idx_first_print = None
    for i, line in enumerate(body_lines):
        coords = parse_gcode_line(line)
        if coords and 'E' in coords and coords['E'] > 0:
            idx_first_print = i
            break
    
    if idx_first_print is not None and idx_first_print > 0:
        # Move init commands from body to header
        header_lines = header_lines + body_lines[:idx_first_print]
        body_lines = body_lines[idx_first_print:]
    
    # Encontrar o primeiro ponto de extrusao no corpo
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
    """Extrai os pontos do contorno (perímetro) até z_referencia.
    
    Filtra movimentos de extrusão (E > 0) com Z <= z_referencia
    e retorna os pontos (X, Y) como um polígono Shapely.
    
    Args:
        body_lines: linhas do corpo do G-code
        z_referencia: altura Z máxima para extrair o contorno
        
    Returns:
        tuple: (shapely.Polygon, list de (x,y) dos pontos originais)
    """
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
            # Se subiu acima da referência, para de coletar
            if z_atual > z_referencia + 0.01:
                break
        
        if 'X' in coords:
            x_atual = coords['X']
        if 'Y' in coords:
            y_atual = coords['Y']
        
        # Coleta pontos com extrusão dentro da faixa Z
        if (z_atual <= z_referencia + 0.01 and 
            'E' in coords and coords['E'] > 0 and
            x_atual is not None and y_atual is not None):
            pontos.append((x_atual, y_atual))
    
    if len(pontos) < 3:
        print(f"ERRO: Apenas {len(pontos)} pontos encontrados abaixo de Z={z_referencia}mm.")
        print("Verifique o valor de --z-ref e o G-code de entrada.")
        sys.exit(1)
    
    # Remover pontos duplicados consecutivos
    pontos_limpos = [pontos[0]]
    for p in pontos[1:]:
        if math.hypot(p[0] - pontos_limpos[-1][0], p[1] - pontos_limpos[-1][1]) > 0.01:
            pontos_limpos.append(p)
    
    # Garantir que o polígono é fechado
    if math.hypot(pontos_limpos[0][0] - pontos_limpos[-1][0], 
                  pontos_limpos[0][1] - pontos_limpos[-1][1]) > 0.1:
        pontos_limpos.append(pontos_limpos[0])
    
    try:
        poligono = Polygon(pontos_limpos)
        if not poligono.is_valid:
            poligono = poligono.buffer(0)  # Corrige auto-interseções menores
        if poligono.is_empty:
            print("ERRO: O polígono extraído é vazio após correção.")
            sys.exit(1)
        # Se buffer(0) retornou MultiPolygon, pegar o maior
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
    
    Args:
        pontos_perimetro: lista de fc.Point (loop fechado, último = primeiro)
        ponto_inicio_slicer: (x, y) do primeiro ponto de extrusão do slicer
    """
    if len(pontos_perimetro) < 3:
        return pontos_perimetro
    
    sx, sy = ponto_inicio_slicer
    
    # Ignorar o último ponto (que fecha o loop = igual ao primeiro)
    loop = pontos_perimetro[:-1]
    
    # Encontrar o ponto mais próximo do início do slicer
    dists = [math.hypot(p.x - sx, p.y - sy) for p in loop]
    idx_mais_proximo = dists.index(min(dists))
    
    # Rotacionar: o ponto mais próximo vira o ÚLTIMO
    # Então o início é o ponto seguinte
    idx_inicio = (idx_mais_proximo + 1) % len(loop)
    rotacionado = loop[idx_inicio:] + loop[:idx_inicio]
    
    # Fechar o loop
    rotacionado.append(fc.Point(x=rotacionado[0].x, y=rotacionado[0].y, z=rotacionado[0].z))
    
    return rotacionado


def polygon_to_points(polygon, z, resolucao_mm=1.0):
    """Converte um polígono Shapely em lista de fc.Point.
    
    Se o polígono tiver poucos pontos, interpola para a resolução desejada.
    """
    coords = list(polygon.exterior.coords)
    pts = []
    
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        dist = math.hypot(x2 - x1, y2 - y1)
        
        if dist > resolucao_mm * 2:
            # Interpolar pontos intermediários
            num_seg = max(1, int(math.ceil(dist / resolucao_mm)))
            for j in range(num_seg):
                t = j / num_seg
                px = x1 + t * (x2 - x1)
                py = y1 + t * (y2 - y1)
                pts.append(fc.Point(x=px, y=py, z=z))
        else:
            pts.append(fc.Point(x=x1, y=y1, z=z))
    
    # Fechar o loop
    pts.append(fc.Point(x=pts[0].x, y=pts[0].y, z=z))
    return pts


def gerar_perimetros(poligono, z, num_perimetros, largura_extrusao, resolucao_mm=1.0):
    """Gera perímetros concêntricos usando Shapely buffer negativo.
    
    Returns:
        list de listas de fc.Point (uma lista por perímetro, do externo ao interno)
    """
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
    """Gera infill zigzag dentro do polígono usando scanlines + Shapely intersection.
    
    Args:
        poligono: Shapely Polygon (contorno original)
        z: altura Z da camada
        num_perimetros: número de perímetros (para calcular offset do infill)
        largura_extrusao: largura do filete
        angulo_graus: ângulo das linhas de infill
        sobreposicao: sobreposição com a parede interna
        
    Returns:
        list de fc.Point (caminho zigzag contínuo)
    """
    # Calcular o polígono interno (após os perímetros)
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
    
    # Bounding box do polígono
    minx, miny, maxx, maxy = poly_infill.bounds
    
    # Centro do polígono para rotação
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2
    
    # Rotacionar o polígono para que as scanlines sejam horizontais
    # (mais simples computacionalmente)
    theta = -angulo_graus  # Rotaciona o polígono no sentido contrário
    poly_rotated = affinity.rotate(poly_infill, theta, origin=(cx, cy))
    
    rminx, rminy, rmaxx, rmaxy = poly_rotated.bounds
    
    # Gerar scanlines horizontais
    pts = []
    y_current = math.ceil(rminy / espacamento) * espacamento
    flip = False
    
    while y_current <= rmaxy + 1e-5:
        # Linha horizontal que cruza o polígono
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
            for sx, sy in seg_coords:
                # Rotação inversa
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
    """Gera infill concêntrico usando Shapely buffer iterativo.
    
    Returns:
        list de listas de fc.Point (uma lista por anel)
    """
    # Offset inicial (após os perímetros)
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
        
        if poly_ring.area < 1.0:  # Muito pequeno
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


def gerar_espiral_concentrica_poligonal(aneis, start_x, start_y):
    """Conecta múltiplos anéis concêntricos em uma única espiral contínua de fora para dentro."""
    if not aneis:
        return []
    
    aneis_validos = [a for a in aneis if len(a) >= 3]
    if not aneis_validos:
        return []
        
    pts_espiral = []
    lx, ly = start_x, start_y
    
    for i in range(len(aneis_validos)):
        anel_atual = rotacionar_anel(aneis_validos[i], lx, ly)
        
        if i == 0:
            # O primeiro anel (mais externo) é impresso 100% completo
            # para garantir perfeita vedação geométrica com os perímetros e zero gaps.
            pts_espiral.extend(anel_atual)
            lx, ly = anel_atual[-1].x, anel_atual[-1].y
        elif i == len(aneis_validos) - 1:
            # Último anel concêntrico: impresso por completo para fechar a base
            pts_espiral.extend(anel_atual)
            lx, ly = anel_atual[-1].x, anel_atual[-1].y
        else:
            n_atual = len(anel_atual)
            if n_atual < 8:
                # Muito pequeno para fazer rampa de transição suave
                pts_espiral.extend(anel_atual)
                lx, ly = anel_atual[-1].x, anel_atual[-1].y
                continue
                
            # Rampa suave a partir de 75% dos pontos
            ponto_corte = int(n_atual * 0.75)
            pts_espiral.extend(anel_atual[:ponto_corte])
            
            p_rampa_inicio = anel_atual[ponto_corte]
            
            # Rotaciona o próximo anel para iniciar o mais perto possível do ponto de início da rampa
            anel_proximo_orientado = rotacionar_anel(aneis_validos[i+1], p_rampa_inicio.x, p_rampa_inicio.y)
            
            n_rampa = n_atual - ponto_corte
            for j in range(n_rampa):
                t = j / (n_rampa - 1) if n_rampa > 1 else 1.0
                # Suavização por perfil cossenoide (S-curve) para eliminar quinas e evitar gaps de transição
                t_suave = (1.0 - math.cos(math.pi * t)) / 2.0
                p_at = anel_atual[ponto_corte + j]
                p_pr = anel_proximo_orientado[0] # Conduz suavemente até o início do próximo anel
                
                rx = (1 - t_suave) * p_at.x + t_suave * p_pr.x
                ry = (1 - t_suave) * p_at.y + t_suave * p_pr.y
                pts_espiral.append(fc.Point(x=rx, y=ry, z=p_at.z))
                
            lx, ly = pts_espiral[-1].x, pts_espiral[-1].y
            
    return pts_espiral


def gerar_base_solida(poligono, args, primeiro_ponto_slicer):
    """Gera a base sólida completa via FullControl.
    
    Args:
        poligono: Shapely Polygon do contorno
        args: argumentos CLI
        primeiro_ponto_slicer: (x, y, z) do primeiro ponto de extrusão do slicer
        
    Returns:
        list: steps do FullControl
    """
    steps = []
    
    # Inicialização
    steps.append(fc.Printer(print_speed=args.velocidade, travel_speed=3000))
    steps.append(fc.ManualGcode(text="M204 P500 T500"))
    steps.append(fc.ExtrusionGeometry(
        area_model='rectangle', 
        width=args.largura_extrusao, 
        height=args.altura_camada
    ))
    
    # Purga (mesmo padrão do usuário)
    steps.append(fc.ManualGcode(text="; --- PURGA PERSONALIZADA ---"))
    steps.append(fc.ManualGcode(text="G1 E25 F100 ; Purga"))
    steps.append(fc.ManualGcode(text="G92 E0.0"))
    
    # Fluxo
    steps.append(fc.ManualGcode(text=f"M221 S{args.fluxo}"))
    
    # Primeiro ponto: centro do bounding box do polígono, na primeira camada
    centroid = poligono.centroid
    
    # Travel para o início do primeiro perímetro
    primeiro_perim = gerar_perimetros(poligono, args.altura_camada, 
                                       min(1, args.num_perimetros), 
                                       args.largura_extrusao)
    if primeiro_perim and primeiro_perim[0]:
        start_pt = primeiro_perim[0][0]
        steps.append(fc.Extruder(on=False))
        steps.append(fc.Point(x=start_pt.x, y=start_pt.y, z=args.altura_camada))
        steps.append(fc.Extruder(on=True))
    
    # Gerar cada camada da base
    for camada in range(args.camadas_base):
        z_atual = args.altura_camada + (camada * args.altura_camada)
        eh_par = (camada % 2 == 0)
        eh_ultima_camada = (camada == args.camadas_base - 1)
        
        # Subir Z se não for a primeira camada
        if camada > 0:
            lx, ly = get_last_point(steps)
            steps.append(fc.Extruder(on=False))
            steps.append(fc.Point(x=lx, y=ly, z=z_atual))
            steps.append(fc.Extruder(on=True))
        
        # --- PERÍMETROS ---
        if args.num_perimetros > 0:
            perimetros = gerar_perimetros(poligono, z_atual, args.num_perimetros, 
                                          args.largura_extrusao)
            
            for i, pts_perim in enumerate(perimetros):
                eh_perim_externo_ultima = (eh_ultima_camada and i == 0)
                
                if eh_perim_externo_ultima and primeiro_ponto_slicer:
                    # Alinhar o último ponto do perímetro externo com o início do slicer
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
                poligono, z_atual, args.num_perimetros, args.largura_extrusao,
                angulo_atual, sobreposicao=0.5
            )
            lx, ly = get_last_point(steps)
            pts_infill = orientar_caminho(pts_infill, lx, ly)
            adicionar_caminho_seguro(steps, pts_infill)
            
        elif args.infill_pattern == 'concentric':
            aneis = gerar_infill_concentrico(
                poligono, z_atual, args.num_perimetros, args.largura_extrusao,
                sobreposicao=0.5
            )
            lx, ly = get_last_point(steps)
            pts_infill = gerar_espiral_concentrica_poligonal(aneis, lx, ly)
            if pts_infill:
                adicionar_caminho_seguro(steps, pts_infill)
    
    steps.append(fc.Extruder(on=False))
    
    return steps


# ==============================================================================
# MÓDULO 4: MESCLADOR DE G-CODES
# ==============================================================================

def ajustar_z_gcode(body_lines, z_offset):
    """Adiciona z_offset a todas as coordenadas Z nas linhas do corpo do G-code.
    
    Returns:
        list de strings (linhas ajustadas)
    """
    resultado = []
    
    for line in body_lines:
        stripped = line.strip()
        
        # Ignorar linhas vazias e comentários puros
        if not stripped or stripped.startswith(';'):
            resultado.append(line)
            continue
        
        # Só ajustar linhas G0/G1
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
    """Gera o G-code final mesclado.
    
    1. Gera G-code da base via FullControl alinhado com o modo de extrusão do slicer.
    2. Ajusta Z do G-code do slicer.
    3. Concatena base + slicer (sem duplicar header/footer).
    
    Returns:
        str: G-code final completo
    """
    # Define se usa extrusão relativa na base (True) ou absoluta (False)
    relative_e = (modo_extrusao == 'relative')
    
    # Gerar G-code da base
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
    
    # Ajustar Z do corpo do slicer
    body_ajustado = ajustar_z_gcode(body_lines_slicer, z_offset)
    
    # Montar G-code final
    # O gcode_base do FullControl já contém header (;STARTGCODE ... G28 etc.)
    # e footer (;ENDGCODE)
    # Precisamos remover o footer do base e o header do slicer
    
    linhas_base = gcode_base.split('\n')
    
    # Encontrar e remover o ;ENDGCODE e tudo depois dele no gcode da base
    idx_end_base = None
    for i, line in enumerate(linhas_base):
        if line.strip() == ';ENDGCODE':
            idx_end_base = i
            break
    
    if idx_end_base is not None:
        linhas_base_corpo = linhas_base[:idx_end_base]
    else:
        linhas_base_corpo = linhas_base
    
    # Adicionar comentário de transição
    linhas_base_corpo.append('')
    linhas_base_corpo.append('; ============================================')
    linhas_base_corpo.append('; TRANSICAO: Base FullControl -> Paredes Slicer')
    linhas_base_corpo.append(f'; Z offset aplicado: +{z_offset:.3f} mm')
    linhas_base_corpo.append(f'; Restaurando modo de extrusao do slicer: {modo_extrusao.upper()}')
    linhas_base_corpo.append('; ============================================')
    
    # IMPORTANTE: Restabelece o modo de extrusão original do slicer e reseta o extrusor
    if modo_extrusao == 'absolute':
        linhas_base_corpo.append('M82 ; modo de extrusao absoluta')
    else:
        linhas_base_corpo.append('M83 ; modo de extrusao relativa')
    
    linhas_base_corpo.append('G92 E0.0 ; resetar extrusor')
    linhas_base_corpo.append('')
    
    # Montar corpo do slicer (ajustado)
    corpo_slicer = ''.join(body_ajustado)
    
    # Footer do slicer
    footer = ''.join(footer_lines_slicer)
    
    # Concatenar tudo
    gcode_final = '\n'.join(linhas_base_corpo) + '\n' + corpo_slicer + footer
    
    return gcode_final


# ==============================================================================
# MÓDULO 5: PÓS-PROCESSAMENTO (limpeza de comentários longos)
# ==============================================================================

def limpar_gcode(gcode_text):
    """Remove comentários desnecessários para compatibilidade com firmware.
    Mesma lógica usada nos scripts cilindro.py e prisma.py.
    """
    linhas = gcode_text.split('\n')
    linhas_limpas = []
    
    for linha in linhas:
        linha = linha.rstrip('\r\n')
        if ';' in linha and not linha.lstrip().startswith(';'):
            # Remove comentários inline
            linha = linha[:linha.index(';')].rstrip()
        elif linha.lstrip().startswith(';'):
            # Preserva marcadores de seção e comentários importantes
            stripped = linha.strip()
            if stripped in (';STARTGCODE', ';ENDGCODE') or stripped.startswith('; ==='):
                pass  # Manter
            elif stripped.startswith('; TRANSICAO') or stripped.startswith('; Z offset') or stripped.startswith('; Restaurando'):
                pass  # Manter
            else:
                continue  # Remover outros comentários
        
        if linha:
            linhas_limpas.append(linha)
    
    return '\n'.join(linhas_limpas) + '\n'


# ==============================================================================
# MÓDULO 6: CLI (argparse)
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Pós-processador: Adiciona base sólida (FullControl) a G-code vase mode (PrusaSlicer)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python gcode_postprocessor.py vaso.gcode --z-ref 1.5 --camadas-base 3
  python gcode_postprocessor.py vaso.gcode --z-ref 1.5 --camadas-base 2 --infill-pattern concentric
  python gcode_postprocessor.py vaso.gcode --z-ref 1.5 --num-perimetros 2 --largura-extrusao 3.0
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
    
    # Validações amigáveis de entrada
    if not args.input:
        print("\n" + "="*60)
        print("  ERRO: Nenhum arquivo G-code de entrada foi fornecido!")
        print("="*60)
        print("Você pode fornecer o arquivo de duas formas:")
        print("  1. Configurando a variável 'INPUT_GCODE' no topo deste script Python.")
        print("  2. Passando o caminho do arquivo por linha de comando:")
        print("     python gcode_postprocessor.py seu_arquivo.gcode")
        print("\nPara ver todas as opções disponíveis, use:")
        print("     python gcode_postprocessor.py --help")
        print("="*60)
        sys.exit(1)
        
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERRO: Arquivo de entrada não encontrado: {args.input}")
        print("Verifique se o caminho do arquivo está correto.")
        sys.exit(1)
    
    if args.output is None:
        args.output = str(input_path.with_suffix('')) + '_com_base.gcode'
    
    # Detecção automática do modo de extrusão
    modo_extrusao = detectar_modo_extrusao(args.input)
    
    # Banner
    print("=" * 60)
    print("  Pos-Processador: PrusaSlicer -> FullControl Base Solida")
    print("=" * 60)
    print(f"\n  Arquivo de entrada: {args.input}")
    print(f"  Modo de extrusao:   {modo_extrusao.upper()}")
    print(f"  Z referencia:       {args.z_ref} mm")
    print(f"  Camadas da base:    {args.camadas_base}")
    print(f"  Largura extrusao:   {args.largura_extrusao} mm")
    print(f"  Altura camada:      {args.altura_camada} mm")
    print(f"  Perimetros:         {args.num_perimetros}")
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
    print(f"\n[3/5] Gerando base solida ({args.camadas_base} camadas)...")
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

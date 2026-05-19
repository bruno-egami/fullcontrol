import fullcontrol as fc
import math

# ==============================================================================
# 1. CONFIGURAÇÕES DO USUÁRIO (PARÂMETROS DO AMBIENTE E GEOMETRIA)
# ==============================================================================

# --- Parâmetros Físicos da Extrusão ---
largura_extrusao = 3.0             # mm (Diâmetro do bico / largura do filete impresso)
altura_camada = 1.5                # mm (Altura de cada camada)

# --- Parâmetros Geométricos do Prisma ---
x_centro, y_centro = 260.0, 45.0   # Centro geométrico da peça na mesa
largura_x = 30.0                   # Largura física da peça no eixo X
comprimento_y = 60.0               # Comprimento físico da peça no eixo Y
z_max_desejado = 15.0              # Altura final total da peça no eixo Z

# --- Parâmetros de Perímetro (Paredes) ---
num_perimetros = 1                 # Número de perímetros/paredes externas (ex: 1, 2, 3...)

# --- Parâmetros de Preenchimento (Infill) ---
infill_percent = 100.0              # Densidade do preenchimento (0% a 100%)
sobreposicao_infill = 0.5          # mm (Sobreposição do infill na parede interna para fusão perfeita)
infill_pattern = 'zigzag'            # Opções: 'zigzag' (Y), 'grid' (X/Y), 'concentric' (anéis), 'gyroid' (senoide 3D)

# --- Controle de Trajetória ---
alternar_ordem_camadas = False     # True: Ímpares fazem Infill primeiro. False: Sempre faz Perímetro primeiro.

# --- Parâmetros Específicos para o Padrão Giroide ---
amplitude_gyroid = 2.0             # mm (Largura/amplitude da onda senoidal do giroide)
comprimento_onda_gyroid = 15.0     # mm (Distância de um ciclo completo da onda)

# --- Velocidades de Movimentação ---
velocidade_impressao = 600         # mm/min (10 mm/s) - recomendada vazão lenta para bico grande de 3mm
velocidade_travel = 3000           # mm/min (50 mm/s) - velocidade para movimentos livres de extrusão

# --- Controle de Fluxo (Extrusão) ---
fluxo_camada_inicial = 90.0        # % (Percentual de fluxo na 1ª camada, reduz o excesso de material/pé de elefante)
fluxo_demais_camadas = 100.0       # % (Percentual de fluxo a partir da camada 1)

# ==============================================================================
# 2. INICIALIZAÇÃO E COMANDOS DE FIRMWARE
# ==============================================================================

steps = []
steps.append(fc.Printer(print_speed=velocidade_impressao, travel_speed=velocidade_travel))
steps.append(fc.ManualGcode(text="M204 P500 T500 ; Configura aceleração para 500 mm/s²"))
steps.append(fc.ExtrusionGeometry(area_model='rectangle', width=largura_extrusao, height=altura_camada))

steps.append(fc.ManualGcode(text="; --- PURGA PERSONALIZADA FORA DA MESA (X300 Y0 Z0) ---"))
steps.append(fc.ManualGcode(text="G1 E25 F100 ; Purga"))
steps.append(fc.ManualGcode(text="G92 E0.0"))

# ==============================================================================
# 3. PROCESSAMENTO MATEMÁTICO DOS PARÂMETROS
# ==============================================================================

x_min, x_max = x_centro - (largura_x / 2), x_centro + (largura_x / 2)
y_min, y_max = y_centro - (comprimento_y / 2), y_centro + (comprimento_y / 2)

recuo = largura_extrusao / 2
x_p_min_outer, x_p_max_outer = x_min + recuo, x_max - recuo
y_p_min_outer, y_p_max_outer = y_min + recuo, y_max - recuo

innermost_offset = recuo + (num_perimetros - 1) * (largura_extrusao * 0.95)
x_innermost_min, x_innermost_max = x_min + innermost_offset, x_max - innermost_offset
y_innermost_min, y_innermost_max = y_min + innermost_offset, y_max - innermost_offset

espacamento_alvo = (largura_extrusao * 0.95) / (infill_percent / 100.0) if infill_percent > 0 else 9999.0

# --- INFILL VERTICAL (X) ---
x_infill_min = x_innermost_min + largura_extrusao * 0.95
x_infill_max = x_innermost_max - largura_extrusao * 0.95
espaco_disponivel_x = x_infill_max - x_infill_min

if infill_percent <= 0 or espaco_disponivel_x <= 0:
    num_linhas_infill_x = 0
    x_coords_infill = []
else:
    num_linhas_infill_x = max(2, int(round(espaco_disponivel_x / espacamento_alvo)) + 1)
    x_coords_infill = [x_infill_min + i * (espaco_disponivel_x) / (num_linhas_infill_x - 1) for i in range(num_linhas_infill_x)]

y_infill_min_vert = y_innermost_min + recuo - sobreposicao_infill
y_infill_max_vert = y_innermost_max - recuo + sobreposicao_infill

# --- INFILL HORIZONTAL (Y) ---
y_infill_min = y_innermost_min + largura_extrusao * 0.95
y_infill_max = y_innermost_max - largura_extrusao * 0.95
espaco_disponivel_y = y_infill_max - y_infill_min

if infill_percent <= 0 or espaco_disponivel_y <= 0:
    num_linhas_infill_y = 0
    y_coords_infill = []
else:
    num_linhas_infill_y = max(2, int(round(espaco_disponivel_y / espacamento_alvo)) + 1)
    # Lista invertida (Top para Bottom)
    y_coords_infill = [y_infill_max - i * (espaco_disponivel_y) / (num_linhas_infill_y - 1) for i in range(num_linhas_infill_y)]

x_infill_min_horiz = x_innermost_min + recuo - sobreposicao_infill
x_infill_max_horiz = x_innermost_max - recuo + sobreposicao_infill

# --- INFILL CONCÊNTRICO ---
offsets_concentricos = []
max_offset_x = (x_max - x_min) / 2
max_offset_y = (y_max - y_min) / 2
max_offset = min(max_offset_x, max_offset_y)

if infill_percent > 0:
    off = innermost_offset + espacamento_alvo
    while off < max_offset - 0.5:
        offsets_concentricos.append(off)
        off += espacamento_alvo

num_camadas = math.ceil(z_max_desejado / altura_camada)

# ==============================================================================
# MOTOR DINÂMICO DE TRAJETÓRIAS (Zero Travels)
# ==============================================================================

# Cria pontos segmentados matematicamente aproximando uma função seno para o Gyroid
def gerar_onda_y(x_c, y_start, y_end, z, phase, amplitude, comprimento_onda):
    pts = []
    passo_y = 1.0 # Densidade da onda: 1mm de segmentação garante curvaturas suaves
    dist = abs(y_end - y_start)
    num_pts = max(10, int(dist / passo_y))
    # Para garantir o cruzamento, a fase depende estritamente da coordenada global
    y_anchor = y_centro - comprimento_y / 2
    for j in range(num_pts + 1):
        t = j / num_pts
        y = y_start + t * (y_end - y_start)
        x = x_c + amplitude * math.sin(2 * math.pi * (y - y_anchor) / comprimento_onda + phase)
        pts.append(fc.Point(x=x, y=y, z=z))
    return pts

# Identifica matematicamente em qual dos 4 quadrantes lógicos (Left/Top) o bico está
def get_corner_flags(x, y, x_min_b, x_max_b, y_min_b, y_max_b):
    is_left = abs(x - x_min_b) <= abs(x - x_max_b)
    is_top = abs(y - y_max_b) <= abs(y - y_min_b)
    return is_left, is_top

# Função de segurança para extrair a última coordenada (X,Y) mesmo com comandos Extruder na lista
def get_last_point(steps):
    for step in reversed(steps):
        if hasattr(step, 'x'):
            return step.x, step.y
    return 0, 0

# Detecção automática de continuidade: se o próximo ponto estiver longe, faz uma viagem vazia (Travel)
def adicionar_caminho_seguro(steps, pts):
    if not pts: return
    lx, ly = get_last_point(steps)
    dist = math.hypot(pts[0].x - lx, pts[0].y - ly)
    if dist > 0.5: # Quebra de continuidade detectada (distância maior que meio mm)
        steps.append(fc.Extruder(on=False))
        steps.append(pts[0])
        steps.append(fc.Extruder(on=True))
        steps.extend(pts[1:])
    else:
        steps.extend(pts)

# Motor unificado de perímetros: Descobre o vértice mais próximo, inicia por ele e não solta!
def gerar_perimetros_dinamicos(num_perim, x_min_b, x_max_b, y_min_b, y_max_b, z, recuo, espessura, start_x, start_y, out_to_in=True, anti_horario=True):
    pts = []
    x_p_min_out, x_p_max_out = x_min_b + recuo, x_max_b - recuo
    y_p_min_out, y_p_max_out = y_min_b + recuo, y_max_b - recuo
    
    # Cantos da borda que será avaliada (sempre a externa para referência de distância)
    corners_out = [
        fc.Point(x=x_p_min_out, y=y_p_max_out, z=z), # 0: TL
        fc.Point(x=x_p_min_out, y=y_p_min_out, z=z), # 1: BL
        fc.Point(x=x_p_max_out, y=y_p_min_out, z=z), # 2: BR
        fc.Point(x=x_p_max_out, y=y_p_max_out, z=z)  # 3: TR
    ]
    
    # Acha o canto lógico mais próximo de onde o bico está
    idx_start = 0
    min_d = 999999
    for i, c in enumerate(corners_out):
        d = math.hypot(c.x - start_x, c.y - start_y)
        if d < min_d:
            min_d = d
            idx_start = i
            
    p_range = range(num_perim) if out_to_in else range(num_perim-1, -1, -1)
    
    for idx_p, p in enumerate(p_range):
        p_offset = recuo + p * espessura
        x1, x2 = x_min_b + p_offset, x_max_b - p_offset
        y1, y2 = y_min_b + p_offset, y_max_b - p_offset
        
        c_p = [
            fc.Point(x=x1, y=y2, z=z), # 0: TL
            fc.Point(x=x1, y=y1, z=z), # 1: BL
            fc.Point(x=x2, y=y1, z=z), # 2: BR
            fc.Point(x=x2, y=y2, z=z)  # 3: TR
        ]
        
        loop = []
        if anti_horario:
            for i in range(5): loop.append(c_p[(idx_start + i) % 4])
        else:
            for i in range(5): loop.append(c_p[(idx_start - i) % 4])
                
        pts.extend(loop)
            
    is_left = (idx_start == 0 or idx_start == 1)
    is_top = (idx_start == 0 or idx_start == 3)
    return pts, is_left, is_top

def gerar_infill_vertical_dinamico(x_coords, y_min, y_max, z, start_left, start_top, pattern, phase, amplitude, comp_onda):
    if len(x_coords) == 0: return []
    pts = []
    x_range = range(len(x_coords)) if start_left else range(len(x_coords)-1, -1, -1)
    
    for idx, i in enumerate(x_range):
        x = x_coords[i]
        go_down = (idx % 2 == 0) if start_top else (idx % 2 != 0)
        y_start, y_end = (y_max, y_min) if go_down else (y_min, y_max)
        
        if pattern == 'gyroid':
            pts.extend(gerar_onda_y(x, y_start, y_end, z, phase, amplitude, comp_onda))
        else:
            if idx == 0: pts.append(fc.Point(x=x, y=y_start, z=z))
            pts.append(fc.Point(x=x, y=y_end, z=z))
            
        if idx < len(x_coords) - 1:
            pts.append(fc.Point(x=x_coords[x_range[idx+1]], y=y_end, z=z))
    return pts

def gerar_infill_horizontal_dinamico(y_coords, x_min, x_max, z, start_left, start_top):
    if len(y_coords) == 0: return []
    pts = []
    y_range = range(len(y_coords)) if start_top else range(len(y_coords)-1, -1, -1)
    
    for idx, i in enumerate(y_range):
        y = y_coords[i]
        go_right = (idx % 2 == 0) if start_left else (idx % 2 != 0)
        x_start, x_end = (x_min, x_max) if go_right else (x_max, x_min)
        
        if idx == 0: pts.append(fc.Point(x=x_start, y=y, z=z))
        pts.append(fc.Point(x=x_end, y=y, z=z))
        
        if idx < len(y_coords) - 1:
            pts.append(fc.Point(x=x_end, y=y_coords[y_range[idx+1]], z=z))
    return pts

# ==============================================================================
# 4. GERAÇÃO DA PEÇA (Caminho Contínuo Total)
# ==============================================================================

# Primeira viagem de aproximação até o ponto 0 da peça (com extrusor desligado)
steps.append(fc.Extruder(on=False))
steps.append(fc.Point(x=x_p_min_outer, y=y_p_max_outer, z=altura_camada))
steps.append(fc.Extruder(on=True)) # Abre o fluxo

# Loop contínuo que desenha a peça camada a camada
for camada in range(num_camadas):
    z_atual = altura_camada + (camada * altura_camada)
    eh_par = (camada % 2 == 0)
    
    # Aplica a alteração dinâmica de fluxo
    if camada == 0:
        steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_camada_inicial)} ; Configura fluxo da primeira camada"))
    elif camada == 1:
        steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_demais_camadas)} ; Restaura fluxo para as demais camadas"))
        
    if camada > 0:
        # Puxa o último X,Y conhecido e apenas eleva o bico no eixo Z, exatamente onde ele parou!
        lx, ly = get_last_point(steps)
        steps.append(fc.Point(x=lx, y=ly, z=z_atual))
        
    if eh_par or not alternar_ordem_camadas:
        # --- PERÍMETRO -> INFILL ---
        # 1. Perímetro (Começa dinamicamente no canto em que a extrusora já estiver!)
        start_x, start_y = get_last_point(steps)
        pts_perim, is_left, is_top = gerar_perimetros_dinamicos(
            num_perimetros, x_min, x_max, y_min, y_max, z_atual, recuo, largura_extrusao * 0.95,
            start_x, start_y, out_to_in=True, anti_horario=True
        )
        adicionar_caminho_seguro(steps, pts_perim)
        
        # 2. Infill (Puxa os rastros de onde o perímetro parou!)
        if infill_pattern == 'concentric':
            lx, ly = get_last_point(steps)
            pts_infill, _, _ = gerar_perimetros_dinamicos(
                len(offsets_concentricos), x_min, x_max, y_min, y_max, z_atual, offsets_concentricos[0] if offsets_concentricos else 0, espacamento_alvo,
                lx, ly, out_to_in=True, anti_horario=True
            )
            adicionar_caminho_seguro(steps, pts_infill)
            
        elif infill_pattern == 'grid' and not eh_par:
            pts_infill = gerar_infill_horizontal_dinamico(
                y_coords_infill, x_infill_min_horiz, x_infill_max_horiz, z_atual, is_left, is_top
            )
            adicionar_caminho_seguro(steps, pts_infill)
            
        elif infill_pattern in ['zigzag', 'gyroid', 'grid']:
            phase = math.pi if (not eh_par and infill_pattern == 'gyroid') else 0
            pts_infill = gerar_infill_vertical_dinamico(
                x_coords_infill, y_infill_min_vert, y_infill_max_vert, z_atual,
                is_left, is_top, infill_pattern, phase, amplitude_gyroid, comprimento_onda_gyroid
            )
            adicionar_caminho_seguro(steps, pts_infill)
            
    else:
        # --- INFILL -> PERÍMETRO ---
        start_x, start_y = get_last_point(steps)
        is_left, is_top = get_corner_flags(start_x, start_y, x_min, x_max, y_min, y_max)
        
        # 1. Infill
        if infill_pattern == 'concentric':
            pts_infill, _, _ = gerar_perimetros_dinamicos(
                len(offsets_concentricos), x_min, x_max, y_min, y_max, z_atual, offsets_concentricos[0] if offsets_concentricos else 0, espacamento_alvo,
                start_x, start_y, out_to_in=False, anti_horario=False
            )
            adicionar_caminho_seguro(steps, pts_infill)
            
        elif infill_pattern == 'grid':
            pts_infill = gerar_infill_horizontal_dinamico(
                y_coords_infill, x_infill_min_horiz, x_infill_max_horiz, z_atual, is_left, is_top
            )
            adicionar_caminho_seguro(steps, pts_infill)
            
        elif infill_pattern in ['zigzag', 'gyroid']:
            pts_infill = gerar_infill_vertical_dinamico(
                x_coords_infill, y_infill_min_vert, y_infill_max_vert, z_atual,
                is_left, is_top, infill_pattern, math.pi, amplitude_gyroid, comprimento_onda_gyroid
            )
            adicionar_caminho_seguro(steps, pts_infill)
            
        # 2. Perímetro
        start_x, start_y = get_last_point(steps)
        pts_perim, _, _ = gerar_perimetros_dinamicos(
            num_perimetros, x_min, x_max, y_min, y_max, z_atual, recuo, largura_extrusao * 0.95,
            start_x, start_y, out_to_in=False, anti_horario=False
        )
        adicionar_caminho_seguro(steps, pts_perim)

steps.append(fc.Extruder(on=False))

# ==============================================================================
# 5. GERAÇÃO DO G-CODE
# ==============================================================================
gcode = fc.transform(steps, 'gcode', fc.GcodeControls(
    printer_name='Community/Cliever CL2Pro', 
    save_as='prisma_solido',
    initialization_data={
        'primer': 'no_primer', 
        'dia_feed': 1.75,
        'extrusion_width': largura_extrusao,
        'extrusion_height': altura_camada
    }
))

print(f"G-code gerado com sucesso!")
print(f"-> Trajetória 100% dinâmica. Travels e cruzamentos eliminados.")

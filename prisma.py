import fullcontrol as fc
import math

# ==============================================================================
# 1. CONFIGURAÇÕES DO USUÁRIO (PARÂMETROS DO AMBIENTE E GEOMETRIA)
# ==============================================================================

# --- Parâmetros Físicos da Extrusão ---
largura_extrusao = 3.0             # mm (Diâmetro do bico / largura do filete impresso)
altura_camada = 1.5                # mm (Altura de cada camada)

# --- Parâmetros de Priming (Clay DIW) ---
priming_ativo = True                # Habilita priming automático após travels
priming_quantidade = 10.0          # mm de extrusão extra de material (quantidade)
priming_velocidade = 100           # mm/min (velocidade de priming)

# --- Parâmetros de Transição para o Modo Vaso ---
transicao_vaso_z_offset = 0.3       # mm (Espaço vertical extra no início do vasemode para evitar esmagamento)
transicao_vaso_fluxo = 85.0         # % (Fluxo de transição reduzido para a primeira camada do vasemode)

# --- Parâmetros Geométricos do Prisma ---
x_centro, y_centro = 260.0, 45.0   # Centro geométrico da peça na mesa
largura_x = 30.0                   # Largura física da peça no eixo X
comprimento_y = 60.0               # Comprimento físico da peça no eixo Y
z_max_desejado = 15.0              # Altura final total da peça no eixo Z

# --- Zonas de Configuração por Camada ---
# Defina o perfil da peça. Cada zona se aplica a partir da 'camada_inicio'.
zonas_camadas = [
    {
        'camada_inicio': 0,
        'num_perimetros': 1,
        'infill_percent': 100.0,
        'infill_pattern': 'concentric',
        'fluxo_perimetro': 90.0,
        'fluxo_infill': 90.0,
        'espiral': False
    },
    {
        'camada_inicio': 3,
        'num_perimetros': 1,
        'infill_percent': 0.0,
        'infill_pattern': 'zigzag',
        'fluxo_perimetro': 100.0,
        'fluxo_infill': 100.0,
        'espiral': True
    }
]

# --- Controle de Trajetória ---
alternar_ordem_camadas = True     # True: Ímpares fazem Infill primeiro. False: Sempre faz Perímetro primeiro.

# --- Controle de Rotação de Infill ---
angulo_infill_base = 45.0          # Graus. Padrões alternarão entre +ângulo e -ângulo a cada camada.

# --- Parâmetros Específicos para o Padrão Giroide ---
amplitude_gyroid = 2.0             # mm (Largura/amplitude da onda senoidal do giroide)
comprimento_onda_gyroid = 15.0     # mm (Distância de um ciclo completo da onda)

# --- Velocidades de Movimentação ---
velocidade_impressao = 600         # mm/min (10 mm/s) - recomendada vazão lenta para bico grande de 3mm
velocidade_travel = 3000           # mm/min (50 mm/s) - velocidade para movimentos livres de extrusão

# --- Controle Extra de Infill ---
sobreposicao_infill = 0.5          # mm (Sobreposição do infill na parede interna para fusão perfeita)

# ==============================================================================
# 2. INICIALIZAÇÃO E COMANDOS DE FIRMWARE
# ==============================================================================

steps = []
steps.append(fc.Printer(print_speed=velocidade_impressao, travel_speed=velocidade_travel))
steps.append(fc.ManualGcode(text="M204 P500 T500"))
steps.append(fc.ExtrusionGeometry(area_model='rectangle', width=largura_extrusao, height=altura_camada))

# ==============================================================================
# 3. PROCESSAMENTO MATEMÁTICO DOS PARÂMETROS
# ==============================================================================

x_min, x_max = x_centro - (largura_x / 2), x_centro + (largura_x / 2)
y_min, y_max = y_centro - (comprimento_y / 2), y_centro + (comprimento_y / 2)

recuo = largura_extrusao / 2
x_p_min_outer, x_p_max_outer = x_min + recuo, x_max - recuo
y_p_min_outer, y_p_max_outer = y_min + recuo, y_max - recuo

num_camadas = math.ceil(z_max_desejado / altura_camada)

def obter_zona(camada):
    zona_ativa = zonas_camadas[0]
    for zona in zonas_camadas:
        if camada >= zona['camada_inicio']:
            zona_ativa = zona
    return zona_ativa

# ==============================================================================
# MOTOR DINÂMICO DE TRAJETÓRIAS (Zero Travels)
# ==============================================================================


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

def orientar_caminho(pts, start_x, start_y):
    if not pts: return pts
    dist_start = math.hypot(pts[0].x - start_x, pts[0].y - start_y)
    dist_end = math.hypot(pts[-1].x - start_x, pts[-1].y - start_y)
    if dist_end < dist_start:
        pts.reverse()
    return pts

def intersect_line_rect_param(v, theta_rad, Xc, Yc, Xmin, Xmax, Ymin, Ymax):
    cos_t = math.cos(theta_rad)
    sin_t = math.sin(theta_rad)
    t_vals = []
    
    # Interseções com as paredes verticais (X)
    if abs(cos_t) > 1e-6:
        t1 = (Xmin - Xc + v * sin_t) / cos_t
        y1 = Yc + v * cos_t + t1 * sin_t
        if Ymin - 1e-5 <= y1 <= Ymax + 1e-5: t_vals.append(t1)
            
        t2 = (Xmax - Xc + v * sin_t) / cos_t
        y2 = Yc + v * cos_t + t2 * sin_t
        if Ymin - 1e-5 <= y2 <= Ymax + 1e-5: t_vals.append(t2)
            
    # Interseções com as paredes horizontais (Y)
    if abs(sin_t) > 1e-6:
        t3 = (Ymin - Yc - v * cos_t) / sin_t
        x3 = Xc - v * sin_t + t3 * cos_t
        if Xmin - 1e-5 <= x3 <= Xmax + 1e-5: t_vals.append(t3)
            
        t4 = (Ymax - Yc - v * cos_t) / sin_t
        x4 = Xc - v * sin_t + t4 * cos_t
        if Xmin - 1e-5 <= x4 <= Xmax + 1e-5: t_vals.append(t4)
            
    if not t_vals: return None
    t_min, t_max = min(t_vals), max(t_vals)
    if t_max - t_min < 1e-5: return None
    
    p1 = (Xc - v * sin_t + t_min * cos_t, Yc + v * cos_t + t_min * sin_t)
    p2 = (Xc - v * sin_t + t_max * cos_t, Yc + v * cos_t + t_max * sin_t)
    return p1, p2, t_min, t_max

def gerar_infill_rotacionado(angulo_graus, x_min_b, x_max_b, y_min_b, y_max_b, z, espacamento, pattern, phase, amplitude, comprimento_onda):
    theta = math.radians(angulo_graus)
    Xc = (x_min_b + x_max_b) / 2
    Yc = (y_min_b + y_max_b) / 2
    
    # Encontra os limites da varredura (v_min e v_max) projetando as 4 quinas
    corners = [(x_min_b, y_min_b), (x_max_b, y_min_b), (x_max_b, y_max_b), (x_min_b, y_max_b)]
    v_vals = [-(x - Xc)*math.sin(theta) + (y - Yc)*math.cos(theta) for x, y in corners]
    v_min, v_max = min(v_vals), max(v_vals)
    
    pts = []
    # Alinha v_start a um múltiplo do espaçamento para os padrões casarem entre camadas!
    v_current = math.ceil(v_min / espacamento) * espacamento
    flip = False
    
    while v_current <= v_max + 1e-5:
        segment = intersect_line_rect_param(v_current, theta, Xc, Yc, x_min_b, x_max_b, y_min_b, y_max_b)
        if segment:
            p1, p2, t_min, t_max = segment
                
            if pattern == 'gyroid':
                # Estende a varredura além da parede para que a onda ultrapasse o limite
                margin = amplitude + 1.0
                t_start = t_max + margin if flip else t_min - margin
                t_end = t_min - margin if flip else t_max + margin
                
                dist = abs(t_end - t_start)
                num_pts = max(10, int(dist / 1.0))
                
                for j in range(num_pts + 1):
                    t_val = t_start + j * ((t_end - t_start) / num_pts)
                    x_base = Xc - v_current * math.sin(theta) + t_val * math.cos(theta)
                    y_base = Yc + v_current * math.cos(theta) + t_val * math.sin(theta)
                    
                    t_along_line = (x_base - Xc) * math.cos(theta) + (y_base - Yc) * math.sin(theta)
                    wave_offset = amplitude * math.sin(2 * math.pi * t_along_line / comprimento_onda + phase)
                    
                    x_final = x_base - wave_offset * math.sin(theta)
                    y_final = y_base + wave_offset * math.cos(theta)
                    
                    # Clamp rígido contra a parede: "esmaga" a onda excedente contra a parede
                    x_clamped = max(x_min_b, min(x_max_b, x_final))
                    y_clamped = max(y_min_b, min(y_max_b, y_final))
                    
                    # Evita duplicar pontos perfeitamente iguais devido ao clamp
                    if not pts or abs(pts[-1].x - x_clamped) > 1e-4 or abs(pts[-1].y - y_clamped) > 1e-4:
                        pts.append(fc.Point(x=x_clamped, y=y_clamped, z=z))
            else: # Zigzag e Grid
                p_start, p_end = (p2, p1) if flip else (p1, p2)
                pts.append(fc.Point(x=p_start[0], y=p_start[1], z=z))
                pts.append(fc.Point(x=p_end[0], y=p_end[1], z=z))
                
        v_current += espacamento
        flip = not flip
        
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

# Modo Espiral Contínua: percorre os 4 lados do retângulo interpolando o eixo Z linearmente.
# Z sobe exatamente 1/4 da altura_camada a cada segmento.
def gerar_espiral_retangular(x_min_b, x_max_b, y_min_b, y_max_b, z_inicio, altura_cam, recuo, start_x, start_y, anti_horario=True):
    pts = []
    x_p_min_out, x_p_max_out = x_min_b + recuo, x_max_b - recuo
    y_p_min_out, y_p_max_out = y_min_b + recuo, y_max_b - recuo
    
    corners_out = [
        (x_p_min_out, y_p_max_out), # 0: TL
        (x_p_min_out, y_p_min_out), # 1: BL
        (x_p_max_out, y_p_min_out), # 2: BR
        (x_p_max_out, y_p_max_out)  # 3: TR
    ]
    
    idx_start = 0
    min_d = 999999
    for i, (cx, cy) in enumerate(corners_out):
        d = math.hypot(cx - start_x, cy - start_y)
        if d < min_d:
            min_d = d
            idx_start = i
            
    # Ordem dos cantos partindo do mais próximo
    loop_corners = []
    if anti_horario:
        for i in range(5): loop_corners.append(corners_out[(idx_start + i) % 4])
    else:
        for i in range(5): loop_corners.append(corners_out[(idx_start - i) % 4])
        
    # Primeiro ponto (exatamente no Z_inicio)
    cx, cy = loop_corners[0]
    pts.append(fc.Point(x=cx, y=cy, z=z_inicio))
    
    # 4 segmentos = 4 cantos seguintes
    for i in range(1, 5):
        cx, cy = loop_corners[i]
        z_atual = z_inicio + (i / 4.0) * altura_cam
        pts.append(fc.Point(x=cx, y=cy, z=z_atual))
        
    return pts


def gerar_espiral_concentrica_retangular(x_min_b, x_max_b, y_min_b, y_max_b, z, offset_inicial, espacamento, start_x, start_y, out_to_in=True, anti_horario=True):
    pts = []
    
    # Encontra os offsets limites
    max_offset_x = (x_max_b - x_min_b) / 2
    max_offset_y = (y_max_b - y_min_b) / 2
    max_offset = min(max_offset_x, max_offset_y)
    
    # Centro geométrico
    x_centro = (x_min_b + x_max_b) / 2
    y_centro = (y_min_b + y_max_b) / 2
    
    # Número de voltas completas - usando floor para evitar duplicidade ou linhas excessivamente próximas
    distancia = max_offset - offset_inicial
    num_voltas = int(math.floor(distancia / espacamento))
    if num_voltas < 1:
        num_voltas = 1
        
    eixo_y_maior = max_offset_y >= max_offset_x

    def gerar_caminho_base(idx_start, anti_horario_dir):
        pts_base = []
        for p in range(num_voltas):
            offset_p = offset_inicial + p * espacamento
            offset_next = offset_inicial + (p + 1) * espacamento
            if p == num_voltas - 1:
                offset_next = max_offset
                
            x1_p, x2_p = x_min_b + offset_p, x_max_b - offset_p
            y1_p, y2_p = y_min_b + offset_p, y_max_b - offset_p
            
            x1_next, x2_next = x_min_b + offset_next, x_max_b - offset_next
            y1_next, y2_next = y_min_b + offset_next, y_max_b - offset_next
            
            C_p = [
                (x1_p, y2_p), # 0: TL
                (x1_p, y1_p), # 1: BL
                (x2_p, y1_p), # 2: BR
                (x2_p, y2_p)  # 3: TR
            ]
            
            C_next = [
                (x1_next, y2_next), # 0: TL
                (x1_next, y1_next), # 1: BL
                (x2_next, y1_next), # 2: BR
                (x2_next, y2_next)  # 3: TR
            ]
            
            if anti_horario_dir:
                idxs = [idx_start, (idx_start + 1) % 4, (idx_start + 2) % 4, (idx_start + 3) % 4]
            else:
                idxs = [idx_start, (idx_start - 1) % 4, (idx_start - 2) % 4, (idx_start - 3) % 4]
                
            pts_base.append(fc.Point(x=C_p[idxs[0]][0], y=C_p[idxs[0]][1], z=z))
            pts_base.append(fc.Point(x=C_p[idxs[1]][0], y=C_p[idxs[1]][1], z=z))
            pts_base.append(fc.Point(x=C_p[idxs[2]][0], y=C_p[idxs[2]][1], z=z))
            pts_base.append(fc.Point(x=C_p[idxs[3]][0], y=C_p[idxs[3]][1], z=z))
            
            p_start = C_p[idxs[3]]
            p_end = C_next[idxs[0]]
            
            # Se a 4ª coordenada (p_start) tem o mesmo Y que a 1ª coordenada (C_p[idxs[0]]), a 4ª linha é horizontal
            if abs(p_start[1] - C_p[idxs[0]][1]) < 1e-4:
                p_trans = (p_end[0], p_start[1])
            else:
                p_trans = (p_start[0], p_end[1])
                
            pts_base.append(fc.Point(x=p_trans[0], y=p_trans[1], z=z))
            
            # Na última volta, adicionamos o ponto final da rampa para fechar a espiral antes da espinha
            if p == num_voltas - 1:
                pts_base.append(fc.Point(x=p_end[0], y=p_end[1], z=z))
                
        p_last = pts_base[-1]
        p_last_y = p_last.y
        p_last_x = p_last.x
        
        if eixo_y_maior:
            y_bottom_spine = y_min_b + max_offset
            y_top_spine = y_max_b - max_offset
            if abs(p_last_y - y_top_spine) < 1e-4:
                y_target_spine = y_bottom_spine
            else:
                y_target_spine = y_top_spine
                
            spine_len = abs(y_target_spine - p_last_y)
            steps_spine = max(2, int(math.ceil(spine_len / 1.0)))
            for i in range(1, steps_spine + 1):
                y_val = p_last_y + (i / steps_spine) * (y_target_spine - p_last_y)
                pts_base.append(fc.Point(x=x_centro, y=y_val, z=z))
        else:
            x_left_spine = x_min_b + max_offset
            x_right_spine = x_max_b - max_offset
            if abs(p_last_x - x_left_spine) < 1e-4:
                x_target_spine = x_right_spine
            else:
                x_target_spine = x_left_spine
                
            spine_len = abs(x_target_spine - p_last_x)
            steps_spine = max(2, int(math.ceil(spine_len / 1.0)))
            for i in range(1, steps_spine + 1):
                x_val = p_last_x + (i / steps_spine) * (x_target_spine - p_last_x)
                pts_base.append(fc.Point(x=x_val, y=y_centro, z=z))
                
        return pts_base

    # Agora decidimos como gerar com base em out_to_in
    if out_to_in:
        x1_ref, x2_ref = x_min_b + offset_inicial, x_max_b - offset_inicial
        y1_ref, y2_ref = y_min_b + offset_inicial, y_max_b - offset_inicial
        corners_ref = [
            (x1_ref, y2_ref), # 0: TL
            (x1_ref, y1_ref), # 1: BL
            (x2_ref, y1_ref), # 2: BR
            (x2_ref, y2_ref)  # 3: TR
        ]
        
        idx_start = 0
        min_d = 999999
        for i, (cx, cy) in enumerate(corners_ref):
            d = math.hypot(cx - start_x, cy - start_y)
            if d < min_d:
                min_d = d
                idx_start = i
                
        pts = gerar_caminho_base(idx_start, anti_horario)
        return pts
    else:
        best_pts = None
        min_d = 999999
        
        for idx in range(4):
            pts_try = gerar_caminho_base(idx, not anti_horario)
            p_final = pts_try[-1]
            d = math.hypot(p_final.x - start_x, p_final.y - start_y)
            if d < min_d:
                min_d = d
                best_pts = pts_try
                
        best_pts.reverse()
        return best_pts


# ==============================================================================
# 4. GERAÇÃO DA PEÇA (Caminho Contínuo Total)
# ==============================================================================

# Primeira viagem de aproximação até o ponto 0 da peça (com extrusor desligado)
steps.append(fc.Extruder(on=False))
steps.append(fc.Point(x=x_p_min_outer, y=y_p_max_outer, z=altura_camada))
steps.append(fc.Extruder(on=True)) # Abre o fluxo

ultimo_era_espiral = False
# Loop contínuo que desenha a peça camada a camada
for camada in range(num_camadas):
    z_atual = altura_camada + (camada * altura_camada)
    eh_par = (camada % 2 == 0)
    
    # Extrai os parâmetros dinâmicos da zona atual
    zona_ativa = obter_zona(camada)
    num_perimetros = zona_ativa.get('num_perimetros', 1)
    infill_percent = zona_ativa.get('infill_percent', 0.0)
    infill_pattern = zona_ativa.get('infill_pattern', 'zigzag')
    fluxo_perim_atual = zona_ativa.get('fluxo_perimetro', 100.0)
    fluxo_infill_atual = zona_ativa.get('fluxo_infill', 100.0)
    espiral = zona_ativa.get('espiral', False)
    
    espacamento_alvo = (largura_extrusao * 0.95) / (infill_percent / 100.0) if infill_percent > 0 else 9999.0

    # Recalcula limites baseados no número de perímetros da zona atual
    if num_perimetros == 0:
        # Sem perímetros, a base sólida é feita apenas de infill.
        # Não precisa ficar 1 perímetro maior. Começa exatamente no recuo padrão (borda).
        innermost_offset = recuo - espacamento_alvo
    else:
        innermost_offset = recuo + (num_perimetros - 1) * (largura_extrusao * 0.95)
    x_innermost_min, x_innermost_max = x_min + innermost_offset, x_max - innermost_offset
    y_innermost_min, y_innermost_max = y_min + innermost_offset, y_max - innermost_offset

    x_infill_bound_min = x_innermost_min + recuo - sobreposicao_infill
    x_infill_bound_max = x_innermost_max - recuo + sobreposicao_infill
    y_infill_bound_min = y_innermost_min + recuo - sobreposicao_infill
    y_infill_bound_max = y_innermost_max - recuo + sobreposicao_infill

    # --- MODO ESPIRAL CONTÍNUA (Vase Mode) ---
    if espiral:
        steps.append(fc.ManualGcode(text="; --- ESPIRAL START ---"))
        
        # Identifica se é a camada de transição (primeira camada do vasemode)
        eh_transicao_vaso = not ultimo_era_espiral
        ultimo_era_espiral = True
        
        if eh_transicao_vaso:
            z_inicio = z_atual - altura_camada + transicao_vaso_z_offset
            altura_cam_atual = altura_camada - transicao_vaso_z_offset
            fluxo_atual = transicao_vaso_fluxo
        else:
            z_inicio = z_atual - altura_camada
            altura_cam_atual = altura_camada
            fluxo_atual = fluxo_perim_atual
            
        steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_atual)}"))
        start_x, start_y = get_last_point(steps)
        pts_espiral = gerar_espiral_retangular(x_min, x_max, y_min, y_max, z_inicio, altura_cam_atual, recuo, start_x, start_y, anti_horario=True)
        adicionar_caminho_seguro(steps, pts_espiral)
        continue
    else:
        ultimo_era_espiral = False
        steps.append(fc.ManualGcode(text="; --- ESPIRAL END ---"))

    # --- MODO TRADICIONAL DISCRETO ---
    if camada > 0:
        # Puxa o último X,Y conhecido e apenas eleva o bico no eixo Z, exatamente onde ele parou!
        lx, ly = get_last_point(steps)
        steps.append(fc.Extruder(on=False))
        steps.append(fc.Point(x=lx, y=ly, z=z_atual))
        steps.append(fc.Extruder(on=True))
        
    # Alternância Angular
    angulo_atual = angulo_infill_base if eh_par else -angulo_infill_base
    
    if eh_par or not alternar_ordem_camadas:
        # --- PERÍMETRO -> INFILL ---
        steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_perim_atual)}"))
        start_x, start_y = get_last_point(steps)
        pts_perim, is_left, is_top = gerar_perimetros_dinamicos(
            num_perimetros, x_min, x_max, y_min, y_max, z_atual, recuo, largura_extrusao,
            start_x, start_y, out_to_in=True, anti_horario=True
        )
        adicionar_caminho_seguro(steps, pts_perim)
        
        if infill_percent > 0:
            steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_infill_atual)}"))
            if infill_pattern == 'concentric':
                lx, ly = get_last_point(steps)
                pts_infill = gerar_espiral_concentrica_retangular(
                    x_min, x_max, y_min, y_max, z_atual, innermost_offset + espacamento_alvo, espacamento_alvo,
                    lx, ly, out_to_in=True, anti_horario=True
                )
                adicionar_caminho_seguro(steps, pts_infill)
                
            elif infill_pattern == 'grid':
                pts1 = gerar_infill_rotacionado(angulo_atual, x_infill_bound_min, x_infill_bound_max, y_infill_bound_min, y_infill_bound_max, z_atual, espacamento_alvo * 2, 'zigzag', 0, 0, 0)
                pts2 = gerar_infill_rotacionado(angulo_atual + 90, x_infill_bound_min, x_infill_bound_max, y_infill_bound_min, y_infill_bound_max, z_atual, espacamento_alvo * 2, 'zigzag', 0, 0, 0)
                
                lx, ly = get_last_point(steps)
                adicionar_caminho_seguro(steps, orientar_caminho(pts1, lx, ly))
                lx, ly = get_last_point(steps)
                adicionar_caminho_seguro(steps, orientar_caminho(pts2, lx, ly))
                
            elif infill_pattern in ['zigzag', 'gyroid']:
                phase = math.pi if not eh_par else 0
                pts_infill = gerar_infill_rotacionado(angulo_atual, x_infill_bound_min, x_infill_bound_max, y_infill_bound_min, y_infill_bound_max, z_atual, espacamento_alvo, infill_pattern, phase, amplitude_gyroid, comprimento_onda_gyroid)
                
                lx, ly = get_last_point(steps)
                adicionar_caminho_seguro(steps, orientar_caminho(pts_infill, lx, ly))
            
    else:
        # --- INFILL -> PERÍMETRO ---
        if infill_percent > 0:
            steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_infill_atual)}"))
            if infill_pattern == 'concentric':
                lx, ly = get_last_point(steps)
                pts_infill = gerar_espiral_concentrica_retangular(
                    x_min, x_max, y_min, y_max, z_atual, innermost_offset + espacamento_alvo, espacamento_alvo,
                    lx, ly, out_to_in=False, anti_horario=False
                )
                adicionar_caminho_seguro(steps, pts_infill)
                
            elif infill_pattern == 'grid':
                pts1 = gerar_infill_rotacionado(angulo_atual, x_infill_bound_min, x_infill_bound_max, y_infill_bound_min, y_infill_bound_max, z_atual, espacamento_alvo * 2, 'zigzag', 0, 0, 0)
                pts2 = gerar_infill_rotacionado(angulo_atual + 90, x_infill_bound_min, x_infill_bound_max, y_infill_bound_min, y_infill_bound_max, z_atual, espacamento_alvo * 2, 'zigzag', 0, 0, 0)
                
                lx, ly = get_last_point(steps)
                adicionar_caminho_seguro(steps, orientar_caminho(pts1, lx, ly))
                lx, ly = get_last_point(steps)
                adicionar_caminho_seguro(steps, orientar_caminho(pts2, lx, ly))
                
            elif infill_pattern in ['zigzag', 'gyroid']:
                phase = math.pi if not eh_par else 0
                pts_infill = gerar_infill_rotacionado(angulo_atual, x_infill_bound_min, x_infill_bound_max, y_infill_bound_min, y_infill_bound_max, z_atual, espacamento_alvo, infill_pattern, phase, amplitude_gyroid, comprimento_onda_gyroid)
                
                lx, ly = get_last_point(steps)
                adicionar_caminho_seguro(steps, orientar_caminho(pts_infill, lx, ly))
            
        # 2. Perímetro
        steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_perim_atual)}"))
        start_x, start_y = get_last_point(steps)
        pts_perim, _, _ = gerar_perimetros_dinamicos(
            num_perimetros, x_min, x_max, y_min, y_max, z_atual, recuo, largura_extrusao,
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

# ==============================================================================
# 6. PÓS-PROCESSAMENTO: Remove comentários longos para compatibilidade com PrusaSlicer
# ==============================================================================
import glob, os

# Encontra o arquivo gerado mais recente
arquivos = sorted(glob.glob('prisma_solido*.gcode'), key=os.path.getmtime)
if arquivos:
    arquivo_gcode = arquivos[-1]
    with open(arquivo_gcode, 'r', encoding='utf-8', errors='replace') as f:
        linhas = f.readlines()
    
    linhas_limpas = []
    primeiro_g0 = True
    em_espiral = False
    for linha in linhas:
        linha = linha.rstrip('\r\n')
        # Remove comentários inline (mas preserva linhas que SÃO comentários puros necessários)
        if ';' in linha and not linha.lstrip().startswith(';'):
            linha = linha[:linha.index(';')].rstrip()
        # Descarta linhas de comentário puro desnecessárias (exceto marcadores de seção)
        elif linha.lstrip().startswith(';') and linha.strip() not in (';STARTGCODE', ';ENDGCODE', '; --- ESPIRAL START ---', '; --- ESPIRAL END ---'):
            continue
            
        # Monitorar estado do modo espiral
        if '; --- ESPIRAL START ---' in linha:
            em_espiral = True
            continue
        elif '; --- ESPIRAL END ---' in linha:
            em_espiral = False
            continue
            
        if linha:  # ignora linhas em branco resultantes
            linhas_limpas.append(linha + '\n')
            # Inserir priming após movimentos de travel (G0) fora do modo espiral
            if priming_ativo and not em_espiral and linha.strip().startswith('G0') and ('X' in linha or 'Y' in linha):
                if primeiro_g0:
                    linhas_limpas.append(f"G1 E{priming_quantidade:.5f} F{priming_velocidade} ; Priming inicial\n")
                    primeiro_g0 = False
                else:
                    linhas_limpas.append(f"G1 E{priming_quantidade:.5f} F{priming_velocidade} ; Priming apos travel\n")
    
    with open(arquivo_gcode, 'w', encoding='utf-8') as f:
        f.writelines(linhas_limpas)
    
    # Verifica se alguma linha ainda é longa
    max_len = max(len(l.rstrip()) for l in linhas_limpas)
    print(f"G-code gerado com sucesso! -> {arquivo_gcode}")
    print(f"-> Linhas no arquivo: {len(linhas_limpas)} | Maior linha: {max_len} chars")

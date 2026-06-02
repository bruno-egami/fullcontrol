import fullcontrol as fc
import math
import glob, os

# ==============================================================================
# 1. CONFIGURAÇÕES DO USUÁRIO (PARÂMETROS DO AMBIENTE E GEOMETRIA)
# ==============================================================================

# --- Configuração Compartilhada da Impressora (Bico, Priming, Wipe, Vaso) ---
from config_impressora import *

resolucao_mm = 1.0                 # mm (Tamanho de cada segmento nas curvas)

# --- Parâmetros Geométricos do Cilindro Inclinado ---
x_centro, y_centro = 260.0, 45.0   # Centro geométrico da peça na mesa
raio_cilindro = 20.0               # Raio físico externo da peça (mm) na primeira camada
z_max_desejado = 15.0              # Altura final total da peça no eixo Z
angulo_parede = 80.0               # Graus (90 = vertical, <90 = afunila para dentro, >90 = expande para fora)

# --- Zonas de Configuração por Camada ---
zonas_camadas = [
    {
        'camada_inicio': 0,
        'num_perimetros': 0,
        'infill_percent': 100.0,
        'infill_pattern': 'concentric',
        'fluxo_perimetro': 100.0,
        'fluxo_infill': 100.0,
        'espiral': False
    },
    {
        'camada_inicio': 30,
        'num_perimetros': 1,
        'infill_percent': 0.0,
        'infill_pattern': 'concentric',
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
velocidade_impressao = 600         # mm/min (10 mm/s)
velocidade_travel = 3000           # mm/min (50 mm/s)

# --- Controle Extra de Infill ---
sobreposicao_infill = 0.5          # mm (Sobreposição do infill na parede interna)

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

recuo = largura_extrusao / 2
raio_p_outer = raio_cilindro - recuo

num_camadas = math.ceil(z_max_desejado / altura_camada)

def obter_zona(camada):
    zona_ativa = zonas_camadas[0]
    for zona in zonas_camadas:
        if camada >= zona['camada_inicio']:
            zona_ativa = zona
    return zona_ativa

# ==============================================================================
# FUNÇÕES MATEMÁTICAS CIRCULARES
# ==============================================================================

def orientar_caminho(pts, start_x, start_y):
    if not pts: return pts
    dist_start = math.hypot(pts[0].x - start_x, pts[0].y - start_y)
    dist_end = math.hypot(pts[-1].x - start_x, pts[-1].y - start_y)
    if dist_end < dist_start:
        pts.reverse()
    return pts

def get_last_point(steps):
    for step in reversed(steps):
        if hasattr(step, 'x'):
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

def gerar_perimetros_circulares(num_perim, raio_maximo, z, espessura, start_x, start_y, out_to_in=True, anti_horario=True):
    pts = []
    
    theta_start = math.atan2(start_y - y_centro, start_x - x_centro)
    p_range = range(num_perim) if out_to_in else range(num_perim-1, -1, -1)
    
    for p in p_range:
        r = raio_maximo - p * espessura
        if r <= 0: continue
        
        circunferencia = 2 * math.pi * r
        num_pts = max(8, int(math.ceil(circunferencia / resolucao_mm)))
        
        loop = []
        for i in range(num_pts + 1):
            theta = theta_start + (i / num_pts) * 2 * math.pi * (1 if anti_horario else -1)
            cx = x_centro + r * math.cos(theta)
            cy = y_centro + r * math.sin(theta)
            loop.append(fc.Point(x=cx, y=cy, z=z))
            
        pts.extend(loop)
        
    return pts

def gerar_espiral_circular(raio, z_inicio, altura_cam, start_x, start_y, anti_horario=True):
    pts = []
    
    theta_start = math.atan2(start_y - y_centro, start_x - x_centro)
    circunferencia = 2 * math.pi * raio
    num_pts = max(8, int(math.ceil(circunferencia / resolucao_mm)))
    
    for i in range(num_pts + 1):
        theta = theta_start + (i / num_pts) * 2 * math.pi * (1 if anti_horario else -1)
        cx = x_centro + raio * math.cos(theta)
        cy = y_centro + raio * math.sin(theta)
        z_atual = z_inicio + (i / num_pts) * altura_cam
        pts.append(fc.Point(x=cx, y=cy, z=z_atual))
        
    return pts

def gerar_infill_circular_rotacionado(angulo_graus, raio_limite, z, espacamento, pattern, phase, amplitude, comprimento_onda):
    theta = math.radians(angulo_graus)
    pts = []
    
    v_min, v_max = -raio_limite, raio_limite
    v_current = math.ceil(v_min / espacamento) * espacamento
    flip = False
    
    while v_current <= v_max + 1e-5:
        if abs(v_current) > raio_limite:
            v_current += espacamento
            continue
            
        T = math.sqrt(max(0, raio_limite**2 - v_current**2))
        t_min, t_max = -T, T
        if t_max - t_min < 1e-5:
            v_current += espacamento
            continue
            
        if pattern == 'gyroid':
            margin = amplitude + 1.0
            t_start = t_max + margin if flip else t_min - margin
            t_end = t_min - margin if flip else t_max + margin
            
            dist = abs(t_end - t_start)
            num_pts = max(10, int(dist / resolucao_mm))
            
            for j in range(num_pts + 1):
                t_val = t_start + j * ((t_end - t_start) / num_pts)
                
                x_base = x_centro - v_current * math.sin(theta) + t_val * math.cos(theta)
                y_base = y_centro + v_current * math.cos(theta) + t_val * math.sin(theta)
                
                t_along_line = (x_base - x_centro) * math.cos(theta) + (y_base - y_centro) * math.sin(theta)
                wave_offset = amplitude * math.sin(2 * math.pi * t_along_line / comprimento_onda + phase)
                
                x_final = x_base - wave_offset * math.sin(theta)
                y_final = y_base + wave_offset * math.cos(theta)
                
                dx = x_final - x_centro
                dy = y_final - y_centro
                dist_center = math.hypot(dx, dy)
                
                if dist_center > raio_limite:
                    dx = dx / dist_center * raio_limite
                    dy = dy / dist_center * raio_limite
                    x_final = x_centro + dx
                    y_final = y_centro + dy
                
                if not pts or abs(pts[-1].x - x_final) > 1e-4 or abs(pts[-1].y - y_final) > 1e-4:
                    pts.append(fc.Point(x=x_final, y=y_final, z=z))
        else:
            p1 = (x_centro - v_current * math.sin(theta) + t_min * math.cos(theta), y_centro + v_current * math.cos(theta) + t_min * math.sin(theta))
            p2 = (x_centro - v_current * math.sin(theta) + t_max * math.cos(theta), y_centro + v_current * math.cos(theta) + t_max * math.sin(theta))
            p_start, p_end = (p2, p1) if flip else (p1, p2)
            pts.append(fc.Point(x=p_start[0], y=p_start[1], z=z))
            pts.append(fc.Point(x=p_end[0], y=p_end[1], z=z))
            
        v_current += espacamento
        flip = not flip
        
    return pts

def gerar_espiral_concentrica_circular(raio_inicio, espacamento, z, start_x, start_y, out_to_in=True, anti_horario=True):
    pts = []
    
    dist_centro = math.hypot(start_x - x_centro, start_y - y_centro)
    if dist_centro < 0.1:
        theta_start = math.pi
    else:
        theta_start = math.atan2(start_y - y_centro, start_x - x_centro)
    
    limite_min = 0.2
    if raio_inicio <= limite_min:
        return pts
        
    num_aneis = int(math.floor((raio_inicio - limite_min) / espacamento)) + 1
    if num_aneis < 1:
        num_aneis = 1
        
    rampa_rad = 0.5 * math.pi
    duracao_ciclo = 2 * math.pi
    total_radianos = num_aneis * duracao_ciclo
    
    raio_fim = 0.0
    raio_medio = raio_inicio / 2
    comprimento_total = (total_radianos / (2 * math.pi)) * 2 * math.pi * raio_medio
    num_pts = max(16, int(math.ceil(comprimento_total / resolucao_mm)))
    
    for i in range(num_pts + 1):
        t = i / num_pts
        rad_acumulado = t * total_radianos
        
        if rad_acumulado >= total_radianos - 1e-9:
            p = num_aneis - 1
            phi_rel = duracao_ciclo
        else:
            p = int(rad_acumulado // duracao_ciclo)
            phi_rel = rad_acumulado % duracao_ciclo
            
        r_p = raio_inicio - p * espacamento
        
        if phi_rel <= 2 * math.pi - rampa_rad:
            r = r_p
        else:
            t_rampa = (phi_rel - (2 * math.pi - rampa_rad)) / rampa_rad
            f_suave = (1.0 - math.cos(math.pi * t_rampa)) / 2.0
            
            if p == num_aneis - 1:
                r = r_p + f_suave * (0.0 - r_p)
            else:
                r_proximo = raio_inicio - (p + 1) * espacamento
                r = r_p + f_suave * (r_proximo - r_p)
                
        theta_delta = rad_acumulado * (1 if anti_horario else -1)
        theta = theta_start + theta_delta
        
        cx = x_centro + r * math.cos(theta)
        cy = y_centro + r * math.sin(theta)
        pts.append(fc.Point(x=cx, y=cy, z=z))
        
    if not out_to_in:
        pts.reverse()
        
    return pts

# ==============================================================================
# 4. GERAÇÃO DA PEÇA (Caminho Contínuo Total com Controle de Inclinação)
# ==============================================================================

# Primeira viagem
steps.append(fc.Extruder(on=False))
steps.append(fc.Point(x=x_centro - raio_p_outer, y=y_centro, z=altura_camada))
steps.append(fc.Extruder(on=True))

ultimo_era_espiral = False
for camada in range(num_camadas):
    z_atual = altura_camada + (camada * altura_camada)
    eh_par = (camada % 2 == 0)
    
    zona_ativa = obter_zona(camada)
    num_perimetros = zona_ativa.get('num_perimetros', 1)
    infill_percent = zona_ativa.get('infill_percent', 0.0)
    infill_pattern = zona_ativa.get('infill_pattern', 'zigzag')
    fluxo_perim_atual = zona_ativa.get('fluxo_perimetro', 100.0)
    fluxo_infill_atual = zona_ativa.get('fluxo_infill', 100.0)
    espiral = zona_ativa.get('espiral', False)
    
    # --- CÁLCULO DAS DIMENSÕES INCLINADAS ---
    if angulo_parede != 90.0:
        delta_r = (z_atual - altura_camada) / math.tan(math.radians(angulo_parede))
    else:
        delta_r = 0.0
        
    raio_atual = raio_cilindro - delta_r
    raio_p_camada = raio_atual - recuo
    
    # Recalcula limites baseados no perímetro
    if num_perimetros == 0:
        # Sem perímetros, a base sólida é feita apenas de infill.
        # Para que a base fique levemente maior (para acabamento manual e apoiar 100% o vaso em espiral),
        # aumentamos o tamanho do infill em uma distância equivalente a 1 perímetro (largura_extrusao * 0.95).
        raio_innermost = raio_p_camada + 2 * (largura_extrusao * 0.95)
    else:
        raio_innermost = raio_p_camada - (num_perimetros - 1) * (largura_extrusao * 0.95)
        
    # --- VERIFICAÇÃO DE FECHAMENTO DO ÁPICE (Apex Check) ---
    if raio_atual <= 0.2:
        steps.append(fc.ManualGcode(text=f"; --- APICE ALCANCADO: Parando na camada {camada} (Z={z_atual}mm) devido ao afunilamento total ---"))
        print(f"-> Apice alcancado na camada {camada} (Z={z_atual}mm) devido ao afunilamento total!")
        break
        
    raio_infill_bound = raio_innermost - recuo + sobreposicao_infill
    espacamento_alvo = (largura_extrusao * 0.95) / (infill_percent / 100.0) if infill_percent > 0 else 9999.0

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
        pts_espiral = gerar_espiral_circular(raio_p_camada, z_inicio, altura_cam_atual, start_x, start_y, anti_horario=True)
        adicionar_caminho_seguro(steps, pts_espiral)
        continue
    else:
        ultimo_era_espiral = False
        steps.append(fc.ManualGcode(text="; --- ESPIRAL END ---"))

    # --- MODO TRADICIONAL DISCRETO ---
    if camada > 0:
        lx, ly = get_last_point(steps)
        steps.append(fc.Extruder(on=False))
        steps.append(fc.Point(x=lx, y=ly, z=z_atual))
        steps.append(fc.Extruder(on=True))
        
    angulo_atual = angulo_infill_base if eh_par else -angulo_infill_base
    
    if eh_par or not alternar_ordem_camadas:
        steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_perim_atual)}"))
        start_x, start_y = get_last_point(steps)
        pts_perim = gerar_perimetros_circulares(num_perimetros, raio_p_camada, z_atual, largura_extrusao * 0.95, start_x, start_y, out_to_in=True, anti_horario=True)
        adicionar_caminho_seguro(steps, pts_perim, tipo='perimetro')
        
        if infill_percent > 0:
            steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_infill_atual)}"))
            if infill_pattern == 'concentric':
                lx, ly = get_last_point(steps)
                pts_infill = gerar_espiral_concentrica_circular(
                    raio_innermost - espacamento_alvo, espacamento_alvo, z_atual,
                    lx, ly, out_to_in=True, anti_horario=True
                )
                adicionar_caminho_seguro(steps, pts_infill, tipo='infill')
                
            elif infill_pattern == 'grid':
                pts1 = gerar_infill_circular_rotacionado(angulo_atual, raio_infill_bound, z_atual, espacamento_alvo * 2, 'zigzag', 0, 0, 0)
                pts2 = gerar_infill_circular_rotacionado(angulo_atual + 90, raio_infill_bound, z_atual, espacamento_alvo * 2, 'zigzag', 0, 0, 0)
                lx, ly = get_last_point(steps)
                adicionar_caminho_seguro(steps, orientar_caminho(pts1, lx, ly), tipo='infill')
                lx, ly = get_last_point(steps)
                adicionar_caminho_seguro(steps, orientar_caminho(pts2, lx, ly), tipo='infill')
                
            elif infill_pattern in ['zigzag', 'gyroid']:
                phase = math.pi if not eh_par else 0
                pts_infill = gerar_infill_circular_rotacionado(angulo_atual, raio_infill_bound, z_atual, espacamento_alvo, infill_pattern, phase, amplitude_gyroid, comprimento_onda_gyroid)
                lx, ly = get_last_point(steps)
                adicionar_caminho_seguro(steps, orientar_caminho(pts_infill, lx, ly), tipo='infill')
            
    else:
        if infill_percent > 0:
            steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_infill_atual)}"))
            if infill_pattern == 'concentric':
                lx, ly = get_last_point(steps)
                pts_infill = gerar_espiral_concentrica_circular(
                    raio_innermost - espacamento_alvo, espacamento_alvo, z_atual,
                    lx, ly, out_to_in=False, anti_horario=True
                )
                adicionar_caminho_seguro(steps, pts_infill, tipo='infill')
                
            elif infill_pattern == 'grid':
                pts1 = gerar_infill_circular_rotacionado(angulo_atual, raio_infill_bound, z_atual, espacamento_alvo * 2, 'zigzag', 0, 0, 0)
                pts2 = gerar_infill_circular_rotacionado(angulo_atual + 90, raio_infill_bound, z_atual, espacamento_alvo * 2, 'zigzag', 0, 0, 0)
                lx, ly = get_last_point(steps)
                adicionar_caminho_seguro(steps, orientar_caminho(pts1, lx, ly), tipo='infill')
                lx, ly = get_last_point(steps)
                adicionar_caminho_seguro(steps, orientar_caminho(pts2, lx, ly), tipo='infill')
                
            elif infill_pattern in ['zigzag', 'gyroid']:
                phase = math.pi if not eh_par else 0
                pts_infill = gerar_infill_circular_rotacionado(angulo_atual, raio_infill_bound, z_atual, espacamento_alvo, infill_pattern, phase, amplitude_gyroid, comprimento_onda_gyroid)
                lx, ly = get_last_point(steps)
                adicionar_caminho_seguro(steps, orientar_caminho(pts_infill, lx, ly), tipo='infill')
            
        steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_perim_atual)}"))
        start_x, start_y = get_last_point(steps)
        pts_perim = gerar_perimetros_circulares(num_perimetros, raio_p_camada, z_atual, largura_extrusao * 0.95, start_x, start_y, out_to_in=False, anti_horario=False)
        adicionar_caminho_seguro(steps, pts_perim, tipo='perimetro')

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
# 5. GERAÇÃO DO G-CODE
# ==============================================================================
gcode = fc.transform(steps, 'gcode', fc.GcodeControls(
    printer_name='Community/Cliever CL2Pro', 
    save_as='cilindro_inclinado_solido',
    initialization_data={
        'primer': 'no_primer', 
        'dia_feed': 1.75,
        'extrusion_width': largura_extrusao,
        'extrusion_height': altura_camada
    }
))

# ==============================================================================
# 6. PÓS-PROCESSAMENTO
# ==============================================================================
arquivos = sorted(glob.glob('cilindro_inclinado_solido*.gcode'), key=os.path.getmtime)
if arquivos:
    arquivo_gcode = arquivos[-1]
    with open(arquivo_gcode, 'r', encoding='utf-8', errors='replace') as f:
        linhas = f.readlines()
    
    linhas_limpas = []
    primeiro_g0 = True
    em_espiral = False
    em_perimetro = False
    em_infill = False
    
    for linha in linhas:
        linha = linha.rstrip('\r\n')
        
        # Filtra comentários inline, mas preserva diretivas estruturais fundamentais
        if ';' in linha and not linha.lstrip().startswith(';'):
            comment_idx = linha.index(';')
            linha = linha[:comment_idx].rstrip()
        elif linha.lstrip().startswith(';') and linha.strip() not in (
            ';STARTGCODE', ';ENDGCODE', 
            '; --- ESPIRAL START ---', '; --- ESPIRAL END ---',
            '; --- PERIMETRO START ---', '; --- PERIMETRO END ---',
            '; --- INFILL START ---', '; --- INFILL END ---'
        ):
            continue
            
        # Monitoramento e processamento de estado
        if '; --- ESPIRAL START ---' in linha:
            em_espiral = True
            linhas_limpas.append(linha + '\n')
            continue
        elif '; --- ESPIRAL END ---' in linha:
            em_espiral = False
            linhas_limpas.append(linha + '\n')
            continue
            
        elif '; --- PERIMETRO START ---' in linha:
            em_perimetro = True
            linhas_limpas.append(linha + '\n')
            continue
        elif '; --- PERIMETRO END ---' in linha:
            em_perimetro = False
            if priming_ativo and priming_fim_perimetro and not em_espiral:
                linhas_limpas.append(f"G1 E{priming_perimetro_fim_qtd:.5f} F{priming_perimetro_fim_vel} ; Retracao/Alivio fim perimetro\n")
            linhas_limpas.append(linha + '\n')
            continue
            
        elif '; --- INFILL START ---' in linha:
            em_infill = True
            linhas_limpas.append(linha + '\n')
            continue
        elif '; --- INFILL END ---' in linha:
            em_infill = False
            if priming_ativo and priming_fim_infill and not em_espiral:
                linhas_limpas.append(f"G1 E{priming_infill_fim_qtd:.5f} F{priming_infill_fim_vel} ; Retracao/Alivio fim infill\n")
            linhas_limpas.append(linha + '\n')
            continue
            
        if linha:
            is_travel = linha.strip().startswith('G0') and ('X' in linha or 'Y' in linha)
            linhas_limpas.append(linha + '\n')
            
            if is_travel and priming_ativo and not em_espiral:
                if primeiro_g0:
                    linhas_limpas.append(f"G1 E{priming_inicial_qtd:.5f} F{priming_inicial_vel} ; Purga inicial para carregar o bico\n")
                    primeiro_g0 = False
                elif em_perimetro and priming_inicio_perimetro:
                    linhas_limpas.append(f"G1 E{priming_perimetro_inicio_qtd:.5f} F{priming_perimetro_inicio_vel} ; Purga inicio perimetro\n")
                elif em_infill and priming_inicio_infill:
                    linhas_limpas.append(f"G1 E{priming_infill_inicio_qtd:.5f} F{priming_infill_inicio_vel} ; Purga inicio infill\n")
    
    with open(arquivo_gcode, 'w', encoding='utf-8') as f:
        f.writelines(linhas_limpas)
    
    max_len = max(len(l.rstrip()) for l in linhas_limpas)
    print(f"G-code do cilindro gerado com sucesso! -> {arquivo_gcode}")
    print(f"-> Linhas no arquivo: {len(linhas_limpas)} | Maior linha: {max_len} chars")

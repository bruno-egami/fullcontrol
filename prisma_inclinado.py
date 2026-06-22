import fullcontrol as fc
import math

def gerar_passos_prisma(config):
    # --- Extração de Parâmetros da Configuração ---
    x_centro = config.get('x_centro', 240.0)
    y_centro = config.get('y_centro', 50.0)
    largura_x = config.get('largura_x', 21.0)
    comprimento_y = config.get('comprimento_y', 60.0)
    z_max_desejado = config.get('z_max_desejado', 10.0)
    angulo_parede = config.get('angulo_parede', 90.0) # 90 é parede reta
    
    zonas_camadas = config.get('zonas_camadas', [
        {
            'camada_inicio': 0,
            'num_perimetros': 1,
            'infill_percent': 100.0,
            'infill_pattern': 'concentric',
            'fluxo_perimetro': 120.0,
            'fluxo_infill': 120.0,
            'espiral': False
        }
    ])
    
    alternar_ordem_camadas = config.get('alternar_ordem_camadas', True)
    angulo_infill_base = config.get('angulo_infill_base', 45.0)
    amplitude_gyroid = config.get('amplitude_gyroid', 2.0)
    comprimento_onda_gyroid = config.get('comprimento_onda_gyroid', 15.0)
    sobreposicao_infill = config.get('sobreposicao_infill', 0.0)
    
    largura_extrusao = config.get('largura_extrusao', 3.0)
    altura_camada = config.get('altura_camada', 1.0)
    
    transicao_vaso_z_offset = config.get('transicao_vaso_z_offset', 0.5)
    transicao_vaso_fluxo = config.get('transicao_vaso_fluxo', 85.0)
    
    wipe_final_ativo = config.get('wipe_final_ativo', True)
    wipe_final_distancia = config.get('wipe_final_distancia', 6.0)
    wipe_final_subida_z = config.get('wipe_final_subida_z', 0.5)

    steps = []

    # ==============================================================================
    # PROCESSAMENTO MATEMÁTICO DOS PARÂMETROS
    # ==============================================================================
    recuo = largura_extrusao / 2
    x_min, x_max = x_centro - (largura_x / 2), x_centro + (largura_x / 2)
    y_min, y_max = y_centro - (comprimento_y / 2), y_centro + (comprimento_y / 2)

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

    def intersect_line_rect_param(v, theta_rad, Xc, Yc, Xmin, Xmax, Ymin, Ymax):
        cos_t = math.cos(theta_rad)
        sin_t = math.sin(theta_rad)
        t_vals = []
        
        if abs(cos_t) > 1e-6:
            t1 = (Xmin - Xc + v * sin_t) / cos_t
            y1 = Yc + v * cos_t + t1 * sin_t
            if Ymin - 1e-5 <= y1 <= Ymax + 1e-5: t_vals.append(t1)
                
            t2 = (Xmax - Xc + v * sin_t) / cos_t
            y2 = Yc + v * cos_t + t2 * sin_t
            if Ymin - 1e-5 <= y2 <= Ymax + 1e-5: t_vals.append(t2)
                
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
        
        corners = [(x_min_b, y_min_b), (x_max_b, y_min_b), (x_max_b, y_max_b), (x_min_b, y_max_b)]
        v_vals = [-(x - Xc)*math.sin(theta) + (y - Yc)*math.cos(theta) for x, y in corners]
        v_min, v_max = min(v_vals), max(v_vals)
        
        pts = []
        v_current = math.ceil(v_min / espacamento) * espacamento
        flip = False
        
        while v_current <= v_max + 1e-5:
            segment = intersect_line_rect_param(v_current, theta, Xc, Yc, x_min_b, x_max_b, y_min_b, y_max_b)
            if segment:
                p1, p2, t_min, t_max = segment
                    
                if pattern == 'gyroid':
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
                        
                        x_clamped = max(x_min_b, min(x_max_b, x_final))
                        y_clamped = max(y_min_b, min(y_max_b, y_final))
                        
                        if not pts or abs(pts[-1].x - x_clamped) > 1e-4 or abs(pts[-1].y - y_clamped) > 1e-4:
                            pts.append(fc.Point(x=x_clamped, y=y_clamped, z=z))
                else:
                    p_start, p_end = (p2, p1) if flip else (p1, p2)
                    pts.append(fc.Point(x=p_start[0], y=p_start[1], z=z))
                    pts.append(fc.Point(x=p_end[0], y=p_end[1], z=z))
                    
            v_current += espacamento
            flip = not flip
            
        return pts

    def gerar_perimetros_dinamicos(num_perim, x_min_b, x_max_b, y_min_b, y_max_b, z, recuo_interno, espessura, start_x, start_y, out_to_in=True, anti_horario=True):
        pts = []
        x_p_min_out, x_p_max_out = x_min_b + recuo_interno, x_max_b - recuo_interno
        y_p_min_out, y_p_max_out = y_min_b + recuo_interno, y_max_b - recuo_interno
        
        corners_out = [
            fc.Point(x=x_p_min_out, y=y_p_max_out, z=z), # 0: TL
            fc.Point(x=x_p_min_out, y=y_p_min_out, z=z), # 1: BL
            fc.Point(x=x_p_max_out, y=y_p_min_out, z=z), # 2: BR
            fc.Point(x=x_p_max_out, y=y_p_max_out, z=z)  # 3: TR
        ]
        
        idx_start = 0
        min_d = 999999
        for i, c in enumerate(corners_out):
            d = math.hypot(c.x - start_x, c.y - start_y)
            if d < min_d:
                min_d = d
                idx_start = i
                
        p_range = range(num_perim) if out_to_in else range(num_perim-1, -1, -1)
        
        for idx_p, p in enumerate(p_range):
            p_offset = recuo_interno + p * espessura
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

    def gerar_espiral_retangular(x_min_b, x_max_b, y_min_b, y_max_b, z_inicio, altura_cam, recuo_interno, start_x, start_y, anti_horario=True):
        pts = []
        x_p_min_out, x_p_max_out = x_min_b + recuo_interno, x_max_b - recuo_interno
        y_p_min_out, y_p_max_out = y_min_b + recuo_interno, y_max_b - recuo_interno
        
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
                
        loop_corners = []
        if anti_horario:
            for i in range(5): loop_corners.append(corners_out[(idx_start + i) % 4])
        else:
            for i in range(5): loop_corners.append(corners_out[(idx_start - i) % 4])
            
        cx, cy = loop_corners[0]
        pts.append(fc.Point(x=cx, y=cy, z=z_inicio))
        
        for i in range(1, 5):
            cx, cy = loop_corners[i]
            z_atual = z_inicio + (i / 4.0) * altura_cam
            pts.append(fc.Point(x=cx, y=cy, z=z_atual))
            
        return pts

    def gerar_espiral_concentrica_retangular(x_min_b, x_max_b, y_min_b, y_max_b, z, offset_inicial, espacamento, start_x, start_y, out_to_in=True, anti_horario=True):
        pts = []
        
        max_offset_x = (x_max_b - x_min_b) / 2
        max_offset_y = (y_max_b - y_min_b) / 2
        max_offset = min(max_offset_x, max_offset_y)
        
        x_centro_local = (x_min_b + x_max_b) / 2
        y_centro_local = (y_min_b + y_max_b) / 2
        
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
                
                if abs(p_start[1] - C_p[idxs[0]][1]) < 1e-4:
                    p_trans = (p_end[0], p_start[1])
                else:
                    p_trans = (p_start[0], p_end[1])
                    
                pts_base.append(fc.Point(x=p_trans[0], y=p_trans[1], z=z))
                
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
                    pts_base.append(fc.Point(x=x_centro_local, y=y_val, z=z))
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
                    pts_base.append(fc.Point(x=x_val, y=y_centro_local, z=z))
                    
            return pts_base

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
    # 4. GERAÇÃO DA PEÇA (Caminho Contínuo Total com Controle de Inclinação)
    # ==============================================================================

    steps.append(fc.Extruder(on=False))
    steps.append(fc.Point(x=x_p_min_outer, y=y_p_max_outer, z=altura_camada))
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
        
        if angulo_parede != 90.0:
            delta_r = (z_atual - altura_camada) / math.tan(math.radians(angulo_parede))
        else:
            delta_r = 0.0
            
        largura_x_atual = largura_x - 2 * delta_r
        comprimento_y_atual = comprimento_y - 2 * delta_r
        
        x_min_camada = x_centro - (largura_x_atual / 2)
        x_max_camada = x_centro + (largura_x_atual / 2)
        y_min_camada = y_centro - (comprimento_y_atual / 2)
        y_max_camada = y_centro + (comprimento_y_atual / 2)
        
        espacamento_alvo = (largura_extrusao * 0.95) / (infill_percent / 100.0) if infill_percent > 0 else 9999.0

        if num_perimetros == 0:
            innermost_offset = recuo - espacamento_alvo
        else:
            innermost_offset = recuo + (num_perimetros - 1) * (largura_extrusao * 0.95)
            
        if largura_x_atual <= 2 * innermost_offset or comprimento_y_atual <= 2 * innermost_offset:
            steps.append(fc.ManualGcode(text=f"; --- APICE ALCANCADO: Parando na camada {camada} (Z={z_atual}mm) devido ao afunilamento total ---"))
            break
            
        x_innermost_min = x_min_camada + innermost_offset
        x_innermost_max = x_max_camada - innermost_offset
        y_innermost_min = y_min_camada + innermost_offset
        y_innermost_max = y_max_camada - innermost_offset

        x_infill_bound_min = x_innermost_min + recuo - sobreposicao_infill
        x_infill_bound_max = x_innermost_max - recuo + sobreposicao_infill
        y_infill_bound_min = y_innermost_min + recuo - sobreposicao_infill
        y_infill_bound_max = y_innermost_max - recuo + sobreposicao_infill

        if espiral:
            steps.append(fc.ManualGcode(text="; --- ESPIRAL START ---"))
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
            pts_espiral = gerar_espiral_retangular(x_min_camada, x_max_camada, y_min_camada, y_max_camada, z_inicio, altura_cam_atual, recuo, start_x, start_y, anti_horario=True)
            adicionar_caminho_seguro(steps, pts_espiral)
            continue
        else:
            ultimo_era_espiral = False
            steps.append(fc.ManualGcode(text="; --- ESPIRAL END ---"))

        if camada > 0:
            lx, ly = get_last_point(steps)
            steps.append(fc.Extruder(on=False))
            steps.append(fc.Point(x=lx, y=ly, z=z_atual))
            steps.append(fc.Extruder(on=True))
            
        angulo_atual = angulo_infill_base if eh_par else -angulo_infill_base
        
        if eh_par or not alternar_ordem_camadas:
            steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_perim_atual)}"))
            start_x, start_y = get_last_point(steps)
            pts_perim, is_left, is_top = gerar_perimetros_dinamicos(
                num_perimetros, x_min_camada, x_max_camada, y_min_camada, y_max_camada, z_atual, recuo, largura_extrusao,
                start_x, start_y, out_to_in=True, anti_horario=True
            )
            adicionar_caminho_seguro(steps, pts_perim, tipo='perimetro')
            
            if infill_percent > 0:
                steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_infill_atual)}"))
                if infill_pattern == 'concentric':
                    lx, ly = get_last_point(steps)
                    pts_infill = gerar_espiral_concentrica_retangular(
                        x_min_camada, x_max_camada, y_min_camada, y_max_camada, z_atual, innermost_offset + espacamento_alvo, espacamento_alvo,
                        lx, ly, out_to_in=True, anti_horario=True
                    )
                    adicionar_caminho_seguro(steps, pts_infill, tipo='infill')
                    
                elif infill_pattern == 'grid':
                    pts1 = gerar_infill_rotacionado(angulo_atual, x_infill_bound_min, x_infill_bound_max, y_infill_bound_min, y_infill_bound_max, z_atual, espacamento_alvo * 2, 'zigzag', 0, 0, 0)
                    pts2 = gerar_infill_rotacionado(angulo_atual + 90, x_infill_bound_min, x_infill_bound_max, y_infill_bound_min, y_infill_bound_max, z_atual, espacamento_alvo * 2, 'zigzag', 0, 0, 0)
                    lx, ly = get_last_point(steps)
                    adicionar_caminho_seguro(steps, orientar_caminho(pts1, lx, ly), tipo='infill')
                    lx, ly = get_last_point(steps)
                    adicionar_caminho_seguro(steps, orientar_caminho(pts2, lx, ly), tipo='infill')
                    
                elif infill_pattern in ['zigzag', 'gyroid']:
                    phase = math.pi if not eh_par else 0
                    pts_infill = gerar_infill_rotacionado(angulo_atual, x_infill_bound_min, x_infill_bound_max, y_infill_bound_min, y_infill_bound_max, z_atual, espacamento_alvo, infill_pattern, phase, amplitude_gyroid, comprimento_onda_gyroid)
                    lx, ly = get_last_point(steps)
                    adicionar_caminho_seguro(steps, orientar_caminho(pts_infill, lx, ly), tipo='infill')
                
        else:
            if infill_percent > 0:
                steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_infill_atual)}"))
                if infill_pattern == 'concentric':
                    lx, ly = get_last_point(steps)
                    pts_infill = gerar_espiral_concentrica_retangular(
                        x_min_camada, x_max_camada, y_min_camada, y_max_camada, z_atual, innermost_offset + espacamento_alvo, espacamento_alvo,
                        lx, ly, out_to_in=False, anti_horario=False
                    )
                    adicionar_caminho_seguro(steps, pts_infill, tipo='infill')
                    
                elif infill_pattern == 'grid':
                    pts1 = gerar_infill_rotacionado(angulo_atual, x_infill_bound_min, x_infill_bound_max, y_infill_bound_min, y_infill_bound_max, z_atual, espacamento_alvo * 2, 'zigzag', 0, 0, 0)
                    pts2 = gerar_infill_rotacionado(angulo_atual + 90, x_infill_bound_min, x_infill_bound_max, y_infill_bound_min, y_infill_bound_max, z_atual, espacamento_alvo * 2, 'zigzag', 0, 0, 0)
                    lx, ly = get_last_point(steps)
                    adicionar_caminho_seguro(steps, orientar_caminho(pts1, lx, ly), tipo='infill')
                    lx, ly = get_last_point(steps)
                    adicionar_caminho_seguro(steps, orientar_caminho(pts2, lx, ly), tipo='infill')
                    
                elif infill_pattern in ['zigzag', 'gyroid']:
                    phase = math.pi if not eh_par else 0
                    pts_infill = gerar_infill_rotacionado(angulo_atual, x_infill_bound_min, x_infill_bound_max, y_infill_bound_min, y_infill_bound_max, z_atual, espacamento_alvo, infill_pattern, phase, amplitude_gyroid, comprimento_onda_gyroid)
                    lx, ly = get_last_point(steps)
                    adicionar_caminho_seguro(steps, orientar_caminho(pts_infill, lx, ly), tipo='infill')
                
            steps.append(fc.ManualGcode(text=f"M221 S{int(fluxo_perim_atual)}"))
            start_x, start_y = get_last_point(steps)
            pts_perim, _, _ = gerar_perimetros_dinamicos(
                num_perimetros, x_min_camada, x_max_camada, y_min_camada, y_max_camada, z_atual, recuo, largura_extrusao,
                start_x, start_y, out_to_in=False, anti_horario=False
            )
            adicionar_caminho_seguro(steps, pts_perim, tipo='perimetro')

    if wipe_final_ativo:
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

    return steps

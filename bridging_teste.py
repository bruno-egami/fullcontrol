import fullcontrol as fc
import math

def gerar_passos_bridging(config):
    passos = []
    
    # Parâmetros Gerais
    cx = config.get('x_centro', 150.0)
    cy = config.get('y_centro', 150.0)
    L = config.get('comprimento_braco', 80.0)
    angulo_abertura = config.get('angulo_abertura', 45.0)
    num_camadas_base = int(config.get('num_camadas_base', 4))
    num_perimetros = int(config.get('num_perimetros', 4))
    espacamento_bridging = config.get('espacamento_bridging', 4.0)
    velocidade_base = config.get('velocidade_base', 20.0) * 60.0
    velocidade_ponte = config.get('velocidade_ponte', 10.0) * 60.0
    ancora_pausa_ms = int(config.get('ancora_pausa_ms', 500))
    
    # Parâmetros Globais de Máquina
    largura_extrusao = config.get('largura_extrusao', 3.0)
    altura_camada = config.get('altura_camada', 1.0)
    
    # O ângulo de cada haste em relação à bissetriz (X axis original)
    angulo_rad = math.radians(angulo_abertura / 2.0)
    
    # Função auxiliar para rotacionar as coordenadas -90 graus 
    # (Faz o vértice apontar para +Y e as pernas para -Y)
    def r(x, y):
        return cx + (y - cy), cy - (x - cx)
    
    # ==========================
    # 1. GERAR A BASE EM "V"
    # ==========================
    passos.append(fc.ManualGcode(text="; --- PERIMETRO START ---"))
    passos.append(fc.ManualGcode(text=f"G1 F{velocidade_base}"))
    
    # Gerar a malha base 2D contínua uma única vez
    caminho_base_2d = []
    
    for i in range(num_perimetros):
        # Coordenadas do vértice deslocado para criar as paredes externas
        x_vert = cx - i * largura_extrusao / math.sin(angulo_rad)
        y_vert = cy
        
        x_end = cx + L
        y_top = cy + L * math.tan(angulo_rad) + i * largura_extrusao / math.cos(angulo_rad)
        y_bot = cy - L * math.tan(angulo_rad) - i * largura_extrusao / math.cos(angulo_rad)
        
        rx_top, ry_top = r(x_end, y_top)
        rx_vert, ry_vert = r(x_vert, y_vert)
        rx_bot, ry_bot = r(x_end, y_bot)
        
        if i % 2 == 0:
            # Desenha de Cima -> Vértice -> Baixo
            caminho_base_2d.append((rx_top, ry_top))
            caminho_base_2d.append((rx_vert, ry_vert))
            caminho_base_2d.append((rx_bot, ry_bot))
        else:
            # Desenha de Baixo -> Vértice -> Cima
            caminho_base_2d.append((rx_bot, ry_bot))
            caminho_base_2d.append((rx_vert, ry_vert))
            caminho_base_2d.append((rx_top, ry_top))
            
    # Posiciona no início do primeiro perímetro (Top_0) antes da primeira camada
    passos.append(fc.Extruder(on=False))
    passos.append(fc.Point(x=caminho_base_2d[0][0], y=caminho_base_2d[0][1], z=altura_camada))
    passos.append(fc.Extruder(on=True))
            
    for camada in range(num_camadas_base):
        z = (camada + 1) * altura_camada
        passos.append(fc.ManualGcode(text=f"; CAMADA {camada}"))
        
        # Inverte o caminho a cada camada para não precisar de traveling
        caminho_camada = caminho_base_2d if camada % 2 == 0 else list(reversed(caminho_base_2d))
        
        for p in caminho_camada:
            passos.append(fc.Point(x=p[0], y=p[1], z=z))
            
    passos.append(fc.Extruder(on=False))
                
    passos.append(fc.ManualGcode(text="; --- PERIMETRO END ---"))

    # ==========================
    # 2. GERAR AS PONTES (BRIDGINGS)
    # ==========================
    passos.append(fc.ManualGcode(text="; --- BRIDGING START ---"))
    
    z_bridge = (num_camadas_base + 1) * altura_camada
    W = largura_extrusao  # Distância interna inicial
    
    # Índice externo para cruzar e ancorar sobre TODAS as pernas da base
    i_outer = num_perimetros - 1
    
    # Posicionar no vértice externo da base
    x_vert_outer = cx - i_outer * largura_extrusao / math.sin(angulo_rad)
    y_vert_outer = cy
    rx_v, ry_v = r(x_vert_outer, y_vert_outer)
    
    passos.append(fc.Extruder(on=False))
    passos.append(fc.Point(x=rx_v, y=ry_v, z=z_bridge))
    passos.append(fc.Extruder(on=True))
    
    # Calcular o primeiro ponto da ponte (Top)
    x_bridge = cx + W / (2 * math.tan(angulo_rad))
    y_top_outer = cy + (x_bridge - cx) * math.tan(angulo_rad) + i_outer * largura_extrusao / math.cos(angulo_rad)
    
    rx, ry = r(x_bridge, y_top_outer)
    
    # Caminha do vértice até o ponto inicial da ponte para estabilizar a pressão (Pré-extrusão)
    passos.append(fc.ManualGcode(text=f"G1 F{velocidade_base} ; Vel Base (Pre-extrusao no vertice)"))
    passos.append(fc.Point(x=rx, y=ry, z=z_bridge))
    
    indo_cima_baixo = True
    
    while W <= 2 * L * math.tan(angulo_rad):
        x_bridge = cx + W / (2 * math.tan(angulo_rad))
        
        y_top_outer = cy + (x_bridge - cx) * math.tan(angulo_rad) + i_outer * largura_extrusao / math.cos(angulo_rad)
        y_bot_outer = cy - (x_bridge - cx) * math.tan(angulo_rad) - i_outer * largura_extrusao / math.cos(angulo_rad)
        
        rx_top, ry_top = r(x_bridge, y_top_outer)
        rx_bot, ry_bot = r(x_bridge, y_bot_outer)
        
        p_top = fc.Point(x=rx_top, y=ry_top, z=z_bridge)
        p_bot = fc.Point(x=rx_bot, y=ry_bot, z=z_bridge)
        
        if indo_cima_baixo:
            # Cruza a ponte (Top -> Bot)
            if ancora_pausa_ms > 0:
                passos.append(fc.ManualGcode(text=f"G4 P{ancora_pausa_ms} ; Pausa de ancoragem (Inicio)"))
            passos.append(fc.ManualGcode(text=f"G1 F{velocidade_ponte} ; Vel Bridging"))
            passos.append(p_bot)
            if ancora_pausa_ms > 0:
                passos.append(fc.ManualGcode(text=f"G4 P{ancora_pausa_ms} ; Pausa de ancoragem (Fim)"))
            
            # Prepara próximo W e anda pela perna para ancorar
            W_next = W + espacamento_bridging
            if W_next <= 2 * L * math.tan(angulo_rad):
                x_next = cx + W_next / (2 * math.tan(angulo_rad))
                y_bot_next = cy - (x_next - cx) * math.tan(angulo_rad) - i_outer * largura_extrusao / math.cos(angulo_rad)
                rx_next, ry_next = r(x_next, y_bot_next)
                passos.append(fc.ManualGcode(text=f"G1 F{velocidade_base} ; Vel Base (Ancora)"))
                passos.append(fc.Point(x=rx_next, y=ry_next, z=z_bridge))
        else:
            # Cruza a ponte (Bot -> Top)
            if ancora_pausa_ms > 0:
                passos.append(fc.ManualGcode(text=f"G4 P{ancora_pausa_ms} ; Pausa de ancoragem (Inicio)"))
            passos.append(fc.ManualGcode(text=f"G1 F{velocidade_ponte} ; Vel Bridging"))
            passos.append(p_top)
            if ancora_pausa_ms > 0:
                passos.append(fc.ManualGcode(text=f"G4 P{ancora_pausa_ms} ; Pausa de ancoragem (Fim)"))
            
            W_next = W + espacamento_bridging
            if W_next <= 2 * L * math.tan(angulo_rad):
                x_next = cx + W_next / (2 * math.tan(angulo_rad))
                y_top_next = cy + (x_next - cx) * math.tan(angulo_rad) + i_outer * largura_extrusao / math.cos(angulo_rad)
                rx_next, ry_next = r(x_next, y_top_next)
                passos.append(fc.ManualGcode(text=f"G1 F{velocidade_base} ; Vel Base (Ancora)"))
                passos.append(fc.Point(x=rx_next, y=ry_next, z=z_bridge))
                
        indo_cima_baixo = not indo_cima_baixo
        W += espacamento_bridging
        
    passos.append(fc.Extruder(on=False))
    passos.append(fc.ManualGcode(text="; --- BRIDGING END ---"))

    # Wipe Final
    wipe_ativo = str(config.get('wipe_final_ativo', 'True')).lower() in ('true', '1', 't', 'y', 'yes')
    if wipe_ativo:
        d_wipe = float(config.get('wipe_final_distancia', 6.0))
        z_wipe = float(config.get('wipe_final_subida_z', 0.5))
        
        p_atual = None
        for step in reversed(passos):
            if isinstance(step, fc.Point):
                p_atual = step
                break
                
        if p_atual:
            passos.append(fc.ManualGcode(text="; --- WIPE FINAL ---"))
            passos.append(fc.Point(x=p_atual.x + d_wipe, y=p_atual.y + d_wipe, z=p_atual.z + z_wipe))

    return passos

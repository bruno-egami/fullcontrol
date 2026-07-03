import math
import fullcontrol as fc
from shapely.geometry import Polygon, Point
import glob, os

from cilindro_inclinado import gerar_passos_cilindro
from prisma_inclinado import gerar_passos_prisma
import bridging_teste
import vetor_inclinado
from config_impressora import *
import config_impressora

DIAMETRO_BICO_COLISAO = 40.0
RAIO_COLISAO = DIAMETRO_BICO_COLISAO / 2.0
ALTURA_Z_HOP = 30.0

def verificar_colisao_2d(peca_atual_idx, configs_pecas):
    """
    Verifica se o Bounding Box / Perímetro Expandido da peça atual colide
    com alguma peça já impressa (índices menores).
    """
    peca_atual = configs_pecas[peca_atual_idx]
    x_atual = float(peca_atual.get('x_centro', 0))
    y_atual = float(peca_atual.get('y_centro', 0))
    
    if peca_atual.get('tipo') == 'cilindro':
        raio_atual = float(peca_atual.get('raio_cilindro', 20))
        poly_atual = Point(x_atual, y_atual).buffer(raio_atual)
    else:
        lx = float(peca_atual.get('largura_x', 30))
        ly = float(peca_atual.get('comprimento_y', 30))
        poly_atual = Polygon([
            (x_atual - lx/2, y_atual - ly/2),
            (x_atual + lx/2, y_atual - ly/2),
            (x_atual + lx/2, y_atual + ly/2),
            (x_atual - lx/2, y_atual + ly/2)
        ])
    
    # Adiciona a zona de perigo do bico ao redor da peça atual
    zona_perigo_atual = poly_atual.buffer(RAIO_COLISAO)
    
    for i in range(peca_atual_idx):
        peca_anterior = configs_pecas[i]
        x_ant = float(peca_anterior.get('x_centro', 0))
        y_ant = float(peca_anterior.get('y_centro', 0))
        
        if peca_anterior.get('tipo') == 'cilindro':
            raio_ant = float(peca_anterior.get('raio_cilindro', 20))
            poly_ant = Point(x_ant, y_ant).buffer(raio_ant)
        else:
            lx_ant = float(peca_anterior.get('largura_x', 30))
            ly_ant = float(peca_anterior.get('comprimento_y', 30))
            poly_ant = Polygon([
                (x_ant - lx_ant/2, y_ant - ly_ant/2),
                (x_ant + lx_ant/2, y_ant - ly_ant/2),
                (x_ant + lx_ant/2, y_ant + ly_ant/2),
                (x_ant - lx_ant/2, y_ant + ly_ant/2)
            ])
            
        if zona_perigo_atual.intersects(poly_ant):
            return True, peca_anterior.get('nome', f"Peça {i+1}")
            
    return False, None

def get_last_point(steps):
    for step in reversed(steps):
        if hasattr(step, 'x') and step.x is not None:
            return step.x, step.y, getattr(step, 'z', 0)
    return 0, 0, 0

def gerar_gcode_sequencial(pecas_fila, nome_arquivo="sequencial_final"):
    # 1. Análise de Colisão
    configs_pecas = []
    for peca in pecas_fila:
        cfg = peca.config.copy()
        cfg['tipo'] = peca.tipo
        cfg['nome'] = peca.nome
        
        # Injeta variáveis globais (que não estão na peca) para uso interno dos geradores
        for key in dir(config_impressora):
            if not key.startswith('_') and not hasattr(getattr(config_impressora, key), '__call__'):
                if key not in cfg:
                    cfg[key] = getattr(config_impressora, key)
        
        # Processa a lista de Zonas que veio da GUI e converte 'qtd_camadas' para 'camada_inicio' acumulativo
        zonas_convertidas = []
        camada_atual = 0
        zonas_gui = cfg.get('zonas_camadas', [])
        
        if not zonas_gui:
            # Fallback seguro caso a peça não tenha zonas
            zonas_gui = [{'qtd_camadas': 999, 'num_perimetros': 1, 'infill_percent': 100.0, 'infill_pattern': 'concentric', 'fluxo_perimetro': 100.0, 'fluxo_infill': 100.0, 'espiral': 'False'}]
            
        for zona in zonas_gui:
            z_conv = {
                'camada_inicio': camada_atual,
                'num_perimetros': int(zona.get('num_perimetros', 1)),
                'infill_percent': float(zona.get('infill_percent', 100.0)),
                'infill_pattern': str(zona.get('infill_pattern', 'concentric')),
                'fluxo_perimetro': float(zona.get('fluxo_perimetro', 100.0)),
                'fluxo_infill': float(zona.get('fluxo_infill', 100.0)),
                'espiral': str(zona.get('espiral', 'False')).lower() in ('true', '1', 't', 'y', 'yes')
            }
            zonas_convertidas.append(z_conv)
            camada_atual += int(zona.get('qtd_camadas', 999))
            
        cfg['zonas_camadas'] = zonas_convertidas
        
        # Transforma booleanos que vieram como string do GUI
        cfg['alternar_ordem_camadas'] = str(cfg.get('alternar_ordem_camadas', 'True')).lower() in ('true', '1', 't', 'y', 'yes')
        cfg['wipe_final_ativo'] = str(cfg.get('wipe_final_ativo', 'True')).lower() in ('true', '1', 't', 'y', 'yes')
        
        configs_pecas.append(cfg)
        
    for i in range(len(configs_pecas)):
        houve_colisao, nome_colidida = verificar_colisao_2d(i, configs_pecas)
        if houve_colisao:
            return False, f"RISCO DE COLISÃO!\nA peça '{configs_pecas[i]['nome']}' se sobrepõe à área da peça já impressa '{nome_colidida}' devido à folga de segurança de {DIAMETRO_BICO_COLISAO}mm do bico de extrusão. Aumente a distância entre as peças."

    # 2. Geração Mestra
    master_steps = []
    largura_extrusao = float(configs_pecas[0].get('largura_extrusao', 3.0))
    altura_camada = float(configs_pecas[0].get('altura_camada', 1.0))
    
    velocidade_primeira_camada_inicial = float(configs_pecas[0].get('velocidade_primeira_camada', config_impressora.velocidade_primeira_camada)) * 60.0
    velocidade_travel_inicial = float(configs_pecas[0].get('velocidade_travel', config_impressora.velocidade_travel)) * 60.0
    
    master_steps.append(fc.Printer(print_speed=velocidade_primeira_camada_inicial, travel_speed=velocidade_travel_inicial))
    master_steps.append(fc.ExtrusionGeometry(area_model='rectangle', width=largura_extrusao, height=altura_camada))
    
    aceleracao_z = int(configs_pecas[0].get('aceleracao_z', config_impressora.aceleracao_z))
    if aceleracao_z > 0:
        master_steps.append(fc.ManualGcode(text=f"M201 Z{aceleracao_z}"))

    for idx, cfg in enumerate(configs_pecas):
        master_steps.append(fc.ManualGcode(text=f"; ================================="))
        master_steps.append(fc.ManualGcode(text=f"; --- INICIANDO PECA: {cfg['nome']} ---"))
        master_steps.append(fc.ManualGcode(text=f"; ================================="))
        
        # Z-Hop Dinâmico antes de mover para a nova peça
        if idx > 0:
            lx, ly, lz = get_last_point(master_steps)
            z_hop_target = lz + ALTURA_Z_HOP
            master_steps.append(fc.Extruder(on=False))
            master_steps.append(fc.Point(x=lx, y=ly, z=z_hop_target)) # Sobe reto
            
            x_novo = float(cfg.get('x_centro', 0))
            y_novo = float(cfg.get('y_centro', 0))
            master_steps.append(fc.Point(x=x_novo, y=y_novo, z=z_hop_target)) # Viaja no alto
            master_steps.append(fc.ManualGcode(text=f"; --- Z-HOP COMPLETO PARA {cfg['nome']} ---"))

        # Injeta os passos do motor de geometria específico
        if cfg['tipo'] == 'cilindro':
            passos_peca = gerar_passos_cilindro(cfg)
        elif cfg['tipo'] == 'prisma':
            passos_peca = gerar_passos_prisma(cfg)
        elif cfg['tipo'] == 'bridging':
            passos_peca = bridging_teste.gerar_passos_bridging(cfg)
        elif cfg['tipo'] == 'vetor':
            passos_peca = vetor_inclinado.gerar_passos_vetor(cfg)
            
        master_steps.extend(passos_peca)
        
    # 3. Transformação em G-code
    print("-> Compilando G-code mestre...")
    arquivo_temp = f"{nome_arquivo}_bruto"
    
    fc.transform(master_steps, 'gcode', fc.GcodeControls(
        printer_name='Community/Cliever CL2Pro', 
        save_as=arquivo_temp,
        initialization_data={
            'primer': 'no_primer', 
            'dia_feed': 1.75,
            'extrusion_width': largura_extrusao,
            'extrusion_height': altura_camada
        }
    ))
    
    # 4. Pós Processamento Mestre (Limpeza e Purgas)
    arquivos = sorted(glob.glob(f'{arquivo_temp}*.gcode'), key=os.path.getmtime)
    if not arquivos:
        return False, "Erro interno: Arquivo bruto não foi gerado pelo motor FullControl."
        
    arquivo_gcode = arquivos[-1]
    with open(arquivo_gcode, 'r', encoding='utf-8', errors='replace') as f:
        linhas = f.readlines()
        
    linhas_limpas = []
    primeiro_g0 = True
    em_espiral = False
    em_perimetro = False
    em_infill = False
    
    min_x, max_x = float('inf'), float('-inf')
    min_y, max_y = float('inf'), float('-inf')
    
    for linha in linhas:
        linha = linha.rstrip('\r\n')
        
        # Filtro de comentários, mantendo marcadores estruturais
        if ';' in linha and not linha.lstrip().startswith(';'):
            comment_idx = linha.index(';')
            linha = linha[:comment_idx].rstrip()
        elif linha.lstrip().startswith(';') and not linha.strip().startswith('; ---') and not linha.strip().startswith('; ==') and linha.strip() not in (';STARTGCODE', ';ENDGCODE'):
            continue
            
        if '; --- ESPIRAL START ---' in linha: em_espiral = True
        elif '; --- ESPIRAL END ---' in linha: em_espiral = False
        elif '; --- PERIMETRO START ---' in linha: em_perimetro = True
        elif '; --- PERIMETRO END ---' in linha:
            em_perimetro = False
            if priming_ativo and priming_fim_perimetro and not em_espiral:
                linhas_limpas.append(f"G1 E{priming_perimetro_fim_qtd:.5f} F{priming_perimetro_fim_vel * 60.0} ; Retracao fim perimetro\n")
        elif '; --- INFILL START ---' in linha: em_infill = True
        elif '; --- INFILL END ---' in linha:
            em_infill = False
            if priming_ativo and priming_fim_infill and not em_espiral:
                linhas_limpas.append(f"G1 E{priming_infill_fim_qtd:.5f} F{priming_infill_fim_vel * 60.0} ; Retracao fim infill\n")
            
        if linha:
            is_travel = linha.strip().startswith('G0') and ('X' in linha or 'Y' in linha)
            
            # --- Check Limits ---
            if linha.strip().startswith('G0 ') or linha.strip().startswith('G1 '):
                partes = linha.split()
                for p in partes:
                    if p.startswith('X'):
                        try:
                            v = float(p[1:])
                            if v < min_x: min_x = v
                            if v > max_x: max_x = v
                        except: pass
                    elif p.startswith('Y'):
                        try:
                            v = float(p[1:])
                            if v < min_y: min_y = v
                            if v > max_y: max_y = v
                        except: pass
                        
            linhas_limpas.append(linha + '\n')
            
            if is_travel and priming_ativo and not em_espiral:
                if primeiro_g0:
                    linhas_limpas.append(f"G1 E{priming_inicial_qtd:.5f} F{priming_inicial_vel * 60.0} ; Purga inicial para carregar o bico\n")
                    primeiro_g0 = False
                elif em_perimetro and priming_inicio_perimetro:
                    linhas_limpas.append(f"G1 E{priming_perimetro_inicio_qtd:.5f} F{priming_perimetro_inicio_vel * 60.0} ; Purga inicio perimetro\n")
                elif em_infill and priming_inicio_infill:
                    linhas_limpas.append(f"G1 E{priming_infill_inicio_qtd:.5f} F{priming_infill_inicio_vel * 60.0} ; Purga inicio infill\n")
                    
    novo_nome = f"{nome_arquivo}.gcode"
    with open(novo_nome, 'w', encoding='utf-8') as f:
        f.writelines(linhas_limpas)
        
    try:
        os.remove(arquivo_gcode)
    except:
        pass
        
    # --- Verificacao de Limites da Mesa ---
    if hasattr(config_impressora, 'mesa_x_max'):
        lim_x_max = config_impressora.mesa_x_max
        lim_x_min = getattr(config_impressora, 'mesa_x_min', 0.0)
        lim_y_max = getattr(config_impressora, 'mesa_y_max', 300.0)
        lim_y_min = getattr(config_impressora, 'mesa_y_min', 0.0)
        
        # Verifica se obteve coordenadas validas
        if max_x != float('-inf'):
            if max_x > lim_x_max or min_x < lim_x_min or max_y > lim_y_max or min_y < lim_y_min:
                msg = (f"ATENÇÃO: A peça ultrapassa os limites físicos da mesa!\n\n"
                       f"Limites Permitidos: X [{lim_x_min} a {lim_x_max}], Y [{lim_y_min} a {lim_y_max}]\n"
                       f"Área Utilizada: X [{min_x:.1f} a {max_x:.1f}], Y [{min_y:.1f} a {max_y:.1f}]\n\n"
                       f"Verifique as posições X/Y ou os comprimentos das peças.")
                return False, msg
                
    return True, f"G-code Mestre gerado com sucesso!\nSalvo como: {novo_nome}\nTotal de peças: {len(configs_pecas)}"

# ==============================================================================
# CONFIGURAÇÃO COMPARTILHADA DA IMPRESSORA E EXTRUSÃO DIW (CLAY DIW)
# ==============================================================================

# --- Parâmetros Físicos da Extrusão ---
largura_extrusao = 3.0  # mm (Diâmetro do bico / largura do filete impresso)
altura_camada = 1.0  # mm (Altura de cada camada padrão)

# --- Parâmetros de Priming/Purga (Clay DIW) ---
priming_ativo = True  # Master switch para habilitar purga/priming automático

# Carga Inicial (Primeiro ponto de extrusão da impressão)
priming_inicial_qtd = 3.0  # mm de purga inicial para carregar o bico
priming_inicial_vel = 2.0  # mm/s (velocidade de purga inicial)

# Perímetro - Início (Start)
priming_inicio_perimetro = True  # Habilita purga no início dos perímetros
priming_perimetro_inicio_qtd = 2.0  # mm de purga no início do perímetro
priming_perimetro_inicio_vel = 2.0  # mm/s

# Perímetro - Fim (End/Retraction)
priming_fim_perimetro = True  # Habilita alívio/retração no final dos perímetros
priming_perimetro_fim_qtd = 2.0  # mm de extrusão no fim do perímetro (negativo para retração)
priming_perimetro_fim_vel = 2.0  # mm/s

# Infill - Início (Start)
priming_inicio_infill = True  # Habilita purga no início do infill
priming_infill_inicio_qtd = 2.0  # mm de purga no início do infill
priming_infill_inicio_vel = 2.0  # mm/s

# Infill - Fim (End/Retraction)
priming_fim_infill = True  # Habilita alívio/retração no final do infill
priming_infill_fim_qtd = 2.0  # mm de extrusão no fim do infill (negativo para retração)
priming_infill_fim_vel = 2.0  # mm/s

# --- Parâmetros de Finalização (Wipe/Arrasto Final) ---
wipe_final_ativo = True  # Habilita o movimento de wipe (limpeza) no fim da impressão
wipe_final_distancia = 6.0  # mm (distância de retorno sobre o próprio filamento, ex: 2x largura_extrusao)
wipe_final_subida_z = 0.5  # mm (elevação em Z durante o wipe para descolamento suave)

# --- Parâmetros de Transição para o Modo Vaso ---
transicao_vaso_z_offset = 0.5  # mm (Espaço vertical extra no início do vasemode para evitar esmagamento)
transicao_vaso_fluxo = 85.0  # % (Fluxo de transição reduzido para a primeira camada do vasemode)

# --- Limites da Mesa (Bed Limits) ---
mesa_x_min = 0.0
mesa_x_max = 300.0
mesa_y_min = 0.0
mesa_y_max = 230.0

# --- Cinematica e Extrusao (Globais) ---
resolucao_mm = 1.0
fluxo_perimetro = 100.0
fluxo_infill = 100.0
velocidade_primeira_camada = 7.5
aceleracao_primeira_camada = 100
velocidade_impressao = 7.5
aceleracao_impressao = 100
velocidade_travel = 50.0
alternar_ordem_camadas = False

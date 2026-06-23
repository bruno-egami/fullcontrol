import sys

with open('vetor_inclinado.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    if i < 30:
        new_lines.append(line)
        continue

    if i == 30:
        new_lines.append('\ndef gerar_passos_vetor(config):\n')
        new_lines.append('    # --- Extração de Parâmetros da Configuração ---\n')
        new_lines.append('    VETOR_ARQUIVO = config.get(\'vetor_arquivo\', "no-celta.dxf")\n')
        new_lines.append('    MODO_LINHA_UNICA = config.get(\'modo_linha_unica\', True)\n')
        new_lines.append('    largura_desejada_x = config.get(\'largura_x\', 100.0)\n')
        new_lines.append('    x_centro = config.get(\'x_centro\', 180.0)\n')
        new_lines.append('    y_centro = config.get(\'y_centro\', 45.0)\n')
        new_lines.append('    z_max_desejado = config.get(\'z_max_desejado\', 100.0)\n')
        new_lines.append('    angulo_parede = config.get(\'angulo_parede\', 80.0)\n')
        new_lines.append('    resolucao_mm = config.get(\'resolucao_mm\', 1.0)\n')
        new_lines.append('    NUM_CAMADAS_BASE_MACICA = int(config.get(\'num_camadas_base_macica\', 4))\n')
        new_lines.append('    sobreposicao_infill = config.get(\'sobreposicao_infill\', 1.0)\n')
        new_lines.append('    velocidade_impressao = config.get(\'velocidade_impressao\', 20.0) * 60.0\n')
        new_lines.append('    aceleracao_impressao = int(config.get(\'aceleracao_impressao\', 500))\n')
        new_lines.append('    velocidade_primeira_camada = config.get(\'velocidade_primeira_camada\', 10.0) * 60.0\n')
        new_lines.append('    aceleracao_primeira_camada = int(config.get(\'aceleracao_primeira_camada\', 500))\n')
        new_lines.append('    velocidade_travel = config.get(\'velocidade_travel\', 50.0) * 60.0\n')
        
    if 30 <= i <= 72:
        continue # skip old config block

    # Delete the old velocities config since we extracted it at the top
    if 'velocidade_impressao = config.get' in line or 'aceleracao_impressao = int(config.get' in line or 'velocidade_primeira_camada = config.get' in line or 'aceleracao_primeira_camada = int(config.get' in line or 'velocidade_travel = config.get' in line or 'sobreposicao_infill = 1.0' in line:
        continue

    if 73 <= i < 996:
        if not line.strip():
            new_lines.append('\n')
        else:
            new_lines.append('    ' + line)
        continue

    if i >= 996:
        continue # skip the rest of the file which is fc.transform and post-processing

new_lines.append('\n    return steps\n\n')

# Append standalone wrapper
new_lines.append('if __name__ == "__main__":\n')
new_lines.append('    config_teste = {\n')
new_lines.append('        "vetor_arquivo": "no-celta.dxf",\n')
new_lines.append('        "modo_linha_unica": True,\n')
new_lines.append('        "num_camadas_base_macica": 2\n')
new_lines.append('    }\n')
new_lines.append('    passos = gerar_passos_vetor(config_teste)\n')
new_lines.append('    import fullcontrol as fc\n')
new_lines.append('    fc.transform(passos, "gcode", fc.GcodeControls(printer_name="Community/Cliever CL2Pro", save_as="vetor_inclinado_solido", initialization_data={"primer": "no_primer", "dia_feed": 1.75, "extrusion_width": 3.0, "extrusion_height": 1.0}))\n')
new_lines.append('    print("\\nG-code gerado como vetor_inclinado_solido.gcode")\n')

with open('vetor_inclinado.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print('Rewrite successful!')

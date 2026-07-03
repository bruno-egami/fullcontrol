import os
import re

files = ['cilindro_inclinado.py', 'prisma_inclinado.py', 'vetor_inclinado.py', 'bridging_teste.py']

replacements = {
    r"config\.get\('resolucao_mm',\s*[\d\.]+\)": "config.get('resolucao_mm', config_impressora.resolucao_mm)",
    r"config\.get\('velocidade_impressao',\s*[\d\.]+\)": "config.get('velocidade_impressao', config_impressora.velocidade_impressao)",
    r"config\.get\('aceleracao_impressao',\s*\d+\)": "config.get('aceleracao_impressao', config_impressora.aceleracao_impressao)",
    r"config\.get\('velocidade_primeira_camada',\s*[\d\.]+\)": "config.get('velocidade_primeira_camada', config_impressora.velocidade_primeira_camada)",
    r"config\.get\('aceleracao_primeira_camada',\s*\d+\)": "config.get('aceleracao_primeira_camada', config_impressora.aceleracao_primeira_camada)",
    r"config\.get\('velocidade_travel',\s*[\d\.]+\)": "config.get('velocidade_travel', config_impressora.velocidade_travel)",
    r"config\.get\('alternar_ordem_camadas',\s*(?:True|False|'True'|'False')\)": "config.get('alternar_ordem_camadas', config_impressora.alternar_ordem_camadas)",
}

for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    if 'import config_impressora' not in content:
        # Insert after import math or import fullcontrol
        content = re.sub(r'(import math)', r'\1\nimport config_impressora', content)
        
    for pattern, rep in replacements.items():
        content = re.sub(pattern, rep, content)
        
    with open(f, 'w', encoding='utf-8') as file:
        file.write(content)

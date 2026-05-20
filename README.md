# FullControlXYZ - Geração Paramétrica Avançada

Este repositório contém scripts personalizados para geração de G-code paramétrico, desenvolvidos sobre o framework original **FullControlXYZ**.

O objetivo destes scripts é permitir a criação rápida de geometrias primitivas (prismas e cilindros) com controle sobre o percurso gerado para cada linha de extrusão, contornando as limitações dos fatiadores (slicers) tradicionais e eliminando viagens vazias (travels) desnecessárias.

Esta demanda surgiu pelo fato de que os fatiadores tradicionais não atendem certas necessidades, como, por exemplo, a impressão de peças com geometrias em que o percurso gerado para cada linha de extrusão não é otimizado, resultando em viagens vazias (travels) desnecessárias. Isto é especialmente útil para impressão DIW de argilas, em que viagens vazias podem causar falhas na impressão.

---

## 🚀 Scripts Desenvolvidos

### 1. Prisma Paramétrico (`prisma.py`)
Gera a geometria de um prisma retangular sólido ou oco, focado na otimização perfeita de cantos e fluxos.

**Funcionalidades Principais:**
- **Zonas de Camadas Dinâmicas:** Permite configurar diferentes parâmetros (número de perímetros, % de infill, fluxo de extrusão) para diferentes alturas da peça. Ideal para criar peças com base 100% sólida e paredes superiores ocas.
- **Modo Espiral Contínuo (Vase Mode):** Quando ativado em uma zona, o eixo Z sobe gradualmente ao longo dos 4 cantos do prisma (interpolação matemática perfeita), eliminando as costuras de transição de camada (Z-seam).
- **Infill Paramétrico Alternado:** Suporte a preenchimentos como `zigzag`, `grid`, `concentric` e `gyroid`. O ângulo do infill alterna automaticamente entre camadas para máxima resistência mecânica.
- **Zero-Travel Inteligente:** A rota de impressão foi puramente calculada para que o infill e os perímetros se conectem continuamente, sem retrações ou movimentos vazios do bico.
- **Pós-processamento de G-code:** O script finaliza limpando e quebrando linhas de comentários muito longos inseridos na inicialização, prevenindo estouros de buffer (erros "string too long") comuns no PrusaSlicer e firmwares de impressoras mais sensíveis.

### 2. Cilindro Paramétrico (`cilindro.py`)
Gera a geometria de um cilindro perfeito, explorando a simetria circular para gerar curvas impecáveis.

**Funcionalidades Principais:**
- **Resolução de Curva Dinâmica (`resolucao_mm`):** O script não depende de limites de polígonos (como em arquivos STL). Ele calcula matematicamente os arcos gerando 1 ponto G-code a cada `1.0 mm` de distância percorrida, resultando em cilindros perfeitamente curvos sem causar "stuttering" (engasgos) no processador da impressora.
- **Infill Otimizado com Teorema de Pitágoras:** O cálculo de interseção do infill linear no círculo usa trigonometria básica, tornando a geração do G-code extremamente limpa e rápida.
- **Clamp Direcional de Giroide:** As ondas senoidais do infill giroide são contidas rigidamente dentro da parede interna do círculo, garantindo que o infill encoste na parede para fusão perfeita, mas nunca vaze para o perímetro externo.
- **Espiral Contínua Adaptativa:** O Vase Mode sobe o eixo Z de forma micro-escalonada a cada milímetro do círculo, sendo a forma de vaso tubular mais perfeita que uma impressora FDM pode reproduzir.
- **Compatibilidade 100% com Zonas:** Assim como o prisma, o cilindro suporta perfeitamente zonas variadas (ex: 5 camadas planas sólidas, seguidas de dezenas de camadas em espiral, mudando configurações livremente).

---

## 🛠️ Como Utilizar

### 1. Preparação do Ambiente

Para configurar o ambiente de desenvolvimento e executar os scripts, siga as etapas abaixo no seu terminal:

**Passo A: Clonar o Repositório**
Clone o repositório para sua máquina local e navegue para o diretório do projeto:
```bash
git clone https://github.com/bruno-egami/fullcontrol.git
cd fullcontrol
```

**Passo B: Criar um Ambiente Virtual (`venv`)**
Recomenda-se o uso de um ambiente virtual para isolar as dependências e evitar conflitos com outros pacotes do seu sistema:
```bash
python -m venv venv
```

**Passo C: Ativar o Ambiente Virtual**
Ative o ambiente virtual de acordo com o seu sistema operacional:
*   **Windows (PowerShell):**
    ```powershell
    .\venv\Scripts\Activate.ps1
    ```
*   **Windows (CMD / Prompt de Comando):**
    ```cmd
    .\venv\Scripts\activate.bat
    ```
*   **Linux / macOS:**
    ```bash
    source venv/bin/activate
    ```

**Passo D: Instalar o Pacote Local e Dependências**
Com o ambiente virtual ativo, instale o pacote `fullcontrol` em modo editável (`-e`). Isso permite que quaisquer modificações ou desenvolvimentos futuros no pacote local sejam refletidos instantaneamente:
```bash
pip install -e .
```
*(Nota: Esse comando irá ler o `pyproject.toml` e instalar de forma automatizada todas as dependências exigidas, como `numpy`, `plotly` e `pydantic`)*

---

### 2. Configuração e Geração de G-code

Após configurar o ambiente, siga os passos abaixo para gerar seus arquivos:

1. **Ajuste os parâmetros físicos:** Edite diretamente os arquivos `prisma.py` ou `cilindro.py` no seu editor de código de preferência.
2. **Configure as Zonas de Camada:** No início de cada script, altere a seção `CONFIGURAÇÕES DO USUÁRIO` e adicione ou remova as fases/zonas dentro do dicionário `zonas_camadas`.
3. **Rode o script:** Com o ambiente virtual ativado no seu terminal, execute o comando correspondente:
   ```bash
   python prisma.py
   # ou
   python cilindro.py
   ```
4. **Pronto para Impressão:** O script compilará a peça e gerará um arquivo `.gcode` limpo na pasta do projeto. Agora você pode abri-lo no visualizador do PrusaSlicer para conferir os caminhos ou enviá-lo diretamente para a impressora!

---

## 📜 Sobre o Projeto Original (FullControlXYZ)

Este projeto foi construído utilizando as ferramentas em linguagem Python do framework **FullControl**, criado por Andrew Gleadall e Dirk Leas.
A proposta do FullControl é permitir que você controle impressoras 3D e máquinas CNC gerando caminhos de ferramenta (pontos XYZ + Extrusão) diretamente via código, oferecendo uma liberdade de design procedimental sem depender das abstrações que os fatiadores clássicos embutem.

- **Repositório Original:** [FullControlXYZ/fullcontrol](https://github.com/FullControlXYZ/fullcontrol)
- **Site Educacional:** [fullcontrol.xyz](https://fullcontrol.xyz)
- **Licença Original:** GPL v3

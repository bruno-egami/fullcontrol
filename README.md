# FullControlXYZ - Geração Paramétrica Avançada

Este repositório contém scripts personalizados para geração de G-code paramétrico, desenvolvidos sobre o framework original **FullControlXYZ**.

O objetivo destes scripts é permitir a criação rápida de geometrias primitivas (prismas e cilindros) com controle sobre o percurso gerado para cada linha de extrusão, contornando as limitações dos fatiadores (slicers) tradicionais e eliminando viagens vazias (travels) desnecessárias.

Esta demanda surgiu pelo fato de que os fatiadores tradicionais não atendem certas necessidades, como, por exemplo, a impressão de peças com geometrias em que o percurso gerado para cada linha de extrusão não é otimizado, resultando em viagens vazias (travels) desnecessárias. Isto é especialmente útil para impressão DIW de argilas, em que viagens vazias podem causar falhas na impressão.


Aqui está uma sugestão de texto técnico para ser inserido logo abaixo do cabeçalho principal do seu `README.md`. Este texto contextualiza as dificuldades específicas da impressão DIW com pastas (argila/cerâmica) e justifica por que o framework de geração paramétrica é essencial.

---

## 💧 O Desafio da Impressão DIW (Direct Ink Writing)

A impressão direta com pastas (DIW), como argila, cerâmica ou outros materiais pastosos, apresenta desafios de engenharia que os fatiadores (slicers) FDM padrão não conseguem resolver de forma eficiente. Diferente dos termoplásticos (PLA, PETG), materiais pastosos comportam-se como fluidos sob pressão e possuem limitações intrínsecas:

* **Inviabilidade de Retrações:** Em sistemas de extrusão de argila, a retração mecânica é frequentemente ineficaz ou contraproducente. Ela pode introduzir bolhas de ar no material, causar falhas de vácuo ou entupimentos no bico. A melhor estratégia é a **extrusão contínua**, sem pausas.
* **Sensibilidade a Movimentos Vazios (Travels):** Qualquer movimento de "travel" sem extrusão gera o risco de gotejamento, criação de "fios" (stringing) ou despressurização do sistema, comprometendo a adesão da camada subsequente.
* **Pressão do Sistema:** A estabilidade de uma peça de argila úmida depende da constância da pressão de extrusão. Paradas bruscas ou mudanças rápidas de direção (comuns em caminhos de infill tradicionais) geram variações de pressão que podem causar "blobs" ou falhas estruturais, levando ao colapso da peça antes da secagem.
* **Geometrias "Vase Mode" Reais:** Devido à natureza úmida do material, a técnica de impressão em espiral contínua (Vase Mode) é a mais segura para garantir a integridade estrutural, evitando "costuras" (Z-seams) que servem como pontos de fragilidade e possíveis vazamentos de material.

Os scripts deste repositório foram desenhados especificamente para atacar estes problemas, priorizando caminhos de ferramenta ininterruptos e controle preciso de fluxo, permitindo que a geometria seja ditada pela física do material, e não pelas limitações dos algoritmos de fatiamento genéricos.

### 🔧 Controle Avançado de Pressão (Clay DIW)
Para superar os desafios mecânicos e fluídicos da argila, implementamos um sistema de **controle ativo de pressão** em todos os geradores paramétricos do repositório:
* **Priming Semântico Independente:** Permite configurar de forma individual o volume de extrusão (`qtd`) e a velocidade (`vel`) da purga inicial para carregar o bico, do início de perímetros e do início de infill.
* **Alívio/Retração Independente no Fim de Percurso:** Permite configurar a velocidade e quantidade de retração no final de cada segmento impresso, distinguindo perímetros e infill de forma isolada.
* **Arrasto/Wipe Tridimensional Final (Nozzle Takeoff):** Ao término da impressão, o bico retrocede automaticamente sobre o próprio filete recém-impresso (ex: `6.0 mm`) e se eleva gradualmente no eixo Z (ex: `0.5 mm`) com o extrusor desligado. Isso cisa a tensão superficial do fluido, cortando a gota sem repuxar material e finalizando a peça com acabamento perfeito.

---

## 🚀 Scripts Desenvolvidos

### 1. Prisma Paramétrico (`prisma.py`) e Prisma Inclinado (`prisma_inclinado.py`)
Gera a geometria de um prisma retangular sólido ou oco, focado na otimização perfeita de cantos e fluxos.
* **Prisma Inclinado:** Implementa a variação dimensional progressiva por camada baseada no ângulo $\theta$ de parede, possibilitando imprimir pirâmides tridimensionais perfeitas convergentes ($\theta < 90^\circ$) ou estruturas divergentes ($\theta > 90^\circ$).
* **Zonas de Camadas Dinâmicas:** Permite configurar diferentes parâmetros (número de perímetros, % de infill, fluxo de extrusão) para diferentes alturas da peça.
* **Modo Espiral Contínuo (Vase Mode):** O eixo Z sobe gradualmente ao longo dos 4 cantos do prisma (interpolação matemática perfeita), eliminando as costuras de transição de camada (Z-seam).
* **Infill Paramétrico Alternado:** Trajetória retangular contínua ortogonal sem diagonais inclinadas, com rotação automática de ângulo a cada camada.
* **Controle de Ápice (Apex Check):** Parada de segurança automática para pirâmides convergentes assim que a área de topo encolhe abaixo da largura de extrusão física do bico.

### 2. Cilindro Paramétrico (`cilindro.py`) e Cilindro Inclinado (`cilindro_inclinado.py`)
Gera a geometria de um cilindro perfeito, explorando a simetria circular para gerar curvas impecáveis.
* **Cilindro Inclinado:** Varia o diâmetro radial de forma paramétrica por camada baseado no ângulo $\theta$ de parede para a criação de cones tridimensionais perfeitos.
* **Resolução de Curva Dinâmica (`resolucao_mm`):** Calcula matematicamente os arcos gerando 1 ponto G-code a cada `1.0 mm` de distância percorrida, resultando em cilindros perfeitamente curvos sem causar "stuttering" (engasgos).
* **Ciclos Cossenoide de 360° Alinhados (Zero Gaps):** Rampas de transição concêntrica em S-curve de $90^\circ$ de período exatamente igual a $2\pi$ para que as transições ocorram no mesmo quadrante angular em todas as voltas, garantindo distanciamento radial rigorosamente constante.
* **Fechamento Central Cossenoide:** O último anel mais interno transiciona suavemente direto para o centro geométrico absoluto ($0.0\text{ mm}$), selando o miolo sem overlap local.

### 3. Padrão e Pós-Processadores Inclinados (`gcode_postprocessor.py` e `gcode_postprocessor_inclinado.py`)
Atua como ponte inteligente entre fatiadores tradicionais (PrusaSlicer) e o FullControl.
* **Pós-processador Inclinado:** Além de gerar a base sólida plana contínua com zero travels, ele ajusta dinamicamente as dimensões radiais da base sólida à medida que ela desce no Z físico abaixo do vaso, garantindo suporte ideal para paredes inclinadas ($\theta \neq 90^\circ$).
* **Auto-Detecção de Extrusão (M82/M83):** Lê e analisa as primeiras linhas do G-code original para detectar automaticamente se a extrusão é Absoluta ou Relativa, adaptando as coordenadas da base sólida para evitar distorções no PrusaSlicer e superextrusões na impressora.
* **Alinhamento e Minimização de Travel:** Rotaciona o ponto inicial da base para coincidir exatamente com o primeiro ponto de extrusão do slicer.

### 4. Gerador Vetorial Inclinado Avançado (`vetor_inclinado.py`)
Nosso mais robusto script paramétrico tridimensional capaz de ler arquivos vetoriais externos para gerar peças tridimensionais complexas e decorativas em Vase Mode e base sólida maciça.

**Funcionalidades Principais:**
* **Parser SVG Nativo (Python puro):** Lê o XML do SVG, processando caminhos `<path d="..." />` Bézier Cúbicas/Quadráticas, polilinhas e primitivos em aproximações poligonais suaves baseadas em `resolucao_mm`.
* **Parser DXF Avançado de Curvas com Bulges:** Importa dinamicamente `ezdxf` e o módulo `ezdxf.path.make_path` para discretizar e interpolar curvas de polilinhas com bulges de arco, arcos circulares e elipses complexas de forma nativa e ultraprecisa.
* **Encadeamento de Segmentos (`linemerge`):** Consolida múltiplos segmentos de curva disjuntos em um único caminho longo contínuo de ponta a ponta.
* **Centralização e Dimensionamento Paramétrico:** Extrai a geometria bruta (polígono ou linha), escala-a proporcionalmente em relação ao seu centroide para que a largura total em X atinja exatamente `largura_desejada_x`, e translada-a na mesa para que o centro geométrico coincida com `(x_centro, y_centro)`.
* **Modo Linha Única (`MODO_LINHA_UNICA = True`):** 
  Permite fatiar geometrias auto-intersectantes de traço simples (como o **Nó da Trindade Celta**). Em vez de tentar fatiar infill ou perímetros extras na base, o script carrega o traço original e o reproduz em Z a cada camada com escala radial paramétrica perfeita em relação ao centroide.
* **Base Sólida Maciça Integrada (Opção A) sem Gaps:** 
  Para fornecer um fundo fechado e estanque ideal sob linhas auto-intersectantes, a **Opção A** (configurando `NUM_CAMADAS_BASE_MACICA`) cria uma base sólida unificada e plana na silhueta externa do nó celta fechando todos os buracos internos.
  - **Infill Concêntrico Adensado sem Gaps:** O offset de infill concêntrico foi refinado para $\text{offset\_base} = \text{recuo} + \text{num\_perimetros} \cdot \text{espacamento} - \text{sobreposicao}$ e o espaçamento foi adensado para **`0.82 * largura_extrusao`** (reduzido de `0.95`). Essa sobreposição maior e mais densa aproximou as linhas radialmente de forma perfeita, eliminando por completo o antigo gap de 1.5 mm nas laterais retas e também os vãos locais que ocorriam nas reentrâncias e curvas internas fechadas do nó celta, garantindo uma base sólida sólida, estanque e homogênea.
  - **Zero Travels:** A transição entre a base sólida maciça e a linha única ocorre sob fluxo ativo. O G-code gerado é impresso em um filete 100% contínuo e ininterrupto do primeiro ao último ponto em cada camada.

### 5. Otimizador de G-code PrusaSlicer (`gcode_optimizer.py`)
Um otimizador de percurso universal e inteligente focado nos princípios do FullControl (caminhos contínuos, sem retracts e mínimo travel).
* **Fatiamento Simplificado no Slicer:** Permite desenhar e fatiar qualquer modelo complexo 3D (STL/OBJ) no fatiador tradicional (como o PrusaSlicer) sem o Vase Mode ativo. O usuário simplesmente configura o fatiador para **1 perímetro, 0 infill, e sem camadas sólidas de topo/base**, exportando um G-code composto apenas pelas cascas da geometria original.
* **Otimização Contínua de Percurso:** O otimizador analisa a entrada, ordena os contornos de cada camada via algoritmo **TSP Greedy (Travelling Salesperson Problem)**, e rotaciona o ponto de início de cada contorno para aproximar ao máximo o final do contorno anterior, minimizando os movimentos de travel e eliminando retracts desnecessários.
* **Geração de Perímetros e Infill Customizados:** Recria parametricamente perímetros extras internos e preenchimento (infill) sob demanda diretamente no script:
  - **Infill Zigzag Otimizado:** Linhas contínuas com alternância de direção a cada camada.
  - **Infill Concêntrico Contínuo:** Espiralização contínua com transições cossinoidais ultra-suaves em S-curve entre anéis concêntricos.
* **Detecção Universal de Parâmetros:** Identifica automaticamente configurações de altura de camada, diâmetro do bico/filete, diâmetro do filamento e modo de extrusão (M82/M83), preservando as alturas de camada originais programadas no fatiador.


### 6. Configuração Compartilhada da Impressora (`config_impressora.py`)
Centraliza todas as definições físicas, de bico/extrusão, de priming independente por percurso, de transição de vaso e de wipe final em um único arquivo unificado de cabeçalho compartilhado.
* **Única Fonte de Verdade (Single Source of Truth):** Elimina a redundância e duplicação de dados entre os diferentes scripts. Quando você ajusta o diâmetro do bico (`largura_extrusao`), a altura de camada base ou recalibra as velocidades e vazões em `config_impressora.py`, todos os 5 geradores paramétricos lêem de forma sincronizada e geram o G-code perfeitamente coerente de forma automática!

---

## 📜 Instruções de Uso

### 1. Preparação do Ambiente

Para configurar o ambiente de desenvolvimento e executar os scripts, siga as etapas abaixo no seu terminal:

**Passo A: Clonar o Repositório**
```bash
git clone https://github.com/bruno-egami/fullcontrol.git
cd fullcontrol
```

**Passo B: Criar um Ambiente Virtual (`venv`)**
```bash
python -m venv venv
```

**Passo C: Ativar o Ambiente Virtual**
*   **Windows (PowerShell):** `.\venv\Scripts\Activate.ps1`
*   **Windows (CMD):** `.\venv\Scripts\activate.bat`
*   **Linux / macOS:** `source venv/bin/activate`

**Passo D: Instalar o Pacote Local e Dependências**
```bash
pip install -e .
# Instalar a biblioteca ezdxf necessária para leitura de DXF com make_path
pip install ezdxf
```

---

### 2. Geração dos Scripts Paramétricos Inclinados (`prisma_inclinado.py` e `cilindro_inclinado.py`)

1. Abra o arquivo correspondente (`prisma_inclinado.py` ou `cilindro_inclinado.py`) no seu editor de código.
2. Localize a seção `1. CONFIGURAÇÕES DO USUÁRIO` no topo.
3. Ajuste os parâmetros de extrusão (`largura_extrusao`, `altura_camada`), dimensões físicas e o ângulo tridimensional desejado:
   - `angulo_parede = 90.0` (vertical)
   - `angulo_parede = 75.0` (afunila/pirâmide)
   - `angulo_parede = 105.0` (vaso expandido)
4. Execute o script com a venv ativa no terminal:
   ```bash
   python prisma_inclinado.py
   # ou
   python cilindro_inclinado.py
   ```
5. Pronto! O G-code gerado no diretório atual poderá ser aberto no visualizador do PrusaSlicer para conferência das paredes inclinadas e espirais concêntricas contínuas.

---

### 3. Uso do Gerador Vetorial Inclinado Avançado (`vetor_inclinado.py`)

Este script lê um vetor SVG (nativo) ou DXF (via ezdxf) contendo uma geometria complexa plana e gera uma estrutura 3D inclinada paramétrica.

1. Insira seu vetor de entrada na pasta do projeto (ex: `no-celta.dxf` ou `estrela.svg`).
2. Abra o arquivo [vetor_inclinado.py](file:///d:/GitHub/FullControlXYZ/vetor_inclinado.py) no editor.
3. Localize as `CONFIGURAÇÕES DO USUÁRIO` no topo e defina:
   - `VETOR_ARQUIVO = "no-celta.dxf"`
   - `MODO_LINHA_UNICA = True` (Ativa para trajetórias de traço simples auto-intersectantes como o nó celta).
   - `NUM_CAMADAS_BASE_MACICA = 2` (Gera base maciça estanque baseada na silhueta do nó celta).
   - Ajuste `angulo_parede` para a inclinação desejada.
4. Execute o script com a venv ativa:
   ```bash
   python vetor_inclinado.py
   ```
5. A peça será gerada como um filete contínuo e ininterrupto com a base fechada maciça de forma ultra robusta.

---

### 4. Uso do Pós-Processador CLI Inclinado (`gcode_postprocessor_inclinado.py`)

Para fatiar peças complexas no fatiador e incluir uma base sólida paramétrica que acompanha a inclinação de parede:

1. Fatie o modelo complexo no PrusaSlicer em **Vase Mode** definindo **camadas sólidas inferiores e perímetros de base como 0**. Exporte o G-code (ex: `meu_vaso.gcode`).
2. Abra [gcode_postprocessor_inclinado.py](file:///d:/GitHub/FullControlXYZ/gcode_postprocessor_inclinado.py) e defina a configuração padrão no topo, ou utilize diretamente a CLI:
   ```bash
   python gcode_postprocessor_inclinado.py meu_vaso.gcode --angulo-parede 75.0 --camadas-base 3
   ```
3. O pós-processador calculará os buffers progressivos negativos ou positivos para Z de base sólida mecânica, mesclando-a de forma transparente no início do arquivo G-code.

---

### 5. Uso do Otimizador de G-code PrusaSlicer (`gcode_optimizer.py`)

Para otimizar um G-code complexo fatiado no PrusaSlicer:

1. **Configuração Recomendada no PrusaSlicer:**
   - Desative o *Vase Mode*.
   - Defina o número de perímetros para **1**.
   - Defina as camadas sólidas de topo (top) e base (bottom) para **0**.
   - Defina a densidade de infill para **0%**.
   - **IMPORTANTE:** Habilite **"Verbose G-code"** (Print Settings > Output options) para permitir a detecção precisa de camadas via marcadores `;LAYER_CHANGE`.
   - Desative qualquer recurso de *Arc Fitting* (usar apenas segmentos lineares G0/G1).
   - Exporte o arquivo G-code (ex: `modelo_original.gcode`).

2. **Execução do Script Otimizador:**
   Com a `venv` ativa, execute o script passando as opções de percurso desejadas:
   ```bash
   # Otimização simples (mantendo 1 perímetro e sem infill)
   python gcode_optimizer.py modelo_original.gcode

   # Adicionar 2 perímetros extras e infill concêntrico espiralado contínuo a 100% de densidade
   python gcode_optimizer.py modelo_original.gcode --num-perimetros 3 --infill-pattern concentric --infill-percent 100

   # Usar infill zigzag a 45 graus e ajustar velocidade de extrusão
   python gcode_optimizer.py modelo_original.gcode --num-perimetros 2 --infill-pattern zigzag --angulo-infill 45 --velocidade 800
   ```

3. **Parâmetros Customizáveis da CLI:**
   - `--num-perimetros N`: Quantidade total de perímetros desejados (default: `1`).
   - `--infill-pattern {none, concentric, zigzag}`: Padrão de preenchimento desejado (default: `none`).
   - `--infill-percent P`: Porcentagem de densidade do infill (default: `100.0`).
   - `--angulo-infill A`: Ângulo base para infill zigzag em graus (default: `45.0`).
   - `--largura-extrusao W`: Largura nominal do filete impresso em mm (default: `3.0`).
   - `--velocidade V`: Velocidade de impressão/extrusão em mm/min (default: `600.0`).
   - `--fluxo F`: Multiplicador de fluxo em % (default: `100`).

O script preserva perfeitamente o cabeçalho (`;STARTGCODE`) e o rodapé (`;ENDGCODE`) originais do fatiador, gerando o arquivo `modelo_original_otimizado.gcode` pronto para ser enviado para a impressora de argila.

---

## 📜 Sobre o Projeto Original (FullControlXYZ)

Este projeto foi construído utilizando as ferramentas em linguagem Python do framework **FullControl**, criado por Andrew Gleadall e Dirk Leas.
A proposta do FullControl é permitir que você controle impressoras 3D e máquinas CNC gerando caminhos de ferramenta (pontos XYZ + Extrusão) diretamente via código, oferecendo uma liberdade de design procedimental sem depender das abstrações que os fatiadores clássicos embutem.

- **Repositório Original:** [FullControlXYZ/fullcontrol](https://github.com/FullControlXYZ/fullcontrol)
- **Site Educacional:** [fullcontrol.xyz](https://fullcontrol.xyz)
- **Licença Original:** GPL v3

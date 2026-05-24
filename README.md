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

### 3. Pós-Processador de G-code (`gcode_postprocessor.py`)
Esta nova ferramenta atua como uma ponte inteligente entre fatiadores tradicionais (como o **PrusaSlicer**) e o **FullControl**, permitindo fatiar geometrias complexas em modo vaso (*Vase Mode*) e gerar uma base sólida mecanicamente otimizada com o FullControl.

**O Problema Resolvido:**
Em impressões DIW (argila), fatiadores tradicionais geram bases sólidas com muitas retrações, preenchimentos fragmentados e movimentos vazios (*travels*), o que costuma causar bolhas de ar e colapso da peça. Com este script, você fatia sua peça complexa no PrusaSlicer em *Vase Mode* **sem nenhuma base** (perímetros inferiores = 0, camadas de base = 0), e a ferramenta gera uma base sólida perfeita, 100% contínua e sem travels pelo FullControl, mesclando-a de forma transparente ao início da peça.

**Funcionalidades Principais:**
- **Variáveis Centralizadas no Topo:** Assim como no `prisma.py` e `cilindro.py`, todos os parâmetros agora podem ser editados diretamente em um bloco de `CONFIGURAÇÃO PADRÃO` no topo do script. Isso facilita o uso sem precisar lembrar ou digitar comandos complexos no terminal.
- **Auto-Detecção do Modo de Extrusão (M82/M83):** O script lê e analisa as primeiras linhas do G-code de entrada para detectar automaticamente se a extrusão do slicer é **Absoluta** (`M82`) ou **Relativa** (`M83`).
- **Resolução de Espessuras no Visualizador:** Ajusta dinamicamente a geração da base do FullControl e adiciona comandos explícitos de transição (`M82`/`M83` + `G92 E0.0`) no G-code mesclado. Isso evita que movimentos absolutos sejam interpretados como relativos, resolvendo as distorções visuais (linhas colossais/troncos de árvore) no visualizador do PrusaSlicer e prevenindo sobreextrusões fatais na impressora.
- **Extração Automática de Contorno:** Lê o G-code do PrusaSlicer, busca os movimentos de extrusão da primeira camada até uma altura de referência especificada e reconstrói o polígono exato do perímetro usando geometria computacional (`shapely`).
- **Geração de Base Robusta (FullControl):** Permite configurar a altura da camada, a largura da extrusão, o número de perímetros internos da base e o tipo de preenchimento.
- **Padrões de Preenchimento Otimizados:**
  - `zigzag`: Linhas retas que alternam automaticamente o ângulo a cada camada para fusão mecânica perfeita.
  - `concentric`: Anéis concêntricos paralelos à parede externa, gerando caminhos de espiral concêntrica impecáveis (perfeitos para cerâmica).
- **Alinhamento e Minimização de Travel (Zero-Travel Dinâmico):** Rotaciona ou reorganiza a ordem de impressão dos perímetros da base gerados no FullControl para que o **último ponto da base coincida perfeitamente com o primeiro ponto de extrusão do G-code do fatiador**. Isso elimina movimentos vazios bruscos entre a base e o início do vaso.
- **Z-Offset Automático:** Aplica um deslocamento preciso em todas as coordenadas Z do corpo do G-code original, subindo a peça proporcionalmente à altura da base criada (`camadas-base * altura-camada`), garantindo continuidade perfeita.
- **Mesclagem Inteligente de Arquivos:** Preserva o cabeçalho original de inicialização da impressora e o rodapé final do PrusaSlicer, inserindo a base do FullControl e a peça no meio de forma segura.

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

### 3. Uso do Pós-Processador de G-code

O pós-processador utiliza a biblioteca `shapely`, que é instalada automaticamente na preparação do ambiente virtual caso você utilize a versão atualizada do repositório (com suporte no `pyproject.toml` e `requirements.txt`).

#### A. Como Preparar o G-code no PrusaSlicer:
1. Importe seu modelo 3D complexo.
2. Ative a opção **Spiral vase** (Modo Vaso).
3. Defina **Bottom solid layers** (Camadas sólidas inferiores) como `0`.
4. Defina **Skirt** (Aba) e **Brim** (Borda) como `0` (ou certifique-se de que eles não fiquem na mesma altura da primeira camada caso queira usá-los, embora o recomendado seja gerar a base diretamente pelo script).
5. Exporte o arquivo G-code (ex: `meu_vaso.gcode`).

#### B. Como Executar a Ferramenta:
Você pode executar o pós-processador de duas formas extremamente convenientes:

##### Método 1: Edição Direta no Script (Recomendado/Mais Prático)
1. Abra o arquivo [gcode_postprocessor.py](file:///d:/GitHub/FullControlXYZ/gcode_postprocessor.py) no seu editor de código.
2. No topo do arquivo, localize a seção `CONFIGURAÇÃO PADRÃO`.
3. Ajuste o nome do arquivo de entrada na variável `INPUT_GCODE` e configure os demais parâmetros da sua base sólida.
4. Salve o arquivo e execute o script simplesmente com:
   ```bash
   python gcode_postprocessor.py
   ```

##### Método 2: Interface de Linha de Comando (CLI)
Com o ambiente virtual ativo, você também pode passar os parâmetros diretamente no terminal. Qualquer argumento fornecido via terminal irá **sobrescrever** o valor definido no topo do arquivo:
```bash
python gcode_postprocessor.py meu_vaso.gcode --z-ref 1.5 --camadas-base 3
```

#### C. Parâmetros da CLI (Interface de Linha de Comando):

Abaixo estão todos os parâmetros que você pode configurar para ajustar a geração da base sólida (todos os padrões listados abaixo agora correspondem aos valores globais definidos no topo do script):

| Parâmetro | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `input` | *Posicional* | `INPUT_GCODE` | Caminho do arquivo G-code do PrusaSlicer (vase mode). Se omitido, utiliza a variável do topo. |
| `--z-ref` | `float` | `Z_REF` | Altura Z (mm) no G-code original para servir de referência na extração do perímetro. |
| `--camadas-base` | `int` | `CAMADAS_BASE` | Quantidade de camadas sólidas a serem geradas para a base. |
| `--largura-extrusao`| `float` | `LARGURA_EXTRUSAO` | Largura da linha de extrusão (mm) desejada na base. |
| `--altura-camada` | `float` | `ALTURA_CAMADA` | Altura (mm) de cada camada gerada na base. |
| `--num-perimetros` | `int` | `NUM_PERIMETROS` | Número de contornos de perímetros internos antes de iniciar o infill. |
| `--infill-pattern` | `str` | `INFILL_PATTERN` | Tipo de preenchimento. Opções: `zigzag` ou `concentric`. |
| `--angulo-infill` | `float` | `ANGULO_INFILL` | Ângulo inicial do infill em graus (apenas para padrão `zigzag`). |
| `--velocidade` | `float` | `VELOCIDADE` | Velocidade de extrusão na base em mm/min (F600). |
| `--fluxo` | `int` | `FLUXO` | Multiplicador de fluxo em % para as camadas de base. |
| `--output` | `str` | `OUTPUT_GCODE` | Caminho do arquivo de saída. Se omitido, salva como `{input}_com_base.gcode`. |
| `--printer` | `str` | `PRINTER_PROFILE` | Perfil de impressora registrado no FullControl. |

**Exemplo mesclando CLI e preenchimento concêntrico:**
```bash
python gcode_postprocessor.py vaso_complexo.gcode --largura-extrusao 4.0 --infill-pattern concentric --output vaso_pronto.gcode
```

---

## 📜 Sobre o Projeto Original (FullControlXYZ)

Este projeto foi construído utilizando as ferramentas em linguagem Python do framework **FullControl**, criado por Andrew Gleadall e Dirk Leas.
A proposta do FullControl é permitir que você controle impressoras 3D e máquinas CNC gerando caminhos de ferramenta (pontos XYZ + Extrusão) diretamente via código, oferecendo uma liberdade de design procedimental sem depender das abstrações que os fatiadores clássicos embutem.

- **Repositório Original:** [FullControlXYZ/fullcontrol](https://github.com/FullControlXYZ/fullcontrol)
- **Site Educacional:** [fullcontrol.xyz](https://fullcontrol.xyz)
- **Licença Original:** GPL v3

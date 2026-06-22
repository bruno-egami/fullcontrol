import customtkinter as ctk
from tkinter import messagebox
import json
import importlib
from motor_mestre import gerar_gcode_sequencial
import config_impressora
import motor_mestre
import cilindro_inclinado
import prisma_inclinado

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class Piece:
    _id_counter = 1
    
    def __init__(self, tipo):
        self.id = Piece._id_counter
        Piece._id_counter += 1
        
        self.tipo = tipo # 'cilindro' ou 'prisma'
        self.nome = f"{tipo.capitalize()} {self.id}"
        
        # Parâmetros padrão base
        self.config = {
            'x_centro': 150.0,
            'y_centro': 150.0,
            'z_max_desejado': 10.0,
            'angulo_parede': 90.0,
            'largura_extrusao': 3.0,
            'altura_camada': 1.0,
            'zonas_camadas': [{
                'qtd_camadas': 999,
                'num_perimetros': 1,
                'infill_percent': 100.0,
                'infill_pattern': 'concentric',
                'fluxo_perimetro': 100.0,
                'fluxo_infill': 100.0,
                'espiral': 'False'
            }],
            'resolucao_mm': 1.0,
            'alternar_ordem_camadas': 'True',
            'angulo_infill_base': 45.0,
            'sobreposicao_infill': 0.5,
            'amplitude_gyroid': 2.0,
            'comprimento_onda_gyroid': 15.0,
            'transicao_vaso_z_offset': 0.5,
            'transicao_vaso_fluxo': 85.0,
            'wipe_final_ativo': 'True',
            'wipe_final_distancia': 6.0,
            'wipe_final_subida_z': 0.5
        }
        
        if tipo == 'cilindro':
            self.config['raio_cilindro'] = 20.0
        elif tipo == 'prisma':
            self.config['largura_x'] = 30.0
            self.config['comprimento_y'] = 30.0

class PrintQueueApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("FullControlXYZ - Impressão Sequencial")
        self.geometry("900x600")
        
        self.pecas_fila = []
        self.peca_selecionada = None
        
        # --- Layout Principal ---
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # PAINEL ESQUERDO (Fila de Impressão)
        self.left_panel = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.left_panel.grid(row=0, column=0, sticky="nsew")
        self.left_panel.grid_rowconfigure(2, weight=1)
        
        self.lbl_fila = ctk.CTkLabel(self.left_panel, text="Fila de Impressão", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_fila.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Botões para adicionar
        self.frame_botoes_add = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.frame_botoes_add.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        
        self.btn_add_cilindro = ctk.CTkButton(self.frame_botoes_add, text="+ Cilindro", width=100, command=lambda: self.adicionar_peca('cilindro'))
        self.btn_add_cilindro.pack(side="left", padx=5)
        
        self.btn_add_prisma = ctk.CTkButton(self.frame_botoes_add, text="+ Prisma", width=100, command=lambda: self.adicionar_peca('prisma'))
        self.btn_add_prisma.pack(side="right", padx=5)

        # Lista de peças (Scrollable)
        self.lista_pecas_frame = ctk.CTkScrollableFrame(self.left_panel)
        self.lista_pecas_frame.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")
        
        # Nome do Arquivo
        self.frame_arquivo = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.frame_arquivo.grid(row=3, column=0, padx=20, pady=(10, 0), sticky="ew")
        self.lbl_arquivo = ctk.CTkLabel(self.frame_arquivo, text="Nome do Arquivo:")
        self.lbl_arquivo.pack(anchor="w")
        self.entry_nome_arquivo = ctk.CTkEntry(self.frame_arquivo, placeholder_text="Ex: pecas_finais")
        self.entry_nome_arquivo.insert(0, "gcode_final_sequencial")
        self.entry_nome_arquivo.pack(fill="x")

        # Botões de Ação Final
        self.frame_acoes = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.frame_acoes.grid(row=4, column=0, padx=20, pady=20, sticky="ew")
        
        self.btn_config_global = ctk.CTkButton(self.frame_acoes, text="Configurações Globais", fg_color="gray40", hover_color="gray30", height=30, command=self.abrir_config_global)
        self.btn_config_global.pack(fill="x", pady=(0, 10))

        self.btn_gerar_gcode = ctk.CTkButton(self.frame_acoes, text="Gerar G-Code Mestre", fg_color="green", hover_color="darkgreen", height=40, font=ctk.CTkFont(weight="bold"), command=self.gerar_gcode)
        self.btn_gerar_gcode.pack(fill="x")

        # PAINEL DIREITO (Parâmetros da Peça)
        self.right_panel = ctk.CTkScrollableFrame(self, corner_radius=0)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.right_panel.grid_columnconfigure(1, weight=1)
        
        self.lbl_titulo_params = ctk.CTkLabel(self.right_panel, text="Parâmetros da Peça Selecionada", font=ctk.CTkFont(size=20, weight="bold"))
        self.lbl_titulo_params.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 20), sticky="w")
        
        self.frame_inputs = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        self.frame_inputs.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.frame_inputs.grid_columnconfigure(1, weight=1)
        
        self.inputs_vars = {} # Dicionário para armazenar as variáveis do Tkinter vinculadas aos inputs
        self.atualizar_lista_ui()

    def adicionar_peca(self, tipo):
        nova_peca = Piece(tipo)
        self.pecas_fila.append(nova_peca)
        self.selecionar_peca(nova_peca)
        self.atualizar_lista_ui()

    def remover_peca(self, peca):
        self.pecas_fila.remove(peca)
        if self.peca_selecionada == peca:
            self.peca_selecionada = None
            self.limpar_painel_direito()
        self.atualizar_lista_ui()

    def selecionar_peca(self, peca):
        # Salva as alterações da peça anterior antes de mudar
        self.salvar_inputs_na_peca_selecionada()
        
        self.peca_selecionada = peca
        self.atualizar_lista_ui()
        self.construir_painel_direito()

    def atualizar_lista_ui(self):
        # Limpa a lista atual
        for widget in self.lista_pecas_frame.winfo_children():
            widget.destroy()
            
        for peca in self.pecas_fila:
            row_frame = ctk.CTkFrame(self.lista_pecas_frame)
            row_frame.pack(fill="x", pady=2)
            
            cor_bg = "gray25" if peca == self.peca_selecionada else "transparent"
            row_frame.configure(fg_color=cor_bg)
            
            btn_nome = ctk.CTkButton(row_frame, text=peca.nome, fg_color="transparent", anchor="w", command=lambda p=peca: self.selecionar_peca(p))
            btn_nome.pack(side="left", fill="x", expand=True, padx=5)
            
            btn_remover = ctk.CTkButton(row_frame, text="X", width=30, fg_color="red", hover_color="darkred", command=lambda p=peca: self.remover_peca(p))
            btn_remover.pack(side="right", padx=5)

    def limpar_painel_direito(self):
        for widget in self.frame_inputs.winfo_children():
            widget.destroy()
        self.inputs_vars.clear()
        self.lbl_titulo_params.configure(text="Nenhuma peça selecionada")

    def salvar_inputs_na_peca_selecionada(self):
        if not self.peca_selecionada:
            return
            
        try:
            # Nome
            if 'nome' in self.inputs_vars:
                self.peca_selecionada.nome = self.inputs_vars['nome'].get()
            
            zonas_dict = {}
            
            # Parâmetros geométricos
            for key, var in self.inputs_vars.items():
                if key != 'nome':
                    val = var.get()
                    # Tenta converter para float se for número, senão mantém string
                    try:
                        val_num = float(val)
                    except ValueError:
                        val_num = val
                        
                    if key.startswith('zona_'):
                        parts = key.split('_', 2)
                        idx = int(parts[1])
                        prop = parts[2]
                        if idx not in zonas_dict:
                            zonas_dict[idx] = {}
                        zonas_dict[idx][prop] = val_num
                    else:
                        self.peca_selecionada.config[key] = val_num
                        
            if zonas_dict:
                nova_lista = []
                for idx in sorted(zonas_dict.keys()):
                    nova_lista.append(zonas_dict[idx])
                self.peca_selecionada.config['zonas_camadas'] = nova_lista
                
        except Exception as e:
            print("Erro ao salvar parâmetros:", e)

    def construir_painel_direito(self):
        self.limpar_painel_direito()
        if not self.peca_selecionada:
            return
            
        self.lbl_titulo_params.configure(text=f"Editando: {self.peca_selecionada.nome}")
        
        row_idx = 0
        def add_input(label_text, key_name, default_val):
            nonlocal row_idx
            lbl = ctk.CTkLabel(self.frame_inputs, text=label_text)
            lbl.grid(row=row_idx, column=0, padx=10, pady=10, sticky="e")
            
            var = ctk.StringVar(value=str(default_val))
            self.inputs_vars[key_name] = var
            
            entry = ctk.CTkEntry(self.frame_inputs, textvariable=var, width=200)
            entry.grid(row=row_idx, column=1, padx=10, pady=10, sticky="w")
            
            row_idx += 1
            
        def add_combobox(label_text, key_name, default_val, options):
            nonlocal row_idx
            lbl = ctk.CTkLabel(self.frame_inputs, text=label_text)
            lbl.grid(row=row_idx, column=0, padx=10, pady=10, sticky="e")
            
            var = ctk.StringVar(value=str(default_val))
            self.inputs_vars[key_name] = var
            
            combo = ctk.CTkOptionMenu(self.frame_inputs, variable=var, values=options, width=200)
            combo.grid(row=row_idx, column=1, padx=10, pady=10, sticky="w")
            
            row_idx += 1

        add_input("Nome da Peça:", "nome", self.peca_selecionada.nome)
        
        # Separador - Posição e Altura
        lbl_sep = ctk.CTkLabel(self.frame_inputs, text="--- Posição e Altura ---", text_color="gray")
        lbl_sep.grid(row=row_idx, column=0, columnspan=2, pady=(15, 5)); row_idx += 1
        
        add_input("Posição X Centro (mm):", "x_centro", self.peca_selecionada.config.get('x_centro', 0))
        add_input("Posição Y Centro (mm):", "y_centro", self.peca_selecionada.config.get('y_centro', 0))
        add_input("Altura Final Z (mm):", "z_max_desejado", self.peca_selecionada.config.get('z_max_desejado', 0))
        add_input("Ângulo da Parede (graus):", "angulo_parede", self.peca_selecionada.config.get('angulo_parede', 90))
        
        # Separador - Geometria Específica
        lbl_sep2 = ctk.CTkLabel(self.frame_inputs, text="--- Dimensões ---", text_color="gray")
        lbl_sep2.grid(row=row_idx, column=0, columnspan=2, pady=(15, 5)); row_idx += 1
        
        if self.peca_selecionada.tipo == 'cilindro':
            add_input("Raio (mm):", "raio_cilindro", self.peca_selecionada.config.get('raio_cilindro', 20))
        elif self.peca_selecionada.tipo == 'prisma':
            add_input("Largura X (mm):", "largura_x", self.peca_selecionada.config.get('largura_x', 30))
            add_input("Comprimento Y (mm):", "comprimento_y", self.peca_selecionada.config.get('comprimento_y', 30))

        # Separador - Zonas de Camada
        frame_zonas_header = ctk.CTkFrame(self.frame_inputs, fg_color="transparent")
        frame_zonas_header.grid(row=row_idx, column=0, columnspan=2, pady=(15, 5), sticky="ew")
        
        lbl_zonas = ctk.CTkLabel(frame_zonas_header, text="--- Zonas de Camadas ---", text_color="gray")
        lbl_zonas.pack(side="left")
        
        btn_add_zona = ctk.CTkButton(frame_zonas_header, text="+ Zona", width=60, command=self.add_zona_ui)
        btn_add_zona.pack(side="right", padx=5)
        
        btn_rem_zona = ctk.CTkButton(frame_zonas_header, text="- Zona", width=60, fg_color="red", hover_color="darkred", command=self.rem_zona_ui)
        btn_rem_zona.pack(side="right")
        
        row_idx += 1
        
        zonas = self.peca_selecionada.config.get('zonas_camadas', [])
        for i, zona in enumerate(zonas):
            lbl_z = ctk.CTkLabel(self.frame_inputs, text=f"** Zona {i+1} **", font=ctk.CTkFont(weight="bold"))
            lbl_z.grid(row=row_idx, column=0, columnspan=2, pady=(10, 0)); row_idx += 1
            
            add_input("Qtd Camadas:", f"zona_{i}_qtd_camadas", zona.get('qtd_camadas', 999))
            add_input("Nº Perímetros:", f"zona_{i}_num_perimetros", zona.get('num_perimetros', 1))
            add_input("Infill (%) [0 a 100]:", f"zona_{i}_infill_percent", zona.get('infill_percent', 100.0))
            add_combobox("Padrão Infill:", f"zona_{i}_infill_pattern", zona.get('infill_pattern', 'concentric'), ["concentric", "grid", "zigzag", "gyroid"])
            add_input("Fluxo Perímetro (%):", f"zona_{i}_fluxo_perimetro", zona.get('fluxo_perimetro', 100.0))
            add_input("Fluxo Infill (%):", f"zona_{i}_fluxo_infill", zona.get('fluxo_infill', 100.0))
            add_combobox("Modo Espiral:", f"zona_{i}_espiral", str(zona.get('espiral', 'False')), ["True", "False"])
        
        lbl_sep4 = ctk.CTkLabel(self.frame_inputs, text="--- Gyroid Específicos ---", text_color="gray")
        lbl_sep4.grid(row=row_idx, column=0, columnspan=2, pady=(15, 5)); row_idx += 1
        
        add_input("Amplitude Gyroid:", "amplitude_gyroid", self.peca_selecionada.config.get('amplitude_gyroid', 2.0))
        add_input("Comp. Onda Gyroid:", "comprimento_onda_gyroid", self.peca_selecionada.config.get('comprimento_onda_gyroid', 15.0))
        
        lbl_sep5 = ctk.CTkLabel(self.frame_inputs, text="--- Extrusão e Fluxo ---", text_color="gray")
        lbl_sep5.grid(row=row_idx, column=0, columnspan=2, pady=(15, 5)); row_idx += 1
        
        add_input("Resolução Curvas (mm):", "resolucao_mm", self.peca_selecionada.config.get('resolucao_mm', 1.0))
        add_input("Fluxo Perímetro (%):", "fluxo_perimetro", self.peca_selecionada.config.get('fluxo_perimetro', 100.0))
        add_input("Fluxo Infill (%):", "fluxo_infill", self.peca_selecionada.config.get('fluxo_infill', 100.0))
        
        lbl_sep6 = ctk.CTkLabel(self.frame_inputs, text="--- Especiais ---", text_color="gray")
        lbl_sep6.grid(row=row_idx, column=0, columnspan=2, pady=(15, 5)); row_idx += 1
        
        add_combobox("Modo Vaso/Espiral:", "espiral", self.peca_selecionada.config.get('espiral', 'False'), ["True", "False"])
        add_input("Vasemode Offset Z (mm):", "transicao_vaso_z_offset", self.peca_selecionada.config.get('transicao_vaso_z_offset', 0.5))
        add_input("Vasemode Fluxo (%):", "transicao_vaso_fluxo", self.peca_selecionada.config.get('transicao_vaso_fluxo', 85.0))
        add_combobox("Alternar Ordem Camadas:", "alternar_ordem_camadas", self.peca_selecionada.config.get('alternar_ordem_camadas', 'True'), ["True", "False"])
        
        lbl_sep7 = ctk.CTkLabel(self.frame_inputs, text="--- Wipe Final ---", text_color="gray")
        lbl_sep7.grid(row=row_idx, column=0, columnspan=2, pady=(15, 5)); row_idx += 1
        
        add_combobox("Ativar Wipe Final:", "wipe_final_ativo", self.peca_selecionada.config.get('wipe_final_ativo', 'True'), ["True", "False"])
        add_input("Distância do Wipe (mm):", "wipe_final_distancia", self.peca_selecionada.config.get('wipe_final_distancia', 6.0))
        add_input("Subida Z no Wipe (mm):", "wipe_final_subida_z", self.peca_selecionada.config.get('wipe_final_subida_z', 0.5))

    def add_zona_ui(self):
        self.salvar_inputs_na_peca_selecionada()
        zonas = self.peca_selecionada.config.get('zonas_camadas', [])
        nova_zona = {
            'qtd_camadas': 10,
            'num_perimetros': 1,
            'infill_percent': 100.0,
            'infill_pattern': 'concentric',
            'fluxo_perimetro': 100.0,
            'fluxo_infill': 100.0,
            'espiral': 'False'
        }
        zonas.append(nova_zona)
        self.peca_selecionada.config['zonas_camadas'] = zonas
        self.construir_painel_direito()

    def rem_zona_ui(self):
        self.salvar_inputs_na_peca_selecionada()
        zonas = self.peca_selecionada.config.get('zonas_camadas', [])
        if len(zonas) > 1:
            zonas.pop()
            self.peca_selecionada.config['zonas_camadas'] = zonas
            self.construir_painel_direito()

    def abrir_config_global(self):
        if hasattr(self, 'config_window') and self.config_window is not None and self.config_window.winfo_exists():
            self.config_window.focus()
            return
            
        self.config_window = ctk.CTkToplevel(self)
        self.config_window.title("Configurações Gerais (Impressora/DIW)")
        self.config_window.geometry("500x700")
        self.config_window.transient(self) # Fica sempre à frente da janela principal
        
        scroll = ctk.CTkScrollableFrame(self.config_window)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        lbl_titulo = ctk.CTkLabel(scroll, text="Parâmetros Globais do Sistema", font=ctk.CTkFont(size=18, weight="bold"))
        lbl_titulo.grid(row=0, column=0, columnspan=2, pady=(10, 20))
        
        # Obter variaveis dinamicas de config_impressora
        self.vars_globais = {}
        row_idx = 1
        
        # Mapeamento de nomes amigáveis
        nomes_amigaveis = {
            'largura_extrusao': 'Largura de Extrusão (mm)',
            'altura_camada': 'Altura da Camada (mm)',
            'priming_ativo': 'Ativar Purga/Priming Geral',
            'priming_inicial_qtd': 'Carga Inicial: Quantidade (mm)',
            'priming_inicial_vel': 'Carga Inicial: Velocidade (mm/min)',
            'priming_inicio_perimetro': 'Perímetro: Ativar Purga no Início',
            'priming_perimetro_inicio_qtd': 'Perímetro Início: Quantidade (mm)',
            'priming_perimetro_inicio_vel': 'Perímetro Início: Velocidade (mm/min)',
            'priming_fim_perimetro': 'Perímetro: Ativar Retração no Fim',
            'priming_perimetro_fim_qtd': 'Perímetro Fim: Retração (mm)',
            'priming_perimetro_fim_vel': 'Perímetro Fim: Velocidade (mm/min)',
            'priming_inicio_infill': 'Infill: Ativar Purga no Início',
            'priming_infill_inicio_qtd': 'Infill Início: Quantidade (mm)',
            'priming_infill_inicio_vel': 'Infill Início: Velocidade (mm/min)',
            'priming_fim_infill': 'Infill: Ativar Retração no Fim',
            'priming_infill_fim_qtd': 'Infill Fim: Retração (mm)',
            'priming_infill_fim_vel': 'Infill Fim: Velocidade (mm/min)',
            'wipe_final_ativo': 'Wipe Final: Ativar Arrasto',
            'wipe_final_distancia': 'Wipe Final: Distância (mm)',
            'wipe_final_subida_z': 'Wipe Final: Subida em Z (mm)',
            'transicao_vaso_z_offset': 'Vasemode: Offset Z de Transição (mm)',
            'transicao_vaso_fluxo': 'Vasemode: Fluxo de Transição (%)'
        }
        
        # Força o reload para garantir que lemos o estado mais recente
        importlib.reload(config_impressora)
        
        for key in dir(config_impressora):
            if not key.startswith('_') and not hasattr(getattr(config_impressora, key), '__call__'):
                val = getattr(config_impressora, key)
                if isinstance(val, (int, float, bool, str)):
                    # Pega o nome amigável ou formata o nome da variável se não existir
                    nome_display = nomes_amigaveis.get(key, key.replace('_', ' ').title())
                    
                    lbl = ctk.CTkLabel(scroll, text=nome_display)
                    lbl.grid(row=row_idx, column=0, sticky="e", padx=10, pady=5)
                    
                    var = ctk.StringVar(value=str(val))
                    self.vars_globais[key] = (var, type(val))
                    
                    entry = ctk.CTkEntry(scroll, textvariable=var, width=200)
                    entry.grid(row=row_idx, column=1, sticky="w", padx=10, pady=5)
                    row_idx += 1
                    
        btn_salvar = ctk.CTkButton(self.config_window, text="Salvar Alterações", fg_color="blue", command=self.salvar_config_global)
        btn_salvar.pack(pady=10)

    def salvar_config_global(self):
        new_configs = {}
        for key, (var, tipo) in self.vars_globais.items():
            val_str = var.get()
            try:
                if tipo == bool:
                    new_configs[key] = val_str.lower() in ('true', '1', 't', 'y', 'yes')
                else:
                    new_configs[key] = tipo(val_str)
            except ValueError:
                messagebox.showerror("Erro de Valor", f"O valor '{val_str}' para {key} é inválido para o tipo {tipo.__name__}.")
                return
                
        # Atualiza o arquivo python fisicamente
        try:
            with open("config_impressora.py", "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            for i, line in enumerate(lines):
                # Check se a linha comeca com a variavel (ignorando espacos)
                stripped = line.lstrip()
                for key, val in new_configs.items():
                    if stripped.startswith(key + " =") or stripped.startswith(key + "="):
                        comment_part = "\n"
                        if "#" in line:
                            comment_part = "  " + line[line.index("#"):]
                            if not comment_part.endswith('\n'):
                                comment_part += '\n'
                                
                        if isinstance(val, str):
                            val_str = f"'{val}'"
                        else:
                            val_str = str(val)
                            
                        # Respeita identacao original
                        indent = line[:len(line) - len(stripped)]
                        lines[i] = f"{indent}{key} = {val_str}{comment_part}"
                        break
                        
            with open("config_impressora.py", "w", encoding="utf-8") as f:
                f.writelines(lines)
                
            # Recarrega os modulos afetados
            importlib.reload(config_impressora)
            importlib.reload(motor_mestre)
            importlib.reload(cilindro_inclinado)
            importlib.reload(prisma_inclinado)
            
            messagebox.showinfo("Sucesso", "Configurações Globais salvas e recarregadas com sucesso!")
            self.config_window.destroy()
            
        except Exception as e:
            messagebox.showerror("Erro Crítico", f"Falha ao salvar config_impressora.py:\n{str(e)}")

    def gerar_gcode(self):
        self.salvar_inputs_na_peca_selecionada()
        self.atualizar_lista_ui()
        
        if len(self.pecas_fila) == 0:
            messagebox.showwarning("Fila Vazia", "Adicione pelo menos uma peça à fila antes de gerar o G-Code.")
            return
            
        print("Iniciando geração sequencial de peças...")
        
        nome_arquivo = self.entry_nome_arquivo.get().strip()
        if not nome_arquivo:
            nome_arquivo = "gcode_final_sequencial"
            
        # Garante que os módulos tenham a config mais atual antes de rodar
        importlib.reload(config_impressora)
        importlib.reload(motor_mestre)
        importlib.reload(cilindro_inclinado)
        importlib.reload(prisma_inclinado)
        
        # Chama o motor mestre!
        sucesso, mensagem = motor_mestre.gerar_gcode_sequencial(self.pecas_fila, nome_arquivo=nome_arquivo)
        
        if sucesso:
            messagebox.showinfo("Sucesso", mensagem)
        else:
            messagebox.showerror("Erro de Geração", mensagem)

if __name__ == "__main__":
    app = PrintQueueApp()
    app.mainloop()

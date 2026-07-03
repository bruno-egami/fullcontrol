import customtkinter as ctk
from tkinter import messagebox
import json
import importlib
from motor_mestre import gerar_gcode_sequencial
import config_impressora
import motor_mestre
import cilindro_inclinado
import prisma_inclinado
import bridging_teste

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class Piece:
    _id_counter = 1
    
    def __init__(self, tipo):
        self.id = Piece._id_counter
        Piece._id_counter += 1
        
        self.tipo = tipo # 'cilindro' ou 'prisma'
        self.nome = f"{tipo.capitalize()} {self.id}"
        import config_impressora
        import importlib
        importlib.reload(config_impressora)
        
        centro_x = (config_impressora.mesa_x_min + config_impressora.mesa_x_max) / 2.0
        centro_y = (config_impressora.mesa_y_min + config_impressora.mesa_y_max) / 2.0
        
        # Parâmetros padrão base
        self.config = {
            'x_centro': centro_x,
            'y_centro': centro_y,
            'z_max_desejado': 10.0,
            'angulo_parede': 90.0,
            'zonas_camadas': [{
                'qtd_camadas': 999,
                'num_perimetros': 1,
                'infill_percent': 100.0,
                'infill_pattern': 'concentric'
            }],
            'angulo_infill_base': 45.0,
            'sobreposicao_infill': 0.5,
            'amplitude_gyroid': 2.0,
            'comprimento_onda_gyroid': 15.0
        }
        
        if tipo == 'cilindro':
            self.config['raio_cilindro'] = 20.0
        elif tipo == 'prisma':
            self.config['largura_x'] = 30.0
            self.config['comprimento_y'] = 30.0
        elif tipo == 'bridging':
            self.config['comprimento_braco'] = 80.0
            self.config['angulo_abertura'] = 45.0
            self.config['espacamento_bridging'] = 4.0
            self.config['num_camadas_base'] = 4
            self.config['num_perimetros'] = 4
            self.config['velocidade_base'] = 20.0
            self.config['velocidade_ponte'] = 10.0
            self.config['ancora_pausa_ms'] = 500

    def to_dict(self):
        return {
            'id': self.id,
            'tipo': self.tipo,
            'nome': self.nome,
            'config': self.config
        }

    @classmethod
    def from_dict(cls, data):
        p = cls(data['tipo'])
        p.id = data['id']
        p.nome = data['nome']
        p.config = data['config']
        # Update class counter to avoid future id collisions
        if p.id >= cls._id_counter:
            cls._id_counter = p.id + 1
        return p

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
        self.left_panel.grid_rowconfigure(3, weight=1)
        
        # Botões de Sessão
        self.frame_sessao = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.frame_sessao.grid(row=0, column=0, padx=10, pady=(15, 0), sticky="ew")
        
        self.btn_salvar_sessao = ctk.CTkButton(self.frame_sessao, text="Salvar Sessão", width=105, fg_color="#1E3A8A", hover_color="#1E40AF", command=self.salvar_sessao)
        self.btn_salvar_sessao.pack(side="left", padx=2)
        
        self.btn_carregar_sessao = ctk.CTkButton(self.frame_sessao, text="Carregar Sessão", width=105, fg_color="#1E3A8A", hover_color="#1E40AF", command=self.carregar_sessao)
        self.btn_carregar_sessao.pack(side="right", padx=2)
        
        self.lbl_fila = ctk.CTkLabel(self.left_panel, text="Fila de Impressão", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_fila.grid(row=1, column=0, padx=20, pady=(15, 10))

        # Botões para adicionar
        self.frame_botoes_add = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.frame_botoes_add.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        
        self.btn_add_cilindro = ctk.CTkButton(self.frame_botoes_add, text="+ Cilindro", width=65, command=lambda: self.adicionar_peca('cilindro'))
        self.btn_add_cilindro.pack(side="left", padx=2)
        
        self.btn_add_prisma = ctk.CTkButton(self.frame_botoes_add, text="+ Prisma", width=65, command=lambda: self.adicionar_peca('prisma'))
        self.btn_add_prisma.pack(side="left", padx=2)
        
        self.btn_add_bridging = ctk.CTkButton(self.frame_botoes_add, text="+ Bridging", width=65, command=lambda: self.adicionar_peca('bridging'))
        self.btn_add_bridging.pack(side="left", padx=2)
        
        self.btn_add_vetor = ctk.CTkButton(self.frame_botoes_add, text="+ Vetor", width=65, command=lambda: self.adicionar_peca('vetor'))
        self.btn_add_vetor.pack(side="left", padx=2)

        # Lista de peças (Scrollable)
        self.lista_pecas_frame = ctk.CTkScrollableFrame(self.left_panel)
        self.lista_pecas_frame.grid(row=3, column=0, padx=10, pady=10, sticky="nsew")
        
        # Nome do Arquivo
        self.frame_arquivo = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.frame_arquivo.grid(row=4, column=0, padx=20, pady=(10, 0), sticky="ew")
        self.lbl_filename = ctk.CTkLabel(self.frame_arquivo, text="Nome do Arquivo G-code:")
        self.lbl_filename.pack(pady=(15,0))
        self.txt_nome_arquivo = ctk.CTkEntry(self.frame_arquivo, width=200, placeholder_text="Digite o nome do G-code")
        self.txt_nome_arquivo.pack(pady=(0,10))
        
        # Botões de Ação Final
        self.frame_acoes = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.frame_acoes.grid(row=5, column=0, padx=20, pady=20, sticky="ew")
        
        self.btn_config_global = ctk.CTkButton(self.frame_acoes, text="Configurações Globais de Impressão", fg_color="gray40", hover_color="gray30", height=30, command=self.abrir_config_global)
        self.btn_config_global.pack(fill="x", pady=5)
        
        self.btn_duplicar = ctk.CTkButton(self.frame_acoes, text="Duplicar Peça Selecionada", fg_color="goldenrod", hover_color="darkgoldenrod", height=30, command=self.duplicar_peca_ui)
        self.btn_duplicar.pack(fill="x", pady=(15,5))

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

    def salvar_sessao(self):
        import json
        import os
        
        # Garante que as edições atuais do painel direito sejam salvas no objeto antes de exportar
        self.salvar_inputs_na_peca_selecionada()
        
        filepath = ctk.filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("Arquivos de Sessão JSON", "*.json")],
            title="Salvar Sessão da Fila de Impressão"
        )
        if not filepath:
            return
            
        dados = {
            'nome_gcode': self.txt_nome_arquivo.get(),
            'fila': [p.to_dict() for p in self.pecas_fila]
        }
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(dados, f, indent=4)
            messagebox.showinfo("Sucesso", "Sessão salva com sucesso!")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar a sessão:\n{e}")

    def carregar_sessao(self):
        import json
        
        filepath = ctk.filedialog.askopenfilename(
            filetypes=[("Arquivos de Sessão JSON", "*.json")],
            title="Carregar Sessão da Fila de Impressão"
        )
        if not filepath:
            return
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                dados = json.load(f)
                
            self.txt_nome_arquivo.delete(0, 'end')
            self.txt_nome_arquivo.insert(0, dados.get('nome_gcode', ''))
            
            self.pecas_fila = [Piece.from_dict(d) for d in dados.get('fila', [])]
            self.peca_selecionada = None
            self.limpar_painel_direito()
            self.atualizar_lista_ui()
            
            messagebox.showinfo("Sucesso", "Sessão carregada com sucesso!")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao carregar a sessão:\n{e}")

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

    def duplicar_peca_ui(self):
        if not self.peca_selecionada:
            return
        
        import copy
        nova = copy.deepcopy(self.peca_selecionada)
        nova.id = Piece._id_counter
        Piece._id_counter += 1
        nova.nome = nova.nome.split('(')[0].strip() + f" (Cópia {nova.id})"
        self.pecas_fila.append(nova)
        self.selecionar_peca(nova)
        self.atualizar_lista_ui()

    def mover_peca_cima(self, peca):
        idx = self.pecas_fila.index(peca)
        if idx > 0:
            self.pecas_fila[idx - 1], self.pecas_fila[idx] = self.pecas_fila[idx], self.pecas_fila[idx - 1]
            self.atualizar_lista_ui()

    def mover_peca_baixo(self, peca):
        idx = self.pecas_fila.index(peca)
        if idx < len(self.pecas_fila) - 1:
            self.pecas_fila[idx + 1], self.pecas_fila[idx] = self.pecas_fila[idx], self.pecas_fila[idx + 1]
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
            
            btn_remover = ctk.CTkButton(row_frame, text="X", width=30, fg_color="red", hover_color="darkred", command=lambda p=peca: self.remover_peca(p))
            btn_remover.pack(side="right", padx=(2, 5))
            
            btn_down = ctk.CTkButton(row_frame, text="▼", width=30, fg_color="gray40", command=lambda p=peca: self.mover_peca_baixo(p))
            btn_down.pack(side="right", padx=2)
            
            btn_up = ctk.CTkButton(row_frame, text="▲", width=30, fg_color="gray40", command=lambda p=peca: self.mover_peca_cima(p))
            btn_up.pack(side="right", padx=2)
            
            btn_nome = ctk.CTkButton(row_frame, text=peca.nome, fg_color="transparent", anchor="w", command=lambda p=peca: self.selecionar_peca(p))
            btn_nome.pack(side="left", fill="x", expand=True, padx=5)

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
                    try:
                        val_num = float(val)
                    except ValueError:
                        if val == "True":
                            val_num = True
                        elif val == "False":
                            val_num = False
                        else:
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
            
        def add_file_input(label_text, key_name, default_val):
            nonlocal row_idx
            lbl = ctk.CTkLabel(self.frame_inputs, text=label_text)
            lbl.grid(row=row_idx, column=0, padx=10, pady=10, sticky="e")
            
            var = ctk.StringVar(value=str(default_val))
            self.inputs_vars[key_name] = var
            
            frame_file = ctk.CTkFrame(self.frame_inputs, fg_color="transparent")
            frame_file.grid(row=row_idx, column=1, padx=10, pady=10, sticky="w")
            
            entry = ctk.CTkEntry(frame_file, textvariable=var, width=140)
            entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
            
            def open_dialog():
                filepath = ctk.filedialog.askopenfilename(
                    title="Selecione o Vetor",
                    filetypes=[("Arquivos Vetoriais", "*.svg *.dxf"), ("Todos os Arquivos", "*.*")]
                )
                if filepath:
                    var.set(filepath)
                    
            btn = ctk.CTkButton(frame_file, text="Procurar", width=55, command=open_dialog)
            btn.pack(side="left")
            
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
        elif self.peca_selecionada.tipo == 'bridging':
            add_input("Compr. do Braço (mm):", "comprimento_braco", self.peca_selecionada.config.get('comprimento_braco', 80.0))
            add_input("Ângulo de Abertura (º):", "angulo_abertura", self.peca_selecionada.config.get('angulo_abertura', 45.0))
            add_input("Espaçamento Pontes (mm):", "espacamento_bridging", self.peca_selecionada.config.get('espacamento_bridging', 4.0))
            add_input("Num. Camadas Base:", "num_camadas_base", self.peca_selecionada.config.get('num_camadas_base', 4))
            add_input("Num. Perímetros Base:", "num_perimetros", self.peca_selecionada.config.get('num_perimetros', 4))
            add_input("Velocidade Base (mm/s):", "velocidade_base", self.peca_selecionada.config.get('velocidade_base', 20.0))
            add_input("Vel. Ponte (mm/s):", "velocidade_ponte", self.peca_selecionada.config.get('velocidade_ponte', 10.0))
            add_input("Pausa na Âncora (ms):", "ancora_pausa_ms", self.peca_selecionada.config.get('ancora_pausa_ms', 500))
        elif self.peca_selecionada.tipo == 'vetor':
            add_file_input("Arquivo Vetor (SVG/DXF):", "vetor_arquivo", self.peca_selecionada.config.get('vetor_arquivo', 'no-celta.dxf'))
            add_combobox("Modo Linha Única:", "modo_linha_unica", str(self.peca_selecionada.config.get('modo_linha_unica', 'True')), ["True", "False"])
            add_input("Num. Camadas Base Maciça:", "num_camadas_base_macica", self.peca_selecionada.config.get('num_camadas_base_macica', 4))
            add_input("Largura X Desejada (mm):", "largura_x", self.peca_selecionada.config.get('largura_x', 100.0))

        if self.peca_selecionada.tipo in ['cilindro', 'prisma', 'vetor']:
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
            
            lbl_sep4 = ctk.CTkLabel(self.frame_inputs, text="--- Infill Específicos ---", text_color="gray")
            lbl_sep4.grid(row=row_idx, column=0, columnspan=2, pady=(15, 5)); row_idx += 1
            
            add_input("Ângulo Infill Base (º):", "angulo_infill_base", self.peca_selecionada.config.get('angulo_infill_base', 45.0))
            add_input("Sobreposição Infill (mm):", "sobreposicao_infill", self.peca_selecionada.config.get('sobreposicao_infill', 0.5))
            add_input("Amplitude Gyroid:", "amplitude_gyroid", self.peca_selecionada.config.get('amplitude_gyroid', 2.0))
            add_input("Comp. Onda Gyroid:", "comprimento_onda_gyroid", self.peca_selecionada.config.get('comprimento_onda_gyroid', 15.0))
            
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
            'priming_inicial_vel': 'Carga Inicial: Velocidade (mm/s)',
            'priming_inicio_perimetro': 'Perímetro: Ativar Purga no Início',
            'priming_perimetro_inicio_qtd': 'Perímetro Início: Quantidade (mm)',
            'priming_perimetro_inicio_vel': 'Perímetro Início: Velocidade (mm/s)',
            'priming_fim_perimetro': 'Perímetro: Ativar Retração no Fim',
            'priming_perimetro_fim_qtd': 'Perímetro Fim: Retração (mm)',
            'priming_perimetro_fim_vel': 'Perímetro Fim: Velocidade (mm/s)',
            'priming_inicio_infill': 'Infill: Ativar Purga no Início',
            'priming_infill_inicio_qtd': 'Infill Início: Quantidade (mm)',
            'priming_infill_inicio_vel': 'Infill Início: Velocidade (mm/s)',
            'priming_fim_infill': 'Infill: Ativar Retração no Fim',
            'priming_infill_fim_qtd': 'Infill Fim: Retração (mm)',
            'priming_infill_fim_vel': 'Infill Fim: Velocidade (mm/s)',
            'wipe_final_ativo': 'Wipe Final: Ativar Arrasto',
            'wipe_final_distancia': 'Wipe Final: Distância (mm)',
            'wipe_final_subida_z': 'Wipe Final: Subida em Z (mm)',
            'transicao_vaso_z_offset': 'Vasemode: Offset Z de Transição (mm)',
            'transicao_vaso_fluxo': 'Vasemode: Fluxo de Transição (%)',
            'mesa_x_min': 'Mesa: Limite Min X (mm)',
            'mesa_x_max': 'Mesa: Limite Max X (mm)',
            'mesa_y_min': 'Mesa: Limite Min Y (mm)',
            'mesa_y_max': 'Mesa: Limite Max Y (mm)',
            'resolucao_mm': 'Cinemática: Resolução Curvas (mm)',
            'fluxo_perimetro': 'Fluxo: Perímetro (%)',
            'fluxo_infill': 'Fluxo: Infill (%)',
            'velocidade_primeira_camada': 'Cinemática: Vel. Primeira Camada (mm/s)',
            'aceleracao_primeira_camada': 'Cinemática: Acc. Primeira Camada (mm/s²)',
            'velocidade_impressao': 'Cinemática: Velocidade Impressão (mm/s)',
            'aceleracao_impressao': 'Cinemática: Aceleração Impressão (mm/s²)',
            'velocidade_travel': 'Cinemática: Velocidade Travel (mm/s)',
            'alternar_ordem_camadas': 'Especial: Alternar Sentido Z'
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
                    
        # --- Campos para Start e End G-Code ---
        lbl_sg = ctk.CTkLabel(scroll, text="Start G-Code Personalizado", font=ctk.CTkFont(weight="bold"))
        lbl_sg.grid(row=row_idx, column=0, columnspan=2, pady=(15, 5))
        row_idx += 1
        
        self.txt_start_gcode = ctk.CTkTextbox(scroll, height=100)
        self.txt_start_gcode.grid(row=row_idx, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        try:
            import sys
            import os
            # Adiciona local module path to ensure import
            fc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fullcontrol")
            if fc_path not in sys.path:
                sys.path.insert(0, fc_path)
            from fullcontrol.devices.community_minimal.settings import cliever_cl2pro
            importlib.reload(cliever_cl2pro)
            start_txt = cliever_cl2pro.default_initial_settings.get("start_gcode", "")
            self.txt_start_gcode.insert("0.0", start_txt)
        except Exception as e:
            print("Erro ao carregar perfil da impressora", e)
        row_idx += 1
        
        lbl_eg = ctk.CTkLabel(scroll, text="End G-Code Personalizado", font=ctk.CTkFont(weight="bold"))
        lbl_eg.grid(row=row_idx, column=0, columnspan=2, pady=(15, 5))
        row_idx += 1
        
        self.txt_end_gcode = ctk.CTkTextbox(scroll, height=100)
        self.txt_end_gcode.grid(row=row_idx, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        try:
            from fullcontrol.devices.community_minimal.settings import cliever_cl2pro
            end_txt = cliever_cl2pro.default_initial_settings.get("end_gcode", "")
            self.txt_end_gcode.insert("0.0", end_txt)
        except: pass
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
            
            # Salva o Start e End G-code diretamente no perfil da biblioteca FullControl
            try:
                import os
                perfil_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fullcontrol", "devices", "community_minimal", "settings", "cliever_cl2pro.py")
                start_txt = self.txt_start_gcode.get("0.0", "end").strip()
                end_txt = self.txt_end_gcode.get("0.0", "end").strip()
                
                novo_perfil = f'''default_initial_settings = {{
    "name": "Cliever CL2Pro",
    "start_gcode": """{start_txt}""",
    "end_gcode": """{end_txt}"""
}}
'''
                with open(perfil_path, "w", encoding="utf-8") as f:
                    f.write(novo_perfil)
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao salvar Gcode customizado no perfil do FullControl: {e}")
            
            messagebox.showinfo("Sucesso", "Configurações Globais e G-Code inicial/final salvos com sucesso!")
            self.config_window.destroy()
            
        except Exception as e:
            messagebox.showerror("Erro Crítico", f"Falha ao salvar config_impressora.py:\n{str(e)}")

    def gerar_gcode(self):
        self.salvar_inputs_na_peca_selecionada()
        self.atualizar_lista_ui()
        
        if len(self.pecas_fila) == 0:
            messagebox.showwarning("Fila Vazia", "Adicione pelo menos uma peça à fila antes de gerar o G-Code.")
            return
            
        import os
        nome_arquivo = self.txt_nome_arquivo.get().strip()
        if not nome_arquivo:
            messagebox.showerror("Erro", "O nome do arquivo G-code não pode estar em branco.")
            return
            
        if not nome_arquivo.endswith('.gcode'):
            nome_arquivo += '.gcode'
            
        # Garante que salva na pasta gcode
        gcode_dir = "gcode"
        if not os.path.exists(gcode_dir):
            os.makedirs(gcode_dir)
            
        caminho_completo = os.path.join(gcode_dir, nome_arquivo)
            
        # Garante que os módulos tenham a config mais atual antes de rodar
        importlib.reload(config_impressora)
        importlib.reload(motor_mestre)
        importlib.reload(cilindro_inclinado)
        importlib.reload(prisma_inclinado)
        importlib.reload(bridging_teste)
        
        # Chama o motor mestre!
        try:
            sucesso, mensagem = motor_mestre.gerar_gcode_sequencial(self.pecas_fila, nome_arquivo=caminho_completo)
            
            if sucesso:
                messagebox.showinfo("Sucesso", mensagem)
            else:
                messagebox.showerror("Erro de Geração", mensagem)
        except Exception as e:
            messagebox.showerror("Erro", str(e))

if __name__ == "__main__":
    app = PrintQueueApp()
    app.mainloop()

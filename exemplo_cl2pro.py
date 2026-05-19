import fullcontrol as fc

# Exemplo de design de caminho simples (um quadrado 100x100)
steps = []
steps.append(fc.Point(x=100, y=100, z=0.2))
steps.append(fc.Point(x=200, y=100, z=0.2))
steps.append(fc.Point(x=200, y=200, z=0.2))
steps.append(fc.Point(x=100, y=200, z=0.2))
steps.append(fc.Point(x=100, y=100, z=0.2))

# Gerando o G-code utilizando o seu novo perfil de impressora
# Observe o prefixo 'Community/' que é necessário para impressoras do diretório community_minimal
gcode = fc.transform(steps, 'gcode', fc.GcodeControls(
    printer_name='Community/Cliever CL2Pro', 
    save_as='teste_cl2pro'
))

print("Gcode gerado com sucesso!")

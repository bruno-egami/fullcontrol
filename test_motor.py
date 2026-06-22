import motor_mestre
from gui import Piece

p = Piece('cilindro')
print("Chamando gerar_gcode_sequencial...")
sucesso, msg = motor_mestre.gerar_gcode_sequencial([p], "test_output")
print("Resultado:", sucesso)
print("Msg:", msg)

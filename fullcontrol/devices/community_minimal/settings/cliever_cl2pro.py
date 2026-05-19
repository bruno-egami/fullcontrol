default_initial_settings = {
    "name": "Cliever CL2Pro",
    "start_gcode": """;STARTGCODE
M106 S128
G90 ; use absolute coordinates
M83 ; extruder relative mode
M200 D0 ; disable volumetric E
M220 S100 ; reset speed
G28 ; home all axes""",
    "end_gcode": """;ENDGCODE
G92 E0.0
G91          ; Altera a impressora para o modo de coordenadas relativas.
G1 Z10 F500  ; Move o eixo Z 10mm para cima a partir da posição atual (Velocidade: 20mm/s).
G90          ; Retorna a impressora para o modo de coordenadas absolutas (MUITO IMPORTANTE).
M84          ; desliga motores
M300 P200    ; Bip final
M107         ; desliga fan
M117 Print finish."""
}

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
G91          ; Modo relativo
G1 Z10 F500  ; Sobe Z 10mm
G90          ; Modo absoluto
M84          ; Desliga motores
M300 P200    ; Bip final
M107         ; Desliga fan
M117 Print finish.
G28 ; homing"""
}

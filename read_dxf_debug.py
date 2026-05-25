import sys
import ezdxf
from ezdxf.path import make_path

def debug_dxf_path(filepath):
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    
    for entity in msp:
        t = entity.dxftype()
        print(f"Entidade: {t}")
        if t in ('LWPOLYLINE', 'POLYLINE'):
            # Obter bulges
            bulges = [v[4] if len(v) > 4 else 0.0 for v in entity.get_points()]
            print(f"Vértices puros (get_points): {len(entity.get_points())}")
            print(f"Bulges: {bulges}")
            
            # Usar make_path
            path = make_path(entity)
            pts_flat = list(path.flattening(distance=1.0))
            print(f"Número de pontos gerados via make_path.flattening: {len(pts_flat)}")
            print("Primeiros 10 pontos:")
            for i, p in enumerate(pts_flat[:10]):
                print(f"  Ponto {i}: ({p.x:.4f}, {p.y:.4f})")

debug_dxf_path("no-celta.dxf")

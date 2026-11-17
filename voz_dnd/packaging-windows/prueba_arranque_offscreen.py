"""Verificación offscreen: construye la ventana principal de voz_dnd igual
que main.py (fase de construcción de UI incluida). Caza bugs de orden como
el de boton_ia_instalar."""
import os, sys, traceback
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, "/home/z/cambiadorVozDM/voz_dnd")
from PyQt6.QtWidgets import QApplication

fallo = None
try:
    from app.gui.main_window import VentanaPrincipal
    app = QApplication(sys.argv)
    ventana = VentanaPrincipal()
    ventana.show()
    # La pestaña Ajustes es la que reventaba: accedemos a sus piezas
    ajustes = ventana.pestana_ajustes
    assert ajustes.boton_ia_instalar is not None
    texto = ajustes.etiqueta_motores.text()
    print("etiqueta_motores:", repr(texto[:60]))
    print("boton visible:", ajustes.boton_ia_instalar.isVisible())
    ventana.close()
except Exception:
    fallo = traceback.format_exc()

if fallo:
    print("FALLO DE ARRANQUE:\n", fallo)
    sys.exit(1)
print("VENTANA OK — construcción de UI completa sin errores")

# MVP: control de presentaciones de Canva con gestos

## Avance de implementación

- Entorno Python 3.12.3 y 28 dependencias instaladas; `uv pip check` correcto.
- README y CLI `python -m gesto` disponibles.
- Etapa 1: prueba aislada de teclado implementada y validada con Canva en
  Chromium bajo X11/XWayland. El navegador Wayland nativo sigue fuera del
  alcance de este adaptador de teclado.
- Etapa 2: modelo oficial descargado y verificado con SHA-256; captura y dibujo
  implementados. Inferencia VIDEO comprobada con tres fotogramas sintéticos.
  Pendiente la prueba con una mano real: esta sesión no expone una cámara.
- Etapa 3: detector temporal e integración visual en `python -m gesto simulate`
  implementados. Incluye suavizado dependiente del tiempo, estados, pausa, rearme,
  descarte por pérdida/cambio de mano y por interrupciones del muestreo.
  Validación con trayectorias sintéticas; pendiente calibración con mano real.
- Validación actual: 80 pruebas automatizadas aprobadas, incluida la integración
  de video simulado con el detector sin teclado y la ventana flotante sin foco.
  Inferencia real sobre tres fotogramas negros sin gestos; resultados completos
  guardados en `log/`.
- Registros de consola y errores en `log/` para la CLI y el ejecutor de pruebas;
  incluyen comando, fecha, duración y código de salida.
- La integración automática con Canva ya envía teclas y reconoce ambos sentidos
  en Chromium/X11. Falta la medición manual de precisión, acciones dobles,
  inactividad y latencia para cerrar la validación del MVP.

## Objetivo y alcance

Controlar una presentación de Canva abierta en el navegador mediante la cámara de
la computadora. Una mano se desplaza hacia la izquierda del usuario para avanzar;
hacia la derecha para retroceder. Cada gesto debe producir como máximo un cambio.

Primera versión: aplicación local de escritorio en Python, una cámara y una mano,
con vista de diagnóstico opcional, calibración básica y modo de simulación.
El usuario abre Canva, inicia la presentación y enfoca su ventana manualmente.
No requiere entrenar un modelo, integrar la API de Canva ni desarrollar una web.
Quedan fuera: Google Slides, galería, múltiples usuarios, instalador y soporte
general de todos los escritorios y navegadores.

## Entorno y dependencias

- Verificado en este directorio: `.venv/bin/python` ejecuta Python **3.12.3**.
- `.python-version` selecciona la rama 3.12 para uv; al recrear el entorno,
  usar `uv venv --python 3.12`.
- MediaPipe Tasks / Hand Landmarker: landmarks y seguimiento de una mano.
- OpenCV (`opencv-contrib-python`, requerido también por MediaPipe): captura de
  video, conversión BGR a RGB y visualización de diagnóstico.
- NumPy: operaciones sobre posiciones y trayectorias.
- PyAutoGUI: envío de teclas al programa enfocado, sujeto a la validación del
  escritorio descrita abajo.
- Biblioteca estándar: configuración con `tomllib`, argumentos, logs, historial
  con `collections.deque` y reloj monótono. No agregar frameworks de interfaz.

`requirements.in` declara dependencias directas. `requirements.txt` es el archivo
para instalación; si se genera con uv pip compile, fija también las transitivas.
Mantener una sola distribución de OpenCV: se eligió `opencv-contrib-python`
porque MediaPipe la requiere. No agregar `opencv-python` ni variantes headless:
comparten el módulo `cv2`.

El modelo preentrenado `hand_landmarker.task` es un recurso adicional, no una
dependencia de pip. En la etapa de detección se descargará desde la documentación
oficial, se registrarán origen y checksum y se guardará en `models/`.

## Diseño propuesto

Flujo: cámara → fotogramas RGB → Hand Landmarker → estado temporal de posiciones →
detector de desplazamiento → acción avanzar/retroceder → adaptador de teclado.

Separar captura, detección, interpretación de gestos y envío de teclas para poder
probar las trayectorias sin cámara ni Canva. La interfaz de salida recibirá
acciones semánticas; la elección de tecla queda dentro del adaptador.

Usar inicialmente el modo VIDEO de Hand Landmarker con timestamps monótonos
crecientes. Procesar secuencialmente simplifica el primer prototipo. Evaluar
LIVE_STREAM y su callback solo si las mediciones de rendimiento lo justifican.

## Etapas y entregables

### 1. Validar el control de Canva antes de la visión

El entorno actual informa Linux con sesión **Wayland**. PyAutoGUI usa X11 en
Linux; tener DISPLAY definido no demuestra compatibilidad con el navegador.

- Abrir una presentación de prueba de al menos cinco páginas, en modo manual.
- Comprobar con el teclado físico las teclas para avanzar y retroceder; propuesta
  inicial: flecha derecha e izquierda, respectivamente.
- En la implementación, realizar una prueba mínima de envío de una sola tecla,
  con cuenta regresiva para enfocar Canva.
- Si falla bajo Wayland, validar una sesión X11 disponible o el navegador bajo
  XWayland. No modificar la sesión ni instalar componentes del sistema sin acordarlo.
- Si se necesita mantener un navegador Wayland nativo, revisar el adaptador de
  entrada antes de continuar; no prometer soporte con PyAutoGUI.

Salida: combinación de escritorio/navegador validada y teclas confirmadas.

### 2. Capturar video y detectar una mano

- Instalar dependencias, verificar imports y descargar el modelo oficial.
- Abrir la cámara con índice configurable; comenzar en 640 × 480.
- Configurar una sola mano y confianzas iniciales de 0.6, ajustables.
- Mostrar landmarks, estado de detección y FPS en modo de diagnóstico.
- Liberar cámara y ventanas al salir; informar claramente errores de cámara o modelo.

Salida: seguimiento estable durante dos minutos en iluminación normal.

### 3. Reconocer desplazamientos en modo de simulación

- Tomar como centro de palma el promedio de muñeca y bases de los dedos.
- Definir una coordenada horizontal coherente con la vista espejo: izquierda y
  derecha siempre desde la perspectiva del usuario; verificar ambos sentidos.
- Suavizar posiciones y mantener referencias temporales del inicio del movimiento,
  la estabilidad y la pausa. La implementación guarda anclas y timestamps con
  memoria constante; no depende de una cantidad fija de fotogramas.
- Parámetros iniciales para calibrar: desplazamiento horizontal mínimo de 20 %
  del ancho de imagen en 150–700 ms y movimiento horizontal mayor que el vertical.
- Usar estados: sin mano → listo → seguimiento → gesto emitido → espera → rearme.
- Tras emitir un gesto, aplicar una pausa inicial de 800 ms y exigir mano estable
  durante 300 ms antes de iniciar otra trayectoria. Ignorar el movimiento de
  retorno mientras no se haya rearmado.
- Al perder la mano, descartar el historial; al recuperarla, exigir estabilidad
  antes de volver a detectar. No unir trayectorias de manos diferentes.
- Registrar avanzar/retroceder sin enviar teclas y mostrar el estado de rearme.

Salida: distinguir barridos voluntarios de temblores, movimiento vertical y retorno.
Los umbrales son hipótesis del prototipo, no valores de precisión garantizada.

### 4. Integrar gestos y presentación

- Mapear barrido izquierdo a avanzar y derecho a retroceder.
- Enviar una pulsación por acción y conservar el foco en Canva; la vista de
  diagnóstico no debe recuperar el foco durante la presentación.
- Iniciar pausado; habilitar mediante cuenta regresiva para enfocar Canva.
- Incorporar una pausa accesible sin enfocar la ventana de OpenCV: propuesta,
  mantener puño cerrado un segundo y exigir soltarlo para repetir el comando.
- Mantener salida por Ctrl+C en terminal y fail-safe de PyAutoGUI. La tecla de
  cierre de OpenCV solo funcionará cuando esa ventana tenga el foco.
- Guardar umbrales, índice de cámara, espejo y teclas en configuración TOML.

Salida: demostración completa con Canva y ajuste de sensibilidad documentado.

### 5. Verificar y documentar

- Pruebas unitarias de trayectorias sintéticas: izquierda, derecha, ruido,
  movimiento vertical, retorno, pérdida de mano y timestamps irregulares.
- Verificar con salida simulada que cada gesto produce una sola acción.
- Prueba manual: 20 barridos por dirección; objetivo inicial, al menos 18 de 20
  correctos por dirección y ningún doble cambio.
- Dos minutos con mano quieta o ausente: objetivo, ningún cambio accidental.
- Medir latencia desde reconocimiento hasta envío de tecla: objetivo menor a
  150 ms. Registrar aparte la duración del gesto y la respuesta visual de Canva.
- Verificar pausa, reanudación, pérdida de cámara y salida limpia.
- Documentar instalación, modelo, ejecución, calibración y escritorio compatible.

Salida: MVP utilizable con resultados medidos y limitaciones explícitas.

## Aprendizaje enfocado para Python intermedio

1. OpenCV: ciclo de captura, RGB/BGR y recursos de cámara.
2. MediaPipe Tasks: landmarks normalizados, tracking, modelo y timestamps.
3. Gestos dinámicos: suavizado, ventanas temporales y máquina de estados.
4. Automatización: foco de ventanas y diferencias entre X11 y Wayland.
5. Validación: trayectorias sintéticas y medición de errores y latencia.

## Fuentes técnicas

- Hand Landmarker y modos de ejecución:
  https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/python
- Distribuciones y compatibilidad de MediaPipe: https://pypi.org/project/mediapipe/
- Selección de una sola variante OpenCV: https://pypi.org/project/opencv-python/
- PyAutoGUI, funcionamiento en Linux: https://github.com/asweigart/pyautogui
- Teclas enviadas a la ventana enfocada: https://pypi.org/project/PyAutoGUI/
- Presentaciones de Canva: https://www.canva.com/help/presenting-designs/

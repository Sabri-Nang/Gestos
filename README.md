# Gesto

Aplicación local en Python para controlar presentaciones de **Canva** con gestos
de la mano capturados por la cámara de la computadora. Usa **MediaPipe Tasks**
para localizar la mano y OpenCV para capturar y visualizar el video.

El comportamiento del MVP es desplazar la mano hacia la izquierda para
avanzar y hacia la derecha para retroceder, desde la perspectiva del usuario.
Cada gesto deberá producir un único cambio de diapositiva.

## Estado actual

Están implementados el diagnóstico, la simulación y el control de presentación:

- Diagnóstico de versiones, sesión gráfica y modelo.
- Descarga del modelo oficial con comprobación SHA-256.
- Prueba aislada de teclado, simulada por defecto y con envío real opcional.
- Captura de una cámara, seguimiento de una mano, landmarks y FPS en pantalla.
- Detector temporal de barridos izquierdo/derecho, con suavizado, pausa y rearme.
- Simulación con acciones y cambios de estado registrados en `log/`.
- Modo presentación: pulsaciones de teclado, inicio pausado, cuenta regresiva y
  pausa por puño sostenido sin cambiar el foco de Canva.
- Configuración de cámara, gestos, tiempos y teclas mediante `gesto.toml`.

La simulación ya fue probada por el usuario y mejoró con los ajustes de umbral
y recuperación de pérdidas breves. El modo presentación está verificado con
teclado simulado. El usuario confirmó el envío programático y los barridos en
Canva usando Chromium con el perfil X11. La detección todavía requiere ajustar
la continuidad del seguimiento y completar las mediciones de precisión.
Los comandos `camera` y `simulate` no envían teclas.

## Requisitos e instalación

- Python **3.12** y `uv`. El entorno de desarrollo se verificó con Python 3.12.3.
- Cámara y sesión gráfica para el diagnóstico visual.
- Canva abierto en modo presentación manual para probar la navegación.
- En Linux, validar X11/XWayland para el envío mediante PyAutoGUI. Bajo Wayland
  nativo no se garantiza que el navegador reciba las teclas.
- En Ubuntu con Python del sistema: `sudo apt-get install python3-tk`. MouseInfo,
  importado por PyAutoGUI, necesita Tkinter incluso cuando solo se envían teclas.
  Este componente del sistema no se instala mediante `requirements.txt`.

Desde el directorio del proyecto:

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
python -m gesto download-model
python -m gesto doctor
```

Si `.venv` ya existe y las dependencias están instaladas, comenzá por activarlo.
En entornos restringidos que no permitan escribir la caché habitual de uv, usá
`uv --cache-dir /tmp/gesto-uv-cache pip install -r requirements.txt`.

## Primer paso: validar Canva y el teclado

1. Abrí una presentación de prueba de al menos cinco páginas en Canva, en modo
   presentación manual, y comprobá las flechas físicas del teclado.
2. Ejecutá una simulación; no envía teclas ni necesita conexión al escritorio:

   ```bash
   python -m gesto keyboard-test --action next
   ```

3. Para la prueba real, ejecutá el comando y enfocá Canva durante la cuenta
   regresiva de cinco segundos:

   ```bash
   python -m gesto keyboard-test --action next --send
   python -m gesto keyboard-test --action previous --send
   ```

Ejecutá los comandos uno por vez. `next` envía flecha derecha y `previous` envía
flecha izquierda; confirmá visualmente el resultado. La tecla llega a la ventana
que tenga el foco. La prueba envía una sola pulsación y termina. El fail-safe de
PyAutoGUI permanece activo.

La sesión detectada durante el desarrollo es Wayland. Si Canva no responde,
verificá una sesión X11 disponible o un navegador bajo XWayland antes de conectar
el reconocimiento de gestos. No se modifica la configuración del escritorio.

Si PyAutoGUI falla antes de la cuenta regresiva, ejecutá desde la misma terminal
gráfica donde vas a usar Canva:

```bash
python -m gesto doctor --keyboard
```

Este diagnóstico comprueba la inicialización sin enviar teclas ni mover el mouse.
El registro conserva la excepción original para distinguir dependencias faltantes
de problemas de autorización o conexión a X11. Que la importación funcione todavía
no confirma la recepción de teclas en un navegador Wayland nativo.

La dependencia `python3-xlib` 0.15 no reconoce las entradas de autorización cuyo
número de pantalla está vacío, presentes en algunas sesiones Mutter/XWayland.
Gesto aplica en memoria la compatibilidad de [python-xlib mantenido](https://github.com/python-xlib/python-xlib/blob/master/Xlib/xauth.py),
usando una credencial existente solo si coinciden familia, host y protocolo.
No modifica archivos de autorización ni políticas de acceso del servidor X11.

Si el log muestra `[TECLA]` pero Canva no cambia, comprobá el destino del envío:

```bash
python -m gesto keyboard-test --focus-only --countdown 10
```

Durante esos diez segundos volvé a Canva mediante Alt+Tab, sin hacer clic sobre
la diapositiva. La línea `[FOCO]` identifica la aplicación que tiene el foco X11,
o informa que no hay ventana X11 enfocada. En una sesión Wayland, ese último
resultado puede indicar que el navegador es nativo Wayland; no confirma por sí
solo la causa. La prueba no envía teclas, abre cámaras ni modifica el foco.
Los envíos reales también registran `[FOCO]` inmediatamente antes de pulsar.
Solo se guarda la clase de aplicación y el identificador de ventana, no títulos
de documentos ni URLs.

### Probar Chromium en X11 desde una sesión Wayland

Si la ventana enfocada no se identifica y el envío no llega al navegador, podemos
probar el backend X11 explícito. El resultado de foco por sí solo no demuestra
que Chromium esté usando Wayland; este procedimiento permite comprobarlo.
Para la instalación Snap de Chromium detectada en este equipo:

```bash
chromium --ozone-platform=x11 --user-data-dir="$HOME/snap/chromium/common/gesto-x11" https://www.canva.com/
```

Este comando abre Chromium con un perfil separado y persistente para Gesto.
Será necesario iniciar sesión en Canva dentro de esa ventana. No cambia el
perfil habitual ni requiere cerrar la sesión de escritorio.

En esa ventana abrí la presentación. Desde otra terminal, con `.venv` activado,
ejecutá `python -m gesto keyboard-test --action next --send --countdown 10`.
Volvé a la ventana nueva con Alt+Tab y esperá el envío sin hacer clic. Si avanza,
probá `python -m gesto present --no-fist-control` sobre esa misma ventana.
El perfil y sus credenciales se guardan bajo `~/snap/chromium/common/gesto-x11`.

Referencias oficiales: [selección del backend Ozone](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/ozone_overview.md)
y [directorio de datos separado](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/user_data_dir.md).

## Segundo paso: cámara y detección de mano

```bash
python -m gesto camera
```

Mostrá una mano a la cámara. La ventana debe dibujar los 21 landmarks y mostrar
`Mano detectada` y los FPS. La vista se espeja por defecto. Probá durante dos
minutos, con iluminación normal, incluyendo momentos sin mano.

Opciones:

```bash
python -m gesto camera --camera 1
python -m gesto camera --no-mirror
python -m gesto camera --confidence 0.7
```

Salí con **Q**, **Esc** o el botón de cierre de la ventana. Q y Esc requieren
que la ventana de diagnóstico tenga el foco. También podés usar Ctrl+C en la
terminal. La aplicación libera la cámara al terminar.

Si falla la captura, revisá el índice, los permisos y que otra aplicación no esté
usando la cámara. Si falta el modelo, ejecutá `python -m gesto download-model`.
La captura y el diagnóstico no guardan imágenes ni envían fotogramas a Canva.

## Tercer paso: reconocer barridos en simulación

```bash
python -m gesto simulate
```

1. Mostrá una mano y mantenela quieta hasta que aparezca **LISTO**.
2. Desplazala hacia tu izquierda aproximadamente un tercio del ancho de la imagen
   en medio segundo. Debe aparecer **AVANZAR**.
3. Devolvé la mano a una posición cómoda durante **ESPERA** y mantenela quieta
   hasta volver a **LISTO**. Un barrido hacia tu derecha debe mostrar **RETROCEDER**.
4. Usá **P** para pausar o reanudar, y **Q** o **Esc** para salir, con la ventana
   enfocada. Al reanudar se exige estabilizar nuevamente la mano.

Las direcciones se mantienen aunque uses `--no-mirror`. Solo se imprimen acciones;
no hace falta abrir Canva. Las acciones, sus desplazamientos, duración y los
cambios de estado quedan en el registro de esa ejecución.

Para ajustar sensibilidad:

```bash
python -m gesto simulate --distance 0.18 --cooldown-ms 1000 --stable-ms 400
```

`--distance` es la fracción mínima del ancho de imagen recorrida por el centro
de la palma suavizado (0.10 en `gesto.toml`). Bajala para aceptar barridos más cortos;
subila si pequeños movimientos disparan acciones. `--cooldown-ms` define la pausa
tras cada acción (800 ms); `--stable-ms`, el tiempo de mano quieta para rearmar
(300 ms). El perfil actual admite entre 150 y 1000 ms y exige dominar el movimiento vertical.

La detección descarta trayectorias ante pérdidas prolongadas de la mano, cambios
confirmados de clasificación o más de 250 ms entre muestras. Un cambio de etiqueta
izquierda/derecha aislado se ignora si la palma sigue cerca; debe sostenerse
120 ms para reiniciar el gesto. Una palma lejana exige rearmar inmediatamente.
Esa clasificación es una ayuda de continuidad, no identificación de personas:
probá con una sola mano.
Los valores son iniciales y requieren calibración con tu cámara.

En el perfil actual, las pérdidas de hasta 180 ms pueden recuperarse si la misma mano
reaparece cerca. Durante ese intervalo se muestra **RECUPERANDO MANO** y no se
emiten acciones. Una ausencia más larga o una reaparición lejos reinicia el gesto.
La estabilización inicial requiere volver a observar la mano quieta.
Estos tiempos se configuran con `dropout_ms` y `hand_switch_ms` en `[gestures]`.
Las muestras sin mano o con una etiqueta dudosa no generan acciones.

Si un barrido no muestra acción, la ventana y el log ahora incluyen detalles
del descarte: pérdida de mano, tiempo vencido, movimiento vertical o demasiado
rápido. Durante el movimiento se muestran el recorrido y el tiempo frente a los
umbrales. Para probar recorridos más cortos y lentos:

```bash
python -m gesto simulate --distance 0.16 --max-duration-ms 1000
```

`--min-duration-ms` y `--max-duration-ms` ajustan la ventana temporal (150–1000 ms
en el perfil actual). Un umbral de distancia más bajo puede aceptar más movimientos
involuntarios: comprobar también la mano quieta y el retorno.

Prueba manual sugerida: 20 barridos por sentido, comprobar que el retorno no genere
otra acción y dos minutos con mano quieta o ausente. Registrar los resultados antes
de conectar Canva; las pruebas sintéticas no miden precisión con personas reales.

## Cuarto paso: controlar Canva

Primero completá la prueba de teclado del primer paso. Si la pulsación real no
avanza la presentación, resolvé la compatibilidad X11/XWayland antes de probar
el control continuo; un log de envío no confirma que Canva haya recibido la tecla.

```bash
python -m gesto present
```

1. La aplicación abre la cámara y arranca **PAUSADA**, sin ventana de diagnóstico.
2. Abrí Canva en modo presentación manual y dejalo enfocado.
3. Mostrá el puño cerrado durante un segundo. Empieza una cuenta regresiva de
   cinco segundos; abrí la mano y asegurate de que Canva conserve el foco.
4. Tras la activación, mantené la palma abierta quieta unos instantes para rearmar.
   Un barrido izquierdo envía una flecha derecha (avanzar); un barrido derecho,
   una flecha izquierda (retroceder).
5. Para **pausar**, sostené nuevamente el puño un segundo. Para **reanudar**, abrí
   la mano al menos 300 ms y repetí el puño sostenido; habrá otra cuenta regresiva.
6. Para **salir**, volvé a la terminal y presioná **Ctrl+C**.

El puño no debe alternar repetidamente mientras lo sostenés: cada comando exige
una liberación observada. Su reconocimiento usa una heurística de los cuatro
dedos plegados, sin el pulgar, y requiere validación con tu mano y cámara. Mientras
se reconoce un puño se descartan los barridos, incluso antes de completar el segundo.
Perder la mano no reanuda una presentación pausada.

Una detección aislada de puño suspende la emisión de acciones en esa muestra,
pero no borra inmediatamente el barrido. Solo un puño sostenido confirma el
cambio de modo. Al volver a una mano extendida, una interrupción mayor a 250 ms
descarta la trayectoria. La vista muestra **CONFIRMANDO PUNO** durante el candidato.

Si necesitás ver estados para calibrar el puño:

```bash
python -m gesto present --preview
```

La vista previa se abre al principio; enfocá Canva durante la cuenta regresiva.
En presentación se usa una vista flotante pequeña de 360 píxeles, sin marco y
configurada para no solicitar el foco del teclado. Muestra el estado en texto
legible sobre la imagen. Arrastrá su barra para ubicarla a un costado; el control
**Pausa / iniciar** alterna el modo y **×** termina la ejecución. Se usan controles
con el mouse, sin depender de atajos de teclado en la vista. Ctrl+C en la terminal
también termina. Los comandos `camera` y `simulate` conservan la ventana OpenCV
y sus controles P/Q/Esc.

La vista flotante usa Tkinter ya instalado, es de tipo tooltip en Linux y marca
sus propias ventanas X11 con `InputHint=0`. No activa ni reorienta otras ventanas.
La apertura y actualización se comprobaron conservando el foco en una prueba
gráfica real. Esto no reemplaza la validación de navegación en Canva con la vista.

El registro incluye activaciones, pausas, barridos y teclas enviadas, junto al
tiempo de la llamada de envío. Ese tiempo no mide la respuesta visual de Canva.
El fail-safe de PyAutoGUI permanece activo: si impide enviar una tecla, la
aplicación termina y libera la cámara.

### Evaluar Canva sin el control por puño

Si la simulación funciona pero la presentación no emite teclas, ejecutá:

```bash
python -m gesto present --no-fist-control --preview
```

Este modo empieza automáticamente tras la cuenta regresiva de cinco segundos.
Durante ese tiempo enfocá Canva. Mostrá la mano abierta, mantenela quieta hasta
**LISTO** y probá barridos hacia ambos lados, devolviendo la mano durante **ESPERA**.
La vista ayuda a comprobar que la cámara conserva la mano dentro de la imagen.
No necesitás cerrar el puño y ese gesto no pausa en este modo. Usá el control
**Pausa / iniciar** de la barra; para terminar, **×** o Ctrl+C en terminal.
Los logs deben incluir `[PRESENTACION]` y `[TECLA]` por cada acción.

## Configuración

`camera`, `simulate`, `present` y `keyboard-test` leen `gesto.toml` del proyecto.
El perfil actual conserva los ajustes probados: distancia 0.10 y duración máxima
1000 ms. Podés editar sus secciones:

- `[camera]`: índice, vista espejo y confianza de MediaPipe.
- `[gestures]`: distancia, duración, pausa y estabilización del barrido.
- `[presentation]`: cuenta regresiva y tiempos de puño/liberación.
- `[keys]`: teclas para `next` y `previous`, inicialmente `right` y `left`.

Las opciones de consola reemplazan los valores del archivo sin modificarlo:

```bash
python -m gesto present --camera 1 --distance 0.18
python -m gesto simulate --config mi_config.toml
```

Las opciones desconocidas, los tipos incorrectos y los umbrales inválidos se
rechazan antes de abrir la cámara o conectar el teclado.

## Organización

```text
gesto/
  __main__.py     Comandos y diagnóstico del entorno
  keyboard.py     Prueba aislada de navegación
  gestures.py     Detector temporal de barridos y estados
  config.py       Lectura y validación de TOML
  presentation.py Activación, pausa por puño y envío de acciones
  preview.py      Vista flotante de presentación sin solicitar foco
  model.py        Descarga y validación del modelo
  vision.py       Captura, inferencia y dibujo
models/
  README.md       Origen y checksum del modelo
tests/           Verificaciones sin cámara ni escritorio
log/             Registros locales de ejecución y resultados de pruebas
PLAN_MVP.md      Etapas y criterios de aceptación
gesto.toml       Configuración de cámara, gestos, presentación y teclas
requirements.in  Dependencias directas
requirements.txt Dependencias fijadas
```

## Validación y próximos pasos

```bash
uv pip check
python -m tests
```

Las pruebas automatizadas no abren la cámara ni envían teclas. La inferencia real
con el modelo se puede verificar sin escritorio mediante el smoke test:

```bash
python -m tests --smoke
```

Esta prueba usa fotogramas negros; valida carga e inferencia, no precisión con
manos reales. Las pruebas de cámara y Canva requieren el equipo del usuario.

Prueba gráfica opcional para comprobar la vista flotante, sin cámara ni teclas:

```bash
python -m tests --preview-smoke
```

Abre la vista con una imagen sintética durante menos de un segundo, compara el
foco antes/después y la cierra. Ejecutarla desde la sesión gráfica y no cambiar
de ventana durante la comprobación. El resultado se registra en `log/`.

## Registros de ejecución

Cada ejecución mediante `python -m gesto ...` guarda un archivo independiente en
`log/`, además de mostrar la salida en la terminal. También se registran las
pruebas ejecutadas con `python -m tests` y `python -m tests --smoke`.

Cada archivo incluye fecha y hora de Buenos Aires, comando, directorio, salida
estándar y errores combinados (incluidos mensajes nativos de MediaPipe), duración
y código de salida. Los nombres incluyen un identificador único para no pisar
ejecuciones anteriores. El código 0 indica finalización normal; las pruebas
fallidas conservan su código de error.

Los registros quedan en el equipo y se excluyen de Git. No contienen capturas
de cámara. Los comandos directos `python -m unittest ...` y
`python -m tests.smoke_vision` no pasan por el registro: usá los comandos de
prueba indicados arriba. Las ejecuciones anteriores a esta función no se
reconstruyen retroactivamente.

El siguiente paso es validar el modo presentación en Canva: ambos sentidos,
retorno sin cambios dobles, pausa/reanudación y salida. Ver [plan del MVP](PLAN_MVP.md).

## Referencias

- [MediaPipe Hand Landmarker para Python](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/python)
- [Modelo oficial y ficha técnica](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker#models)
- [PyAutoGUI y su funcionamiento en Linux](https://github.com/asweigart/pyautogui)
- [Presentar diseños en Canva](https://www.canva.com/help/presenting-designs/)

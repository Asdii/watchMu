Watch MU

Un detector de ítems para MU Online que usa captura de pantalla en tiempo real y coincidencia de plantillas (template matching).

Cuando se encuentra un ítem configurado, el programa:

Muestra un popup en pantalla.

Reproduce un sonido (alert.wav).

Guarda una captura de la coincidencia en la carpeta hits/.

⚠️ Importante:

El juego debe estar en modo ventana con resolución 1440x900 (no funciona en fullscreen).

Necesitas tener las plantillas (.png) de los ítems que quieres detectar.

Requisitos

Python 3.10 o 3.11

Windows 10/11

Librerías necesarias:

pip install windows-capture opencv-python numpy psutil pywin32 scikit-image

Preparación

Coloca el archivo alert.wav en la misma carpeta que watch_mu.py.

Crea una carpeta items/ y pon dentro las imágenes (.png) de los ítems a detectar.

Ejemplo: rare.png, uncommon.png, scarlet_rune.png

Asegúrate de abrir MU Online en modo ventana 1440x900.

Uso

Ejemplo de comando más sencillo para detectar ítems:

python watch_mu.py --title "EterealConquest" --items items/ --threshold 0.95 --fps 1 --scales "1.00" --hits hits

Parámetros principales

--title → parte del título de la ventana del juego.

--items → carpeta con los .png de los ítems.

--threshold → umbral mínimo de coincidencia (0–1).

--fps → frecuencia de escaneo en capturas por segundo.

--scales → factor de escala de las plantillas (ej: "0.90,1.00,1.10").

--hits → carpeta donde se guardarán los aciertos.

Ejemplo rápido
python watch_mu.py --title "EterealConquest" --items items/ --threshold 0.95


Esto:

Busca la ventana con título "EterealConquest".

Escanea en tiempo real los ítems de la carpeta items/.

Lanza un popup + sonido .wav cuando encuentra uno.

Guarda la captura en hits/.
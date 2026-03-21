# Audio to Video Studio

Generador batch de videos a partir de archivos de audio utilizando FFmpeg y una interfaz gráfica moderna construida con CustomTkinter.

## Descripción

Audio to Video Studio toma una carpeta con múltiples archivos de audio (MP3 o WAV), una imagen de fondo, y genera automáticamente un video por cada audio aplicando efectos visuales dinámicos como zoom suave, glitch y overlays animados.

## Características

- Procesamiento batch de múltiples audios
- Efectos visuales: zoom dinámico, glitch, overlays
- Fade in/out de audio configurable
- Resolución 1080p o 4K
- Cola de procesamiento con progreso en tiempo real
- Presets de configuración (lofi, ambient, jazz)
- Interfaz oscura moderna

## Requisitos

- Python 3.10+
- FFmpeg y ffprobe instalados en el sistema PATH
- Dependencias Python: ver `requirements.txt`

## Instalación

```bash
pip install -r requirements.txt
```

## Uso

```bash
python main.py
```

## Compilar a .exe

```bash
pip install pyinstaller
pyinstaller --onefile --windowed main.py
```

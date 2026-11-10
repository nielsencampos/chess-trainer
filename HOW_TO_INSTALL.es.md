# Cómo instalar Chess Trainer

*[In English](HOW_TO_INSTALL.md) · [Em português](HOW_TO_INSTALL.pt-BR.md)*

Chess Trainer es un programa gratuito que funciona en tu propia computadora. No necesita cuenta ni
internet para jugar. Los pasos llevan unos cinco minutos.

## 1. Descarga

Abre la [página de Releases](https://github.com/nielsencampos/chess-trainer/releases/latest) y, en
**Assets**, descarga el archivo para tu computadora:

| Tu computadora | Archivo |
|---|---|
| Windows 10 u 11 | `chess-trainer-…-windows-x64-setup.exe` |
| Mac con chip Apple (M1, M2, M3…) | `chess-trainer-…-macos-arm64.zip` |
| Mac con procesador Intel | `chess-trainer-…-macos-intel.zip` |
| Linux (Ubuntu 22.04 o más nuevo, o similar) | `chess-trainer-…-linux-x86_64.tar.gz` |

¿No sabes qué Mac tienes? Abre el menú Apple → **Acerca de este Mac**. "Chip: Apple M…" es chip
Apple; "Procesador: Intel" es Intel.

La descarga pesa entre 100 y 300 MB, porque incluye el motor de ajedrez Stockfish.

## 2. Instala y abre

### Windows

1. Haz doble clic en **chess-trainer-…-windows-x64-setup.exe** en la carpeta Descargas.
2. Windows puede mostrar **"Windows protegió su PC"** (SmartScreen). El aviso aparece porque el
   programa es nuevo y no tiene un certificado pago, no porque tenga algún problema. Haz clic en
   **Más información** y luego en **Ejecutar de todas formas**.
3. Sigue el instalador. No pide contraseña de administrador y añade **Chess Trainer** al menú Inicio
   (y al escritorio, si marcas esa opción).
4. Abre **Chess Trainer** desde el menú Inicio.

Si la ventana queda en blanco, instala el **Microsoft Edge WebView2 Runtime**, gratuito, desde el
sitio de Microsoft (Windows 11 y Windows 10 actualizado ya lo traen).

**Sin instalar:** el archivo `chess-trainer-…-windows-x64.zip` tiene el mismo programa. Haz clic
derecho en él → **Extraer todo…** y abre **chess-trainer.exe** en la carpeta extraída. Si aparece
*Failed to execute script 'launcher'*, borra la carpeta extraída, haz clic derecho en el zip →
**Propiedades** → marca **Desbloquear** → **Aceptar**, y extráelo otra vez.

### macOS

1. Haz doble clic en el archivo zip en la carpeta Descargas (Safari puede haberlo descomprimido ya).
   Aparece **Chess Trainer**.
2. Arrastra **Chess Trainer** a la carpeta **Aplicaciones**.
3. Haz doble clic en él. La primera vez, macOS dice que no puede verificar la app, porque Apple no
   la ha notarizado (eso exige una cuenta de desarrollador paga). Para abrirla de todos modos:
   - **macOS 15 Sequoia o más nuevo:** cierra el aviso. Abre **Ajustes del Sistema** → **Privacidad
     y seguridad**, baja hasta el mensaje sobre "Chess Trainer" y haz clic en **Abrir igualmente**.
     Escribe tu contraseña y haz clic en **Abrir igualmente** otra vez.
   - **macOS 14 Sonoma o más antiguo:** con la tecla Control pulsada, haz clic (o clic derecho) en
     **Chess Trainer** en Aplicaciones → **Abrir** → **Abrir**.

   macOS recuerda tu elección; desde entonces se abre con normalidad.

Si macOS dice que la app **"está dañada y no se puede abrir"**, abre la app **Terminal**, pega esta
línea, pulsa Return y abre la app de nuevo:

```bash
xattr -dr com.apple.quarantine "/Applications/Chess Trainer.app"
```

### Linux

1. Descomprime el archivo: haz doble clic en él en tu gestor de archivos y extráelo, o ejecuta
   `tar xzf chess-trainer-*-linux-x86_64.tar.gz`. Aparece una carpeta `chess-trainer`.
2. En una terminal, dentro de esa carpeta, ejecuta:

   ```bash
   ./install.sh
   ```

   Copia el programa a `~/.local/opt/chess-trainer` y añade **Chess Trainer** al menú de
   aplicaciones. No pide contraseña de administrador.
3. Abre **Chess Trainer** desde el menú de aplicaciones. También puedes ejecutar `./chess-trainer`
   desde la carpeta sin instalarlo.

Si la ventana no se abre en un escritorio X11, instala el paquete `libxcb-cursor0` (por ejemplo
`sudo apt install libxcb-cursor0`).

## Dónde se guardan tus partidas y líneas

Tus partidas guardadas, las importadas y tus líneas están en un solo archivo, `chess-trainer.duckdb`,
en esta carpeta. La carpeta también guarda el registro (`chess-trainer.log`) y las preferencias de
pantalla (tema, idioma, tablero) en `webview`.

| Sistema | Carpeta |
|---|---|
| Windows | `%LOCALAPPDATA%\chess-trainer` (pégalo en la barra de direcciones del Explorador de archivos) |
| macOS | `~/Library/Application Support/chess-trainer` (en Finder: **Ir** → **Ir a la carpeta…**) |
| Linux | `~/.local/share/chess-trainer` |

El programa y tus datos están separados: instalar una versión nueva o quitar el programa no toca tus
partidas.

### Haz una copia de seguridad

1. Cierra Chess Trainer. Mientras está abierto, los cambios recientes siguen en un archivo aparte,
   `chess-trainer.duckdb.wal`, y una copia solo de la base no los tendría.
2. Copia toda la carpeta `chess-trainer` de la tabla a un pendrive, una carpeta en la nube u otro
   disco.

Para restaurarla, cierra Chess Trainer y vuelve a poner la carpeta en el mismo lugar. El archivo de
la base funciona en cualquier sistema, así que también sirve para llevar tus partidas a otra
computadora. Una base de la versión Docker (`data/chess-trainer.duckdb`) se puede copiar igual.

## Actualiza

Descarga la versión nueva e instálala igual, en lugar de la anterior (Windows: ejecuta el instalador
nuevo; macOS: reemplaza la app en Aplicaciones; Linux: ejecuta `./install.sh` desde la carpeta nueva). Tus
partidas siguen donde están.

## Desinstala

1. Quita el programa:
   - **Windows:** **Configuración** → **Aplicaciones** → **Aplicaciones instaladas** → **Chess
     Trainer** → **Desinstalar**. Si usaste el zip, borra su carpeta.
   - **macOS:** arrastra **Chess Trainer** de Aplicaciones a la Papelera.
   - **Linux:** ejecuta `~/.local/opt/chess-trainer/install.sh --uninstall`.
2. Solo si también quieres borrar tus partidas y líneas: borra la carpeta de datos de la tabla. No
   se puede deshacer, así que haz antes una copia si quizá las quieras después.

## Si algo sale mal

- Abre solo un Chess Trainer a la vez.
- Chess Trainer usa el puerto 47800 de tu propia computadora. Si otro programa lo usa, Chess Trainer
  no arranca; el motivo queda escrito en `chess-trainer.log`, en la carpeta de datos.
- Para informar un problema, abre un [issue](https://github.com/nielsencampos/chess-trainer/issues)
  y adjunta `chess-trainer.log`.

## La otra forma: Docker

Si ya usas Docker, puedes ejecutar la misma app sin instalarla: mira
[Español en el README](README.md#español). Se abre en el navegador en <http://127.0.0.1:8000> y
guarda los datos en la carpeta `data/` del proyecto.

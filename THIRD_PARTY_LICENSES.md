# Third-party licenses

chess-trainer is licensed under GPL-3.0-only (see [LICENSE](LICENSE)). It ships or downloads the
components below. Each keeps its own license and copyright.

| Component | Where | Version / source | License | Copyright |
|---|---|---|---|---|
| Stockfish | Downloaded into the image at build time (`/opt/stockfish`, with its `Copying.txt` and `AUTHORS`) | Official releases; source at <https://github.com/official-stockfish/Stockfish> | GPL-3.0 | The Stockfish developers |
| chessops | `web/js/vendor/chessops/` (the modules the app needs, source-map comments removed) | 0.15.1, <https://github.com/niklasf/chessops> | GPL-3.0-or-later | Niklas Fiekas |
| @badrap/result | `web/js/vendor/badrap-result.js` (source-map comment removed) | 0.3.1, <https://github.com/badrap/result> | MIT (text below) | Badrap Oy |
| Lichess openings catalog | `catalog/data/`, and `openings/` is seeded from it | `lichess-org/chess-openings` at the commit in `catalog/SOURCE_COMMIT` | CC0-1.0 | Public domain dedication |
| Merida pieces | `web/pieces/merida/` | `lichess-org/lila` at `ae7b6b5` | GPL-2.0-or-later | Armando Hernandez Marroquin |
| Familjen Grotesk | `web/fonts/` | Fontsource 5.3.0 | OFL-1.1 | The Familjen Grotesk Project Authors |
| JetBrains Mono | `web/fonts/` | Fontsource 5.3.0 | OFL-1.1 | The JetBrains Mono Project Authors |
| ponytail skills | `.claude/skills/ponytail*/` (Claude Code skills for development, not shipped in the image) | `DietrichGebert/ponytail` at `96608e0` | MIT (text below) | DietrichGebert |

### Desktop app

The desktop packages (`desktop/`, built by PyInstaller) also ship Python, the app's Python
dependencies from `pyproject.toml`, the Stockfish build for that system (with its `Copying.txt` and
`AUTHORS` in `stockfish/`), and the components below. The versions are the ones in `uv.lock`.

| Component | Where | Version / source | License | Copyright |
|---|---|---|---|---|
| Python | All packages | CPython 3.13, <https://www.python.org/> | PSF-2.0 | Python Software Foundation |
| pywebview | All packages: the native window | 6.2.1, <https://github.com/r0x0r/pywebview> | BSD-3-Clause | Roman Sirokov |
| WebView2 SDK DLLs | Windows package, shipped inside pywebview | <https://www.nuget.org/packages/Microsoft.Web.WebView2> | BSD-3-Clause | Microsoft Corporation |
| bottle, proxy_tools | All packages, used by pywebview | 0.13.4 and 0.1.0 | MIT | Marcel Hellkamp (bottle); Jonathan Tushman (proxy_tools) |
| platformdirs | All packages: finds the user's data folder | 4.14.5, <https://github.com/tox-dev/platformdirs> | MIT | The platformdirs developers |
| PyInstaller bootloader | All packages: the executable that starts the app | 6.22.3, <https://pyinstaller.org/> | GPL-2.0-or-later with the PyInstaller bootloader exception | The PyInstaller Development Team |
| Qt 6 (Qt Base, Qt WebEngine and the modules they need) | Linux package | PyQt6-Qt6 6.12.0 and PyQt6-WebEngine-Qt6 6.140.0 wheels, <https://www.qt.io/> | LGPL-3.0 (Qt WebEngine embeds Chromium, under BSD-3-Clause and the licenses listed in its `about:credits`) | The Qt Company Ltd. and other contributors |
| PyQt6, PyQt6-WebEngine, PyQt6-sip | Linux package: Python bindings for Qt | 6.12.0, 6.140.0 and 13.13.0, <https://riverbankcomputing.com/software/pyqt/> | GPL-3.0-only (PyQt6-sip: BSD-2-Clause) | Riverbank Computing Limited |
| QtPy | Linux package, used by pywebview | 2.4.3, <https://github.com/spyder-ide/qtpy> | MIT | QtPy contributors |
| Inno Setup | Windows installer (`…-setup.exe`): the setup and uninstall program around the app | 6.7, <https://jrsoftware.org/isinfo.php> | Inno Setup License (permissive, <https://jrsoftware.org/files/is/license.txt>) | Jordan Russell and Martijn Laan |
| pythonnet, clr-loader | Windows package: pywebview's bridge to WebView2 | 3.2.1 and 0.3.1, <https://github.com/pythonnet/pythonnet> | MIT | The Contributors of the Python.NET Project |
| PyObjC | macOS package: pywebview's bridge to WKWebView | 13.0, <https://github.com/ronaldoussoren/pyobjc> | MIT | Ronald Oussoren and contributors |

The window's browser engine is the system's on Windows (Microsoft Edge WebView2) and macOS
(WKWebView): they are part of the operating system and not shipped. On Linux it is Qt WebEngine,
shipped in the package. PyQt6 is GPL-3.0, the same license as chess-trainer, so the Linux package
as a whole is distributed under GPL-3.0; its source is this repository.

License texts: [GPL-2.0](https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt),
[GPL-3.0](LICENSE), [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0),
[OFL-1.1](https://openfontlicense.org/open-font-license-official-text/),
[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/legalcode),
[MIT](https://opensource.org/license/mit),
[BSD-3-Clause](https://opensource.org/license/bsd-3-clause),
[BSD-2-Clause](https://opensource.org/license/bsd-2-clause),
[LGPL-3.0](https://www.gnu.org/licenses/lgpl-3.0.txt),
[PSF-2.0](https://docs.python.org/3/license.html),
[PyInstaller's license and bootloader exception](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt).

Lichess's Maestro and Alpha piece sets are deliberately not included: their terms forbid
commercial use, which GPL-3.0 does not allow a project to restrict.

## @badrap/result (MIT)

Copyright (c) 2018 Badrap Oy

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## ponytail (MIT)

Copyright (c) 2026 DietrichGebert

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

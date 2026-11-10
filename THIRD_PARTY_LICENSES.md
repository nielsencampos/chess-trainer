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

License texts: [GPL-2.0](https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt),
[GPL-3.0](LICENSE), [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0),
[OFL-1.1](https://openfontlicense.org/open-font-license-official-text/),
[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/legalcode),
[MIT](https://opensource.org/license/mit).

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

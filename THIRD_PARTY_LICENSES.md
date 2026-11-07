# Third-party licenses

chess-trainer is licensed under GPL-3.0-only (see [LICENSE](LICENSE)). It ships or downloads the
components below. Each keeps its own license and copyright.

| Component | Where | Version / source | License | Copyright |
|---|---|---|---|---|
| Stockfish | Downloaded into the image at build time (`/opt/stockfish`, with its `Copying.txt` and `AUTHORS`) | Official releases; source at <https://github.com/official-stockfish/Stockfish> | GPL-3.0 | The Stockfish developers |
| chess.js | `web/js/vendor/chess.js` (source-map comment removed) | 1.4.0, <https://github.com/jhlywa/chess.js> | BSD-2-Clause (text below) | Jeff Hlywa |
| Lichess openings catalog | `catalog/data/`, and `openings/` is seeded from it | `lichess-org/chess-openings` at the commit in `catalog/SOURCE_COMMIT` | CC0-1.0 | Public domain dedication |
| Merida pieces | `web/pieces/merida/` | `lichess-org/lila` at `ae7b6b5` | GPL-2.0-or-later | Armando Hernandez Marroquin |
| Cburnett pieces | `web/pieces/cburnett/`, and the pieces in `web/logo.svg` and `web/logo.png` | `lichess-org/lila` at `ae7b6b5` | GPL-2.0-or-later | Colin M.L. Burnett |
| Chessnut pieces | `web/pieces/chessnut/` | `lichess-org/lila` at `ae7b6b5`; <https://github.com/LexLuengas/chessnut-pieces> | Apache-2.0 | Alexis Luengas |
| Fantasy pieces | `web/pieces/fantasy/` | `lichess-org/lila` at `ae7b6b5`; <https://github.com/maurimo/chess-art> | MIT | Maurizio Monge |
| Familjen Grotesk | `web/fonts/` | Fontsource 5.3.0 | OFL-1.1 | The Familjen Grotesk Project Authors |
| JetBrains Mono | `web/fonts/` | Fontsource 5.3.0 | OFL-1.1 | The JetBrains Mono Project Authors |
| Caveat | `web/logo.svg` and `web/logo.png` (title and moves, converted to outlines) | Fontsource 5.3.0 | OFL-1.1 | The Caveat Project Authors |
| Noto Sans Symbols 2 | `web/fonts/` (Unicode piece set) | Fontsource 5.3.0 | OFL-1.1 | The Noto Project Authors |

License texts: [GPL-2.0](https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt),
[GPL-3.0](LICENSE), [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0),
[OFL-1.1](https://openfontlicense.org/open-font-license-official-text/),
[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/legalcode),
[MIT](https://opensource.org/license/mit).

Lichess's Maestro and Alpha piece sets are deliberately not included: their terms forbid
commercial use, which GPL-3.0 does not allow a project to restrict.

## chess.js (BSD-2-Clause)

Copyright (c) 2025, Jeff Hlywa (jhlywa@gmail.com)
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.

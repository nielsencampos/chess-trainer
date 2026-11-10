<p align="center">
  <img src="web/logo.svg" alt="Chess Trainer logo: four board squares with C, T, a pen and a clock" width="160">
</p>

# Chess Trainer

Local chess trainer: play Stockfish with real clock presets, drill your openings against a bot that
follows the book and flags where you left theory, and review your games from PGN, Chess.com or
Lichess with an evaluation bar. Chess960 included. English, Portuguese and Spanish, all in one
Docker image. It runs on your own machine (amd64 or arm64), with no accounts and no internet needed
to play.

*[Versão em português abaixo.](#português-brasil) · [Versión en español abajo.](#español)*

## Run

You need Docker with Compose.

```bash
git clone https://github.com/nielsencampos/chess-trainer.git
cd chess-trainer
docker compose up --build
```

Open <http://127.0.0.1:8000>.

The app is published on loopback only, because it has no login. To reach it from another device,
set `CHESS_TRAINER_BIND=0.0.0.0`, on a network you trust. `CHESS_TRAINER_PORT` changes the port.

**Desktop app (preview):** the same app in its own window, without Docker, is being built in
[desktop/](desktop/README.md). There are no downloads yet; Docker stays the way to run it.

## How it works

The full guide, with pictures, is in [docs/HELP.md](docs/HELP.md), the same as the Help screen in
the app, and who made it and why is in [docs/ABOUT.md](docs/ABOUT.md). A summary:

1. Pick your color and the lines to drill, from all 3,865 lines of the book. Search by name, ECO
   or moves. Each selected line has the same chance of being drawn.
2. The bot plays the drawn line. If you play a move from another selected line, it follows you.
3. A move outside the selected lines is a deviation: it is recorded with the expected moves and
   shown at the end of the game.
4. When the line ends or someone leaves theory, Stockfish takes over at the selected level.

Unchecking "Show moves" hides the move list and the opening name, headings included, during a game, so you can write on paper. They come back at the end.

Beyond openings:

- **Clocks:** bullet, and the blitz, rapid and classical presets of a DGT 3000 clock, or no clock.
- **Chess960:** roll one of the 960 starting positions, or paste its FEN, and play Stockfish.
- **Saved games:** every game is saved. Filter them, export them as PGN, review them move by move,
  or start a new game from any of their moves (not yet from a Chess960 game).
- **Import:** paste PGN, upload a file, or fetch a player's public games from Chess.com or Lichess.
  The review shows the PGN's evaluations, classifications, clocks, comments and side lines.
- **Evaluation bar:** Stockfish's evaluation while reviewing, and at the end of a game. It is a
  quick check, not a full analysis: for that, export the PGN to Chess.com or Lichess.
- **Scoresheet:** a printable A4 scoresheet, modeled on an official one, to write your moves by hand
  during long games. It is not an official scoresheet: it is for training only.
- **Help:** how to use every screen, in the app's menu.

Chess Trainer is for training. Never use it, or any engine, during a game against another person.

**Current state:** the book and games are in DuckDB (`data/chess-trainer.duckdb`). Bot levels are
provisional. The UI is in English, Brazilian Portuguese and Spanish. See the
[project brief](docs/PROJECT_BRIEF.md) for what comes next.

## The book

The bot's book is in `openings/`, one JSON file per opening family, loaded into DuckDB on start (a
few seconds the first time). It starts with all 3,865 lines of the
[Lichess openings catalog](https://github.com/lichess-org/chess-openings). Any line plays with either
color. The catalog lists named positions, not recommended replies, so lines are often short and the
engine plays on from there. They can be extended by pull request, recording the source. The format
is in [the brief, §6](docs/PROJECT_BRIEF.md).

The database lives in `./data`, which the container writes as UID 1000. To back it up, stop the app
and copy the file. Every move is saved there, so an unfinished game continues when you open the page
again, even after a restart. Clocks stop while the app is closed.

## Update Stockfish

The image uses the latest official Stockfish release at build time. To update:

```bash
docker compose build --pull
docker compose up -d
```

To pin a version (`sf_19` or newer; older releases have no universal or Linux arm64 binary):

```bash
STOCKFISH_VERSION=sf_19 docker compose build
```

The running version is in the page footer and at `/api/health`. If the build reports a GitHub rate
limit, wait an hour: the limit is 60 API requests per hour without a token.

## Develop

Needs [uv](https://docs.astral.sh/uv/). Test commands and conventions are in [CLAUDE.md](CLAUDE.md).

```bash
uv sync
uv run pytest
```

The pictures in Help are screenshots of the app in each language. After a visible UI change, make
them again against a running app (it plays and resigns games):

```bash
uv run python scripts/help_media.py --base-url http://127.0.0.1:8000
```

`docs/HELP*.md` and `docs/ABOUT*.md` are written from the Help and About screens' strings. After changing them, run
`uv run python scripts/help_docs.py`; a test fails while the files are out of date.

## License

[GPL-3.0](LICENSE). Third-party components are listed in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

---

## Português (Brasil)

Treinador local de xadrez: jogue contra o Stockfish com os relógios de verdade, pratique suas
aberturas contra um bot que segue o livro e mostra onde você saiu da teoria, e revise suas partidas
de PGN, Chess.com ou Lichess com barra de avaliação. Tem Chess960. Em inglês, português e espanhol,
tudo numa imagem Docker. Roda na sua máquina (amd64 ou arm64), sem conta e sem precisar de internet
para jogar.

**Para rodar**, com Docker e Compose instalados:

```bash
git clone https://github.com/nielsencampos/chess-trainer.git
cd chess-trainer
docker compose up --build
```

Depois abra <http://127.0.0.1:8000>.

**App desktop (prévia):** o mesmo app numa janela própria, sem Docker, está sendo feito em
[desktop/](desktop/README.md). Ainda não há downloads; por enquanto, rode com Docker.

**Guia completo**, com imagens: [docs/HELP.pt-BR.md](docs/HELP.pt-BR.md), o mesmo da tela de Ajuda do app. Quem fez e por quê: [docs/ABOUT.pt-BR.md](docs/ABOUT.pt-BR.md).

**Como funciona:** escolha a cor e as linhas, entre as 3.865 do livro, com busca por nome,
ECO ou lances. Cada linha selecionada tem a mesma chance de ser sorteada, e o bot joga a linha sorteada. Um lance fora das linhas selecionadas é um
desvio: ele é registrado com os lances esperados e aparece no fim da partida. Quando a linha acaba, ou
alguém sai da teoria, o Stockfish assume no nível escolhido. Desmarcar "Mostrar lances" esconde a
lista de lances e o nome da abertura durante a partida, para você anotar no papel.

**Além das aberturas:** relógios de bullet e os de blitz, rápido e clássico de um relógio DGT 3000;
Chess960; todas as partidas salvas, com filtros, exportação em PGN, revisão lance a lance e novo jogo
a partir de qualquer lance (ainda não de uma partida Chess960); importação de PGN colado, de arquivo ou das partidas públicas de um
jogador no Chess.com ou no Lichess; barra de avaliação do Stockfish na revisão e no fim da partida (uma checagem rápida: para uma
análise completa, exporte o PGN para o Chess.com ou o Lichess); planilha de anotação A4 para imprimir,
não oficial, só para treino; e uma Ajuda no menu. O Chess Trainer é para treinar: nunca o use, nem
qualquer engine, durante uma partida contra outra pessoa.

**Estado atual:** o livro e as partidas ficam no DuckDB, e uma partida não terminada continua quando você reabre a página. Os
níveis do bot são provisórios. A interface está em inglês, português e espanhol.

**Para atualizar o Stockfish:** rode `docker compose build --pull` e depois `docker compose up -d`.

## Español

Entrenador local de ajedrez: juega contra Stockfish con los relojes de verdad, practica tus aperturas
contra un bot que sigue el libro y muestra dónde saliste de la teoría, y revisa tus partidas de PGN,
Chess.com o Lichess con barra de evaluación. Incluye Chess960. En inglés, portugués y español, todo
en una imagen Docker. Funciona en tu máquina (amd64 o arm64), sin cuenta y sin necesitar internet
para jugar.

**Para ejecutarlo**, con Docker y Compose instalados:

```bash
git clone https://github.com/nielsencampos/chess-trainer.git
cd chess-trainer
docker compose up --build
```

Después abre <http://127.0.0.1:8000>.

**App de escritorio (vista previa):** la misma app en su propia ventana, sin Docker, se está
haciendo en [desktop/](desktop/README.md). Aún no hay descargas; por ahora, ejecútala con Docker.

**Guía completa**, con imágenes: [docs/HELP.es.md](docs/HELP.es.md), la misma que la pantalla de Ayuda de la app. Quién lo hizo y por qué: [docs/ABOUT.es.md](docs/ABOUT.es.md).

**Cómo funciona:** elige el color y las líneas, entre las 3.865 del libro, con búsqueda por nombre,
ECO o jugadas. Cada línea seleccionada tiene la misma probabilidad de salir, y el bot juega la línea
sorteada. Una jugada fuera de las líneas seleccionadas es una desviación: se registra con las jugadas
esperadas y aparece al final de la partida. Cuando la línea se acaba, o alguien sale de la teoría,
Stockfish toma el relevo en el nivel elegido. Desmarcar "Mostrar jugadas" oculta la lista de jugadas y
el nombre de la apertura durante la partida, para que anotes en papel.

**Además de las aperturas:** relojes de bullet y los de blitz, rápidas y clásicas de un reloj DGT 3000;
Chess960; todas las partidas guardadas, con filtros, exportación en PGN, revisión jugada a jugada y
nueva partida desde cualquier jugada (aún no desde una partida Chess960); importación de PGN pegado,
de archivo o de las partidas públicas de un jugador en Chess.com o Lichess; barra de evaluación de
Stockfish en la revisión y al final de la partida (una revisión rápida: para un análisis completo,
exporta el PGN a Chess.com o Lichess); planilla de anotación A4 para imprimir, no oficial, solo para
entrenar; y una Ayuda en el menú. Chess Trainer es para entrenar: nunca lo uses, ni ningún motor,
durante una partida contra otra persona.

**Estado actual:** el libro y las partidas están en DuckDB, y una partida sin terminar continúa cuando
vuelves a abrir la página. Los niveles del bot son provisionales. La interfaz está en inglés, portugués
y español.

**Para actualizar Stockfish:** ejecuta `docker compose build --pull` y después `docker compose up -d`.

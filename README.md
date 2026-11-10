<p align="center">
  <img src="web/logo.svg" alt="Chess Trainer logo: four board squares with C, T, a pen and a clock" width="160">
</p>

# chess-trainer

Local opening trainer: drill your chess repertoire against a bot that plays your book lines, then
Stockfish when theory ends. Python, plain JavaScript and Stockfish, all in one Docker image. It
runs on your own machine (amd64 or arm64), with no accounts and no internet needed to play.

*[Versão em português abaixo.](#português-brasil)*

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

## How it works

1. Pick your color and the lines to drill, from all 3,865 lines of the book. Search by name, ECO
   or moves. Each selected line has the same chance of being drawn.
2. The bot plays the drawn line. If you play a move from another selected line, it follows you.
3. A move outside the selected lines is a deviation: it is recorded with the expected moves and
   shown at the end of the game.
4. When the line ends or someone leaves theory, Stockfish takes over at the selected level.

Unchecking "Show moves" hides the move list and the opening name, headings included, during a game, so you can write on paper. They come back at the end.

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

## License

[GPL-3.0](LICENSE). Third-party components are listed in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

---

## Português (Brasil)

Treinador local de aberturas: pratique seu repertório contra um bot que joga as suas linhas e, quando
a teoria acaba, passa para o Stockfish. Roda na sua máquina (amd64 ou arm64), sem conta e sem precisar
de internet para jogar.

**Para rodar**, com Docker e Compose instalados:

```bash
git clone https://github.com/nielsencampos/chess-trainer.git
cd chess-trainer
docker compose up --build
```

Depois abra <http://127.0.0.1:8000>.

**Como funciona:** escolha a cor e as linhas, entre as 3.865 do livro, com busca por nome,
ECO ou lances. Cada linha selecionada tem a mesma chance de ser sorteada, e o bot joga a linha sorteada. Um lance fora das linhas selecionadas é um
desvio: ele é registrado com os lances esperados e aparece no fim da partida. Quando a linha acaba, ou
alguém sai da teoria, o Stockfish assume no nível escolhido. Desmarcar "Mostrar lances" esconde a
lista de lances e o nome da abertura durante a partida, para você anotar no papel.

**Estado atual:** o livro e as partidas ficam no DuckDB, e uma partida não terminada continua quando você reabre a página. Os
níveis do bot são provisórios. A interface está em inglês, português e espanhol.

**Para atualizar o Stockfish:** rode `docker compose build --pull` e depois `docker compose up -d`.

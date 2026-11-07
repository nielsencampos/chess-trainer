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

1. Pick your color, the openings and the variations to drill. Each selected variation has the same
   chance of being drawn.
2. The bot plays the drawn line. If you play a move from another selected line, it follows you.
3. A move outside the selected lines is a deviation: it is recorded with the expected moves and
   shown at the end of the game.
4. When the line ends or someone leaves theory, Stockfish takes over at the selected level.

Scoresheet mode hides the move list, so you can write on paper during long time controls.

**Current state (Phase 1):** games live in memory and are not saved after the server stops. Bot
levels are provisional. The UI is in English. See the [project brief](docs/PROJECT_BRIEF.md) for
what comes next.

## The repertoire

`repertoire/*.pgn` holds one file per opening, and each game in a file is one variation. The first
repertoire comes from the [Lichess openings catalog](https://github.com/lichess-org/chess-openings),
so lines are named positions and many stop early: the engine plays on from there. Lines can be
extended by pull request, with the source recorded in `[Source]`. Required headers and rules are in
[the brief, §6](docs/PROJECT_BRIEF.md).

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
uv run python -m catalog.validate
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

**Como funciona:** escolha a cor, as aberturas e as variações. Cada variação selecionada tem a mesma
chance de ser sorteada, e o bot joga a linha sorteada. Um lance fora das linhas selecionadas é um
desvio: ele é registrado com os lances esperados e aparece no fim da partida. Quando a linha acaba, ou
alguém sai da teoria, o Stockfish assume no nível escolhido. O modo súmula esconde a lista de lances
para você anotar no papel.

**Estado atual (Fase 1):** as partidas ficam na memória e não são salvas quando o servidor para. Os
níveis do bot são provisórios e a interface está em inglês; o pt-BR chega na Fase 4.

**Para atualizar o Stockfish:** rode `docker compose build --pull` e depois `docker compose up -d`.

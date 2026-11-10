# Como instalar o Chess Trainer

*[In English](HOW_TO_INSTALL.md) · [En español](HOW_TO_INSTALL.es.md)*

O Chess Trainer é um programa gratuito que roda no seu próprio computador. Não precisa de conta
nem de internet para jogar. Os passos levam uns cinco minutos.

## 1. Baixe

Abra a [página de Releases](https://github.com/nielsencampos/chess-trainer/releases/latest) e, em
**Assets**, baixe o arquivo do seu computador:

| Seu computador | Arquivo |
|---|---|
| Windows 10 ou 11 | `chess-trainer-…-windows-x64.zip` |
| Mac com chip Apple (M1, M2, M3…) | `chess-trainer-…-macos-arm64.zip` |
| Mac com processador Intel | `chess-trainer-…-macos-intel.zip` |
| Linux (Ubuntu 22.04 ou mais novo, ou parecido) | `chess-trainer-…-linux-x86_64.tar.gz` |

Não sabe qual é o seu Mac? Abra o menu Apple → **Sobre Este Mac**. "Chip: Apple M…" é chip Apple;
"Processador: Intel" é Intel.

O download tem entre 100 e 300 MB, porque inclui o motor de xadrez Stockfish.

## 2. Instale e abra

### Windows

1. Na pasta Downloads, clique com o botão direito no arquivo zip → **Extrair Tudo…** → **Extrair**.
   Não abra o programa de dentro do zip.
2. Mova a pasta `chess-trainer` extraída para onde você guarda programas, como a pasta Documentos.
3. Abra a pasta e dê dois cliques em **chess-trainer.exe**.
4. Na primeira vez, o Windows pode mostrar **"O Windows protegeu o computador"** (SmartScreen). O
   aviso aparece porque o programa é novo e não tem um certificado pago, não porque haja algo de
   errado com ele. Clique em **Mais informações** e depois em **Executar assim mesmo**. O Windows
   lembra da sua escolha.
5. Para abrir mais fácil da próxima vez: botão direito em **chess-trainer.exe** → **Mostrar mais
   opções** → **Enviar para** → **Área de trabalho (criar atalho)**.

Se a janela ficar em branco, instale o **Microsoft Edge WebView2 Runtime**, gratuito, do site da
Microsoft (o Windows 11 e o Windows 10 atualizado já vêm com ele).

### macOS

1. Dê dois cliques no arquivo zip na pasta Downloads (o Safari pode já ter descompactado). Aparece o
   **Chess Trainer**.
2. Arraste o **Chess Trainer** para a pasta **Aplicativos**.
3. Dê dois cliques nele. Na primeira vez, o macOS diz que não consegue verificar o app, porque ele
   não é autenticado pela Apple (isso exige uma conta paga de desenvolvedor). Para abrir mesmo
   assim:
   - **macOS 15 Sequoia ou mais novo:** feche o aviso. Abra **Ajustes do Sistema** → **Privacidade e
     Segurança**, role até a mensagem sobre o "Chess Trainer" e clique em **Abrir Mesmo Assim**.
     Digite sua senha e clique em **Abrir Mesmo Assim** de novo.
   - **macOS 14 Sonoma ou mais antigo:** com a tecla Control apertada, clique (ou clique com o botão
     direito) no **Chess Trainer** em Aplicativos → **Abrir** → **Abrir**.

   O macOS lembra da sua escolha; depois disso ele abre normalmente.

Se o macOS disser que o app **"está danificado e não pode ser aberto"**, abra o app **Terminal**,
cole esta linha, aperte Return e abra o app de novo:

```bash
xattr -dr com.apple.quarantine "/Applications/Chess Trainer.app"
```

### Linux

1. Descompacte o arquivo: dê dois cliques nele no gerenciador de arquivos e extraia, ou rode
   `tar xzf chess-trainer-*-linux-x86_64.tar.gz`. Aparece uma pasta `chess-trainer`.
2. Num terminal, dentro dessa pasta, rode:

   ```bash
   ./install.sh
   ```

   Ele copia o programa para `~/.local/opt/chess-trainer` e põe o **Chess Trainer** no menu de
   aplicativos. Não pede senha de administrador.
3. Abra o **Chess Trainer** pelo menu de aplicativos. Também dá para rodar `./chess-trainer` da
   pasta sem instalar.

Se a janela não abrir num desktop X11, instale o pacote `libxcb-cursor0` (por exemplo
`sudo apt install libxcb-cursor0`).

## Onde ficam suas partidas e linhas

Suas partidas salvas, as importadas e as suas linhas ficam num arquivo só, `chess-trainer.duckdb`,
nesta pasta. A pasta também guarda o log (`chess-trainer.log`) e as preferências de tela (tema,
idioma, tabuleiro) em `webview`.

| Sistema | Pasta |
|---|---|
| Windows | `%LOCALAPPDATA%\chess-trainer` (cole na barra de endereço do Explorador de Arquivos) |
| macOS | `~/Library/Application Support/chess-trainer` (no Finder: **Ir** → **Ir para a Pasta…**) |
| Linux | `~/.local/share/chess-trainer` |

O programa e os seus dados ficam separados: instalar uma versão nova ou remover o programa não mexe
nas suas partidas.

### Faça backup

1. Feche o Chess Trainer.
2. Copie a pasta `chess-trainer` inteira, a da tabela acima, para um pendrive, uma pasta na nuvem ou
   outro disco.

Para restaurar, feche o Chess Trainer e ponha a pasta de volta no mesmo lugar. O arquivo do banco
funciona em qualquer sistema, então ele também serve para levar suas partidas para outro
computador. Um banco da versão Docker (`data/chess-trainer.duckdb`) pode ser copiado do mesmo jeito.

## Atualize

Baixe a versão nova e instale do mesmo jeito, no lugar da antiga (Windows: troque a pasta; macOS:
troque o app em Aplicativos; Linux: rode `./install.sh` da pasta nova). Suas partidas continuam
onde estão.

## Desinstale

1. Remova o programa:
   - **Windows:** apague a pasta `chess-trainer` e o atalho da área de trabalho, se você criou um.
   - **macOS:** arraste o **Chess Trainer** de Aplicativos para o Lixo.
   - **Linux:** rode `~/.local/opt/chess-trainer/install.sh --uninstall`.
2. Só se quiser apagar também suas partidas e linhas: apague a pasta de dados da tabela acima. Isso
   não tem volta, então faça um backup antes se talvez for querer depois.

## Se algo der errado

- Abra só um Chess Trainer por vez.
- O Chess Trainer usa a porta 47800 do seu próprio computador. Se outro programa estiver usando, o
  Chess Trainer não abre; o motivo fica escrito no `chess-trainer.log`, na pasta de dados.
- Para relatar um problema, abra uma [issue](https://github.com/nielsencampos/chess-trainer/issues)
  e anexe o `chess-trainer.log`.

## O outro jeito: Docker

Se você já usa Docker, dá para rodar o mesmo app sem instalar: veja
[Português (Brasil) no README](README.md#português-brasil). Ele abre no navegador em
<http://127.0.0.1:8000> e guarda os dados na pasta `data/` do projeto.

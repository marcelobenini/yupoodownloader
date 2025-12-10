import os
import sys
os.environ["PYTHONASYNCIODEBUG"] = "1"

CONFIG_PATH = os.path.dirname(__file__).replace("\\", "/") + "/config.json"

import asyncio
from time import sleep, perf_counter

# Garante que no Windows use o WindowsSelectorEventLoopPolicy,
# mas não quebra em outros sistemas.
try:
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
except Exception:
    pass

from rich.console import Console
from rich.text import Text
from rich.panel import Panel
import rich.prompt as prompt
import re
from tkinter import filedialog
import tkinter as tk
import json
import requests

from rich_patch import make_prompt, render_default  # <<< usa o rich_patch.py

clear = lambda: os.system("cls")


class App:
    def __init__(self):
        self.version = "1.4.2"
        # desativamos qualquer checagem online de updates
        self.update_message = None

        self.console = Console(color_system="auto")
        self.st1np = self.parse_nick()

    def main(self):
        clear()
        self.default()
        self.console.print(
            "\nPrograma desenvolvido para te ajudar a baixar "
            "imagens com qualidade e facilmente do site da [#0ba162]Yupoo[/]!"
        )
        self.console.print("\n[b #6149ab]Opções[/]")
        self.console.print(
            "[b #baa6ff]1.[/] Baixe todas as imagens de todos os álbuns. "
            "([bold u #c7383f]pesado[/])"
        )
        self.console.print(
            "[b #baa6ff]2.[/] Baixe apenas a foto principal de todos os álbuns."
        )
        self.console.print(
            "[b #baa6ff]3.[/] Inserir álbuns ou categorias para baixar todas as fotos."
        )
        self.console.print(
            "[b #baa6ff]4.[/] Inserir álbuns ou categorias para baixar apenas a foto principal."
        )

        self.edit_rich()
        self.opt = prompt.Prompt.ask(
            "\n[b #6149ab]>>[/]  Selecione uma opção",
            choices=["1", "2", "3", "4"],
            default="3",
        )
        clear()
        self.default()

        try:
            self.execute_answer()
        except Exception as e:
            self.console.print("[b #c7383f]" + str(e) + "[/]")
            import traceback

            with open("info.log", "a", encoding="utf-8") as f:
                f.write(
                    f"albums: {getattr(self, 'yupoo_downloader', None) and self.yupoo_downloader.albums}\n\n"
                    f"{traceback.format_exc()}\n-\n"
                )
            return

        self.console.print(
            f"\n[b #0ba162]Concluído! Imagens salvas no diretório {self.path_to_save}, "
            "na pasta chamada fotos_yupoo.[/]"
        )
        self.console.print(
            f"Tempo gasto: [b #0ba162]{round(perf_counter() - self.start_time, 2)}[/]"
        )

        # abre a pasta no Explorer
        import subprocess

        FILEBROWSER_PATH = os.path.join(os.getenv("WINDIR"), "explorer.exe")

        def explore(path):
            path = os.path.normpath(path)
            if os.path.isdir(path):
                subprocess.run([FILEBROWSER_PATH, path])
            elif os.path.isfile(path):
                subprocess.run([FILEBROWSER_PATH, "/select,", path])

        explore(os.path.join(self.path_to_save, "fotos_yupoo"))

        opt = prompt.Confirm.ask("\nDeseja executar o programa novamente?", default=True)
        if opt:
            os.execl(sys.executable, sys.executable, *sys.argv)
        else:
            sys.exit()

    # --------------------------------------------------------------------- #
    # EXECUTE ANSWER
    # --------------------------------------------------------------------- #
    def execute_answer(self):
        try:
            selected_print = lambda option, text: self.console.print(
                f"Opção [b #6149ab]{option}[/] selecionada: [b #baa6ff]{text}[/]"
            )

            def choose_path():
                self.console.print(
                    "\nEscolha o [#baa6ff b]diretório padrão[/] para salvar as fotos."
                )
                root = tk.Tk()
                root.withdraw()
                while True:
                    self.path_to_save = filedialog.askdirectory()
                    if self.path_to_save != "":
                        break
                with open("config.json", "w", encoding="utf-8") as f:
                    config = {"path_to_save": self.path_to_save}
                    json.dump(config, f)

            # verifica / escolhe diretório padrão
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    self.path_to_save = config.get("path_to_save", "")
                if self.path_to_save != "":
                    self.console.print(
                        f"\nDiretório padrão: [b #baa6ff]{self.path_to_save}[/]"
                    )
                    opt = prompt.Confirm.ask(
                        "O diretório para salvar as fotos está correto?", default=True
                    )
                    if not opt:
                        choose_path()
                else:
                    choose_path()
            else:
                choose_path()

            clear()
            from main import YupooDownloader

            self.default()

            # ------------- OPÇÕES 1 E 2 – CATÁLOGO INTEIRO -----------------
            if self.opt in ("1", "2"):
                if self.opt == "1":
                    selected_print_ = lambda: selected_print(
                        "1", "Baixando todas as fotos do catálogo!"
                    )
                    selected_print_()
                    self.console.print("\nInsira o link do catálogo.")
                    while True:
                        url = prompt.Prompt.ask("[#6149ab b]link[/]")
                        url = self.verify_url(self.parse_url(url))
                        if url is not None:
                            break
                    clear()
                    self.default()
                    selected_print_()
                    self.start_time = perf_counter()
                    self.yupoo_downloader = YupooDownloader(
                        all_albums=True, urls=url, cover=False
                    )
                    asyncio.run(self.yupoo_downloader.main())
                else:
                    selected_print_ = lambda: selected_print(
                        "2", "Baixando todas as fotos principais do catálogo!"
                    )
                    selected_print_()
                    self.console.print("\nInsira o link do catálogo.")
                    while True:
                        url = prompt.Prompt.ask("[#6149ab b]link[/]")
                        url = self.verify_url(self.parse_url(url))
                        if url is not None:
                            break
                    clear()
                    self.default()
                    selected_print_()
                    self.start_time = perf_counter()
                    self.yupoo_downloader = YupooDownloader(
                        all_albums=True, urls=url, cover=True
                    )
                    asyncio.run(self.yupoo_downloader.main())

            # ------------- OPÇÕES 3 E 4 – LINKS DE ÁLBUNS ------------------
            elif self.opt in ("3", "4"):
                if self.opt == "3":
                    selected_print_ = lambda: selected_print(
                        "3", "Baixando todas as fotos dos álbuns selecionados!"
                    )
                else:
                    selected_print_ = lambda: selected_print(
                        "4",
                        "Baixando todas as fotos principais dos álbuns selecionados!",
                    )

                # LOOP: permite repetir a mesma opção 3/4 várias vezes
                while True:
                    selected_print_()
                    self.console.print(
                        "\nInsira os links dos álbuns para download."
                    )
                    self.console.print(
                        "([#baa6ff]digite [#0ba162 b]ok[/] para executar e "
                        "[#c7383f b]del[/] para cancelar o último link inserido[/])\n"
                    )

                    # zera a lista a cada rodada
                    self.urls = []

                    # coleta de links
                    while True:
                        url = prompt.Prompt.ask("[#6149ab b]link[/]")
                        url = url.strip()
                        if url.lower() == "ok":
                            if len(self.urls) != 0:
                                break
                            self.console.print(
                                "[b #c7383f]insira pelo menos um link antes de iniciar![/]\n"
                            )
                        elif url.lower() == "del":
                            if len(self.urls) != 0:
                                self.urls.pop()
                                self.console.print(
                                    "último link [#c7383f]removido[/]!\n"
                                )
                            else:
                                self.console.print(
                                    "[b #c7383f]insira pelo menos um link antes de remover![/]\n"
                                )
                        else:
                            # parseia e valida o link; se for válido, é adicionado em self.urls
                            self.verify_url(self.parse_url(url))

                    # executa download para esse lote de links
                    clear()
                    self.default()
                    selected_print_()
                    self.start_time = perf_counter()
                    if self.opt == "3":
                        self.yupoo_downloader = YupooDownloader(
                            all_albums=False, urls=self.urls, cover=False
                        )
                    else:
                        self.yupoo_downloader = YupooDownloader(
                            all_albums=False, urls=self.urls, cover=True
                        )
                    asyncio.run(self.yupoo_downloader.main())

                    # pergunta se quer repetir a mesma opção
                    again = prompt.Confirm.ask(
                        "\nDeseja baixar mais álbuns usando esta mesma opção?",
                        default=False,
                    )
                    if not again:
                        break

                    clear()
                    self.default()

        except Exception as e:
            raise Exception(e)

    # --------------------------------------------------------------------- #
    # PARSE / VERIFY URL
    # --------------------------------------------------------------------- #
    def parse_url(self, url: str):
        rx_url = lambda text: re.findall(r"(?<=https:\/\/)(.*?)(?=\.x)", text)
        if len(rx_url(url)) == 0:
            rx_catalog = re.findall(r"(?<=photos\/)(.*?)(?=\/)", url)
            if len(rx_catalog) != 0:
                catalog = rx_catalog[0]
                url_split = [part for part in url.split("/") if part != ""]

                # catalog url
                if url_split[-1] == "albums" and url_split[-2] == catalog:
                    url = f"https://{catalog}.x.yupoo.com/"
                # album url
                elif (
                    url_split[-2] == "albums"
                    and url_split[-3] == catalog
                ):
                    url = f"https://{catalog}.x.yupoo.com/albums/{url_split[-1]}"
                # categories / collections
                elif (url_split[-2] in ("categories", "collections")) and (
                    url_split[-3] == catalog
                ):
                    url = (
                        f"https://{catalog}.x.yupoo.com/{url_split[-2]}/{url_split[-1]}"
                    )
                else:
                    return None
        return url

    def verify_url(self, url):
        if url is None:
            self.console.print(
                "[b #c7383f]ultimo link não considerado, link inválido!\n"
            )
        elif "yupoo" not in url:
            self.console.print(
                "[b #c7383f]ultimo link não considerado, link inválido!\n"
                "lembre-se de inserir apenas catálogos do site Yupoo![/]\n"
            )
        elif not url.startswith("https://"):
            self.console.print(
                '[b #c7383f]ultimo link não considerado, link inválido!\n'
                'lembre-se de colocar "https://"[/]\n'
            )
        else:
            # opções 1 e 2: só aceitam URL do catálogo raiz
            if self.opt in ("1", "2"):
                if "categories" in url or "collections" in url:
                    self.console.print(
                        "[b #c7383f]ultimo link não considerado, link inválido!\n"
                        "use a 3 ou 4 opção para baixar categorias[/]\n"
                    )
                elif ".com" not in url[-5:]:
                    self.console.print(
                        '[b #c7383f]ultimo link não considerado, link inválido!\n'
                        'não pode haver nada após ".com", exemplo de link válido: '
                        '"https://_____.x.yupoo.com/"[/]\n'
                    )
                else:
                    return url
            # opções 3 e 4: guardamos vários links em self.urls
            elif self.opt in ("3", "4"):
                if not hasattr(self, "urls"):
                    self.urls = []
                if url not in self.urls:
                    self.urls.append(url)

    # --------------------------------------------------------------------- #
    # INTERFACE / ESTILO
    # --------------------------------------------------------------------- #
    def default(self):
        if self.update_message:
            self.console.print(
                Panel.fit(
                    self.update_message,
                    title="[blink #4912ff]AVISO[/]",
                    subtitle="[blink #4912ff]AVISO[/]",
                )
            )

        self.console.print(self.st1np)
        self.console.print(
            f"[#baa6ff]Aplicação [#6149ab b]v{self.version}[/], desenvolvida por [#6149ab b]st1np[/]![/]\n"
        )
        self.console.print("[#ffffff]Telegram:[/] [default]https://t.me/appyupoo[/]")
        self.console.print("Sugestões, reportar bugs: (12) 9 8137-2735\n")
        self.console.print(
            Panel.fit(
                "Considere apoiar o PROJETO!\nChave PIX: (12) 9 8137-2735",
                title="***",
                subtitle="***",
            )
        )

    def edit_rich(self):
        def choices_style(style="prompt.choices"):
            prompt.PromptBase.make_prompt = make_prompt(
                style=style, DefaultType=prompt.DefaultType, Text=Text
            )

        def default_style(style="prompt.default", path="Confirm"):
            if path == "Confirm":
                prompt.Confirm.render_default = render_default(
                    path=path,
                    style=style,
                    DefaultType=prompt.DefaultType,
                    Text=Text,
                )
            elif path == "Prompt":
                prompt.PromptBase.render_default = render_default(
                    path=path,
                    style=style,
                    DefaultType=prompt.DefaultType,
                    Text=Text,
                )

        prompt.Confirm.choices = ["s", "n"]
        prompt.Confirm.validate_error_message = (
            "Digite apenas [bold #0ba162]S[/] e [bold #c7383f]N[/]\n"
        )
        prompt.PromptBase.illegal_choice_message = (
            "[#c7383f]Por favor, selecione uma das opções disponíveis[/]"
        )
        choices_style("bold #baa6ff")
        default_style("bold #6149ab")
        default_style("bold #6149ab", "Prompt")

    def parse_nick(self):
        nick = Text(
            """       __  ___          
  ___ / /_<  /___   ___ 
 (_-</ __// // _ \\ / _ \\
/___/\\__//_//_//_// .__/
                 /_/  """,
            style="bold #4912ff",
        )

        def change_color(regex_list, color):
            for regex in regex_list:
                nick.highlight_regex(regex, color)

        regex_1 = [
            r"  ___    ",
            r"<  /",
            r"// //",
            r"//_//",
        ]  # #baa6ff
        regex_2 = [
            r"/ _ ",
            r" __/",
            r"\\__/",
            r"_//_// \.__/",
        ]  # #4912ff
        change_color(regex_1, "b #baa6ff")
        change_color(regex_2, "b #4912ff")

        return nick


if __name__ == "__main__":
    try:
        clear()
        app = App().main()
        while True:
            sleep(1)
    except KeyboardInterrupt:
        clear()
        app = None
        clear()
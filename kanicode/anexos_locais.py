"""Caminhos originais dos arquivos soltos na janela nativa, sem copiar conteúdo."""
import json
from pathlib import Path

IMAGENS = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp", "image/svg+xml"}

def receber(janela, evento):
    arquivos, erros = [], []
    for item in evento.get("dataTransfer", {}).get("files", []):
        if item.get("type") in IMAGENS:
            continue  # As imagens continuam no fluxo de miniaturas do navegador.
        nome = str(item.get("name") or "arquivo")
        caminho = item.get("pywebviewFullPath")
        try:
            if not isinstance(caminho, str) or not Path(caminho).is_absolute() or not Path(caminho).is_file():
                raise ValueError()
            caminho = str(Path(caminho).resolve())
            arquivos.append({"nome": Path(caminho).name, "caminho": caminho, "arquivo": True})
        except (OSError, ValueError):
            erros.append("Não consegui acessar " + nome + ". Arraste um arquivo existente do Explorador do Windows.")
    if arquivos or erros:
        dados = json.dumps({"arquivos": arquivos, "erros": erros}, ensure_ascii=True)
        janela.evaluate_js("window.kaniAnexosLocais(" + dados + ")")

def ligar(janela):
    from webview.dom import DOMEventHandler
    # O listener DOM habilita no WebView2 a entrega dos caminhos reais, ausentes no File do JavaScript.
    janela.dom.document.events.drop += DOMEventHandler(lambda evento: receber(janela, evento), prevent_default=True)
    janela.evaluate_js("window.KC_DROP_LOCAL = true")

import os
import requests
import feedparser

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

FEEDS = [
    "https://www.melhorescartoes.com.br/feed",
    "https://passageirodeprimeira.com/feed/",
    "https://pontospravoar.com/feed/"
]

PALAVRAS_CHAVE = [
    "bônus", "transferência", "átomos", "livelo", "esfera", 
    "latam pass", "latam", "smiles", "tudoazul", "azul fidelidade", "% de bônus"
]

ARQUIVO_HISTORICO = "enviados.txt"

def carregar_enviados():
    if not os.path.exists(ARQUIVO_HISTORICO):
        return set()
    with open(ARQUIVO_HISTORICO, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def salvar_enviado(link):
    with open(ARQUIVO_HISTORICO, "a", encoding="utf-8") as f:
        f.write(f"{link}\n")

def enviar_telegram(titulo, link):
    mensagem = (
        f"🚨 <b>NOVA PROMOÇÃO DE MILHAS IDENTIFICADA!</b>\n\n"
        f"📌 <b>{titulo}</b>\n\n"
        f"🔗 <a href='{link}'>Clique aqui para conferir os detalhes</a>"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensagem,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    requests.post(url, json=payload, timeout=10)

def executar():
    enviados = carregar_enviados()
    novos_enviados = 0

    for url_feed in FEEDS:
        try:
            feed = feedparser.parse(url_feed)
            for entry in feed.entries[:10]:
                titulo = entry.title
                link = entry.link

                if link not in enviados:
                    if any(termo in titulo.lower() for termo in PALAVRAS_CHAVE):
                        enviar_telegram(titulo, link)
                        salvar_enviado(link)
                        enviados.add(link)
                        novos_enviados += 1
        except Exception as e:
            print(f"Erro ao processar feed {url_feed}: {e}")

    print(f"Processamento concluído. {novos_enviados} novos alertas enviados.")

if __name__ == "__main__":
    executar()

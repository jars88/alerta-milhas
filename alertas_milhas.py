import os
from datetime import datetime, timezone, timedelta
import requests
import feedparser

# Configurações do Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Portais agregadores de promoções
FEEDS = [
    "https://www.melhorescartoes.com.br/feed",
    "https://passageirodeprimeira.com/feed/",
    "https://pontospravoar.com/feed/"
]

# Palavras-chave para Transferência Bonificada
TERMOS_TRANSFERENCIA = [
    "transferência", "transfira", "bônus", "% de bônus", "bonificada", "bonificação"
]

# Palavras-chave para Compras Bonificadas no Varejo
TERMOS_COMPRA = [
    "pontos por real", "pontos por r$", "pontos/r$", "compre e ganhe", 
    "compre e pontue", "acumule pontos", "pts por real", "pts/real"
]

# Mapeamento de Tags e Emojis por Programa
PROGRAMAS = {
    "latam": ("🔴 LATAM PASS", ["latam", "latam pass"]),
    "smiles": ("🟠 SMILES", ["smiles", "gol"]),
    "azul": ("🔵 AZUL FIDELIDADE", ["azul", "tudoazul", "azul fidelidade"]),
    "livelo": ("🩷 LIVELO", ["livelo"]),
    "atomos": ("⚫ C6 ÁTOMOS", ["átomos", "atomos", "c6 bank", "c6"]),
    "esfera": ("🟢 ESFERA", ["esfera", "santander"])
}

ARQUIVO_HISTORICO = "enviados.txt"

def carregar_enviados():
    if not os.path.exists(ARQUIVO_HISTORICO):
        return set()
    with open(ARQUIVO_HISTORICO, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def salvar_enviado(link):
    with open(ARQUIVO_HISTORICO, "a", encoding="utf-8") as f:
        f.write(f"{link}\n")

def identificar_programas(texto):
    texto_lower = texto.lower()
    tags = []
    for chave, (tag_nome, sinonimos) in PROGRAMAS.items():
        if any(s in texto_lower for s in sinonimos):
            tags.append(tag_nome)
    return " | ".join(tags) if tags else "🌐 FIDELIDADE & MILHAS"

def identificar_tipo(texto):
    texto_lower = texto.lower()
    tem_transf = any(t in texto_lower for t in TERMOS_TRANSFERENCIA)
    tem_compra = any(t in texto_lower for t in TERMOS_COMPRA)

    if tem_transf and not tem_compra:
        return "✈️ TRANSFERÊNCIA BONIFICADA"
    elif tem_compra and not tem_transf:
        return "🛍️ COMPRA BONIFICADA (VAREJO)"
    elif tem_transf and tem_compra:
        return "🔥 OFERTA DE TRANSFERÊNCIA / COMPRA"
    return "📢 OPORTUNIDADE DE PONTOS"

def enviar_telegram(titulo, link):
    categoria = identificar_tipo(titulo)
    programas = identificar_programas(titulo)

    mensagem = (
        f"<b>{categoria}</b>\n"
        f"🏷️ <i>{programas}</i>\n\n"
        f"📌 <b>{titulo}</b>\n\n"
        f"🔗 <a href='{link}'>Clique aqui para conferir o regulamento</a>"
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
    # Validação do horário de silêncio (Horário de Brasília: UTC-3)
    fuso_brasilia = timezone(timedelta(hours=-3))
    hora_atual = datetime.now(fuso_brasilia).hour

    if hora_atual >= 23 or hora_atual < 6:
        print(f"Modo noturno ativo ({hora_atual}h). Alertas silenciados.")
        return

    enviados = carregar_enviados()
    todos_termos = TERMOS_TRANSFERENCIA + TERMOS_COMPRA
    novos_enviados = 0

    for url_feed in FEEDS:
        try:
            feed = feedparser.parse(url_feed)
            for entry in feed.entries[:12]:
                titulo = entry.title
                link = entry.link

                if link not in enviados:
                    if any(termo in titulo.lower() for termo in todos_termos):
                        enviar_telegram(titulo, link)
                        salvar_enviado(link)
                        enviados.add(link)
                        novos_enviados += 1
        except Exception as e:
            print(f"Erro ao processar feed {url_feed}: {e}")

    print(f"Execução concluída. {novos_enviados} novos alertas enviados.")

if __name__ == "__main__":
    executar()

import os
import csv
import re
from datetime import datetime, timezone, timedelta, time
import requests
import feedparser

# Configurações do Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Portais agregadores: Milhas, Cartões e Passagens Aéreas Promocionais
FEEDS = [
    # Portais de Programas e Fidelidade
    "https://www.melhorescartoes.com.br/feed",
    "https://passageirodeprimeira.com/feed/",
    "https://pontospravoar.com/feed/",
    # Portais de Promoções de Voos e Passagens
    "https://www.melhoresdestinos.com.br/feed",
    "https://passagensimperdiveis.com.br/feed/"
]

# Palavras-chave por Categoria
TERMOS_TRANSFERENCIA = [
    "transferência", "transfira", "bônus", "% de bônus", "bonificada", "bonificação"
]

TERMOS_COMPRA = [
    "pontos por real", "pontos por r$", "pontos/r$", "compre e ganhe", 
    "compre e pontue", "acumule pontos", "pts por real", "pts/real"
]

TERMOS_VOOS = [
    "passagens", "passagem", "voos", "voo", "trechos", "ida e volta", 
    "orlando", "lisboa", "miami", "paris", "madrid", "nordeste", "promoção de passagens"
]

# Mapeamento de Programas e Ícones Visuais
PROGRAMAS = {
    "latam": ("🔴 LATAM PASS", ["latam", "latam pass"]),
    "smiles": ("🟠 SMILES", ["smiles", "gol"]),
    "azul": ("🔵 AZUL FIDELIDADE", ["azul", "tudoazul", "azul fidelidade"]),
    "livelo": ("🩷 LIVELO", ["livelo"]),
    "atomos": ("⚫ C6 ÁTOMOS", ["átomos", "atomos", "c6 bank", "c6"]),
    "esfera": ("🟢 ESFERA", ["esfera", "santander"]),
    "tap": ("⚪ TAP MILES&GO", ["tap miles", "miles&go", "tap"])
}

ARQUIVO_HISTORICO_TXT = "enviados.txt"
ARQUIVO_HISTORICO_CSV = "historico_alertas.csv"

def obter_horario_brasilia():
    fuso_brasilia = timezone(timedelta(hours=-3))
    return datetime.now(fuso_brasilia)

def carregar_enviados():
    if not os.path.exists(ARQUIVO_HISTORICO_TXT):
        return set()
    with open(ARQUIVO_HISTORICO_TXT, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def salvar_enviado(link):
    with open(ARQUIVO_HISTORICO_TXT, "a", encoding="utf-8") as f:
        f.write(f"{link}\n")

def registrar_historico_csv(data_hora, categoria, programas, titulo, link):
    arquivo_novo = not os.path.exists(ARQUIVO_HISTORICO_CSV)
    
    # Extrai percentual de bônus se houver (ex: 80%, 100%, 30%)
    match_bonus = re.search(r'(\d+)\s*%', titulo)
    bonus_extraido = f"{match_bonus.group(1)}%" if match_bonus else "-"

    with open(ARQUIVO_HISTORICO_CSV, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        if arquivo_novo:
            writer.writerow(["Data", "Hora", "Categoria", "Programas", "Bonus_Identificado", "Titulo", "Link"])
        
        writer.writerow([
            data_hora.strftime("%d/%m/%Y"),
            data_hora.strftime("%H:%M:%S"),
            categoria,
            programas,
            bonus_extraido,
            titulo,
            link
        ])

def identificar_programas(texto):
    texto_lower = texto.lower()
    tags = []
    for chave, (tag_nome, sinonimos) in PROGRAMAS.items():
        if any(s in texto_lower for s in sinonimos):
            tags.append(tag_nome)
    return " | ".join(tags) if tags else "🌐 GERAL / COMPANHIAS"

def identificar_tipo(texto):
    texto_lower = texto.lower()
    tem_transf = any(t in texto_lower for t in TERMOS_TRANSFERENCIA)
    tem_compra = any(t in texto_lower for t in TERMOS_COMPRA)
    tem_voo = any(t in texto_lower for t in TERMOS_VOOS)

    if tem_voo and not (tem_transf or tem_compra):
        return "✈️ ALERTA DE PASSAGENS / VOOS"
    elif tem_transf and not tem_compra:
        return "🔄 TRANSFERÊNCIA BONIFICADA"
    elif tem_compra and not tem_transf:
        return "🛍️ COMPRA BONIFICADA (VAREJO)"
    elif tem_transf and tem_compra:
        return "🔥 TRANSFERÊNCIA & COMPRA"
    return "📢 OPORTUNIDADE DE PONTOS / VIAGEM"

def enviar_telegram(titulo, link, categoria, programas):
    mensagem = (
        f"<b>{categoria}</b>\n"
        f"🏷️ <i>{programas}</i>\n\n"
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
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro ao disparar mensagem no Telegram: {e}")

def executar():
    agora = obter_horario_brasilia()
    hora_minuto_atual = agora.time()

    inicio_silencio = time(23, 59, 0)
    fim_silencio = time(5, 59, 59)

    if hora_minuto_atual >= inicio_silencio or hora_minuto_atual <= fim_silencio:
        print(f"Modo noturno ativo ({agora.strftime('%H:%M')}). Alertas silenciados.")
        return

    enviados = carregar_enviados()
    todos_termos = TERMOS_TRANSFERENCIA + TERMOS_COMPRA + TERMOS_VOOS
    novos_enviados = 0

    for url_feed in FEEDS:
        try:
            feed = feedparser.parse(url_feed)
            for entry in feed.entries[:15]:
                titulo = entry.title
                link = entry.link

                if link not in enviados:
                    if any(termo in titulo.lower() for termo in todos_termos):
                        categoria = identificar_tipo(titulo)
                        programas = identificar_programas(titulo)
                        
                        enviar_telegram(titulo, link, categoria, programas)
                        salvar_enviado(link)
                        registrar_historico_csv(agora, categoria, programas, titulo, link)
                        
                        enviados.add(link)
                        novos_enviados += 1
        except Exception as e:
            print(f"Erro ao processar feed {url_feed}: {e}")

    print(f"Execução concluída. {novos_enviados} novos registros gravados no histórico.")

if __name__ == "__main__":
    executar()

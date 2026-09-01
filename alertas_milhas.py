import os
import csv
import re
from datetime import datetime, timezone, timedelta, time
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

# 1. Termos de Transferência Bonificada
TERMOS_TRANSFERENCIA = [
    "transferência", "transfira", "transferir", "bônus", "% de bônus", 
    "bonificada", "bonificação", "bonificados", "pontos bônus", "milhas bônus",
    "conversão bonificada", "converta", "pontos extras", "milhas extras"
]

# 2. Termos de Compras no Varejo (Pontos por R$)
TERMOS_COMPRA_VAREJO = [
    "pontos por real", "pontos por r$", "pontos/r$", "compre e ganhe", 
    "compre e pontue", "acumule pontos", "pts por real", "pts/real",
    "pontos a cada real", "pts a cada real", "milhas por real", "milhas por r$"
]

# Filtro restrito: Apenas Livelo e C6 Átomos
MEUS_PROGRAMAS_ORIGEM = {
    "livelo": ("🩷 LIVELO", ["livelo"]),
    "atomos": ("⚫ C6 ÁTOMOS", ["átomos", "atomos", "c6 bank", "c6"])
}

# Outros bancos para descarte de promoções exclusivas que não te atendem
OUTROS_BANCOS_IGNORAR = [
    "esfera", "santander", "itaú", "itau", "iupp", "brb", "curtaí", 
    "curtai", "coopera", "sicoob", "inter loop", "nubank", "caixa"
]

# Companhias Aéreas e Parceiros de Destino
COMPANHIAS_DESTINO = {
    "latam": ("🔴 LATAM PASS", ["latam", "latam pass"]),
    "smiles": ("🟠 SMILES", ["smiles", "gol"]),
    "azul": ("🔵 AZUL FIDELIDADE", ["azul", "tudoazul", "azul fidelidade"]),
    "tap": ("⚪ TAP MILES&GO", ["tap miles", "miles&go", "tap"]),
    "accor": ("🏨 ALL ACCOR", ["all accor", "accor"])
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

def registrar_historico_csv(data_hora, categoria, origens, destinos, detalhe, titulo, link):
    arquivo_novo = not os.path.exists(ARQUIVO_HISTORICO_CSV)

    with open(ARQUIVO_HISTORICO_CSV, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        if arquivo_novo:
            writer.writerow(["Data", "Hora", "Categoria", "Origem", "Destino", "Bonus_Multiplicador", "Titulo", "Link"])
        
        writer.writerow([
            data_hora.strftime("%d/%m/%Y"),
            data_hora.strftime("%H:%M:%S"),
            categoria,
            origens,
            destinos,
            detalhe,
            titulo,
            link
        ])

def verificar_relevancia(texto_lower):
    # Se mencionar Livelo ou C6 Átomos diretamente, é aprovado
    tem_meu_programa = any(
        any(sin in texto_lower for sin in dados[1]) 
        for dados in MEUS_PROGRAMAS_ORIGEM.values()
    )
    if tem_meu_programa:
        return True

    # Se for uma promoção exclusiva de outro banco (ex: Esfera, Itaú), descarta
    if any(banco in texto_lower for banco in OUTROS_BANCOS_IGNORAR):
        return False

    # Se for promoção genérica para "todos os bancos" ou das aéreas sem banco específico
    termos_genericos = ["todos os bancos", "bancos participantes", "demais bancos", "cartões de crédito"]
    if any(tg in texto_lower for tg in termos_genericos):
        return True

    # Se mencionar companhia aérea e bônus sem citar banco exclusivo, aceita
    tem_aerea = any(
        any(sin in texto_lower for sin in dados[1]) 
        for dados in COMPANHIAS_DESTINO.values()
    )
    tem_bonus = any(tb in texto_lower for tb in TERMOS_TRANSFERENCIA)
    return tem_aerea and tem_bonus

def extrair_origem_destino(texto):
    texto_lower = texto.lower()
    
    origens_encontradas = []
    for chave, (tag_nome, sinonimos) in MEUS_PROGRAMAS_ORIGEM.items():
        if any(s in texto_lower for s in sinonimos):
            origens_encontradas.append(tag_nome)
            
    destinos_encontrados = []
    for chave, (tag_nome, sinonimos) in COMPANHIAS_DESTINO.items():
        if any(s in texto_lower for s in sinonimos):
            destinos_encontrados.append(tag_nome)
            
    str_origem = " | ".join(origens_encontradas) if origens_encontradas else "🩷 LIVELO / ⚫ ÁTOMOS (Ou Todos)"
    str_destino = " | ".join(destinos_encontrados) if destinos_encontrados else "Companhia Aérea / Parceiro"
    
    return str_origem, str_destino

def classificar_oferta(texto):
    texto_lower = texto.lower()
    tem_transf = any(t in texto_lower for t in TERMOS_TRANSFERENCIA)
    tem_compra = any(t in texto_lower for t in TERMOS_COMPRA_VAREJO)

    if tem_transf and not tem_compra:
        return "🔄 TRANSFERÊNCIA BONIFICADA"
    elif tem_compra and not tem_transf:
        return "🛍️ COMPRA BONIFICADA (PONTOS POR REAL)"
    elif tem_transf and tem_compra:
        return "🔥 TRANSFERÊNCIA & COMPRA"
    return None

def extrair_bonus_ou_multiplicador(texto):
    match_bonus = re.search(r'(\d+)\s*%', texto)
    match_pts = re.search(r'(\d+)\s*(?:pontos|pts)', texto, re.IGNORECASE)
    
    if match_bonus:
        return f"Até {match_bonus.group(1)}% de bônus"
    elif match_pts:
        return f"{match_pts.group(1)} pontos por R$ 1"
    return "Consulte o regulamento"

def enviar_telegram(titulo, link, categoria, origem, destino, bonus_info):
    if "TRANSFERÊNCIA" in categoria:
        bloco_detalhes = (
            f"🏦 <b>Origem:</b> {origem}\n"
            f"✈️ <b>Destino:</b> {destino}\n"
            f"🎁 <b>Bônus:</b> {bonus_info}\n"
        )
    else:
        bloco_detalhes = (
            f"🏷️ <b>Programa:</b> {origem}\n"
            f"⚡ <b>Multiplicador:</b> {bonus_info}\n"
        )

    mensagem = (
        f"<b>{categoria}</b>\n\n"
        f"{bloco_detalhes}\n"
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

    # Silêncio estrito entre 23:59:00 e 05:59:59 (Horário de Brasília)
    inicio_silencio = time(23, 59, 0)
    fim_silencio = time(5, 59, 59)

    if hora_minuto_atual >= inicio_silencio or hora_minuto_atual <= fim_silencio:
        print(f"Modo noturno ativo ({agora.strftime('%H:%M')}). Alertas silenciados.")
        return

    enviados = carregar_enviados()
    novos_enviados = 0

    for url_feed in FEEDS:
        try:
            feed = feedparser.parse(url_feed)
            for entry in feed.entries[:15]:
                titulo = entry.title
                link = entry.link

                if link not in enviados:
                    categoria = classificar_oferta(titulo)
                    
                    # Checa se é transferência/compra e se envolve estritamente Livelo/Átomos
                    if categoria and verificar_relevancia(titulo.lower()):
                        origem, destino = extrair_origem_destino(titulo)
                        bonus_info = extrair_bonus_ou_multiplicador(titulo)
                        
                        enviar_telegram(titulo, link, categoria, origem, destino, bonus_info)
                        salvar_enviado(link)
                        registrar_historico_csv(agora, categoria, origem, destino, bonus_info, titulo, link)
                        
                        enviados.add(link)
                        novos_enviados += 1
        except Exception as e:
            print(f"Erro ao processar feed {url_feed}: {e}")

    print(f"Execução concluída. {novos_enviados} novos alertas processados.")

if __name__ == "__main__":
    executar()

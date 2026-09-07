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

# 3. Termos Estratégicos de Clubes de Pontos e Assinaturas Rentáveis
TERMOS_CLUBES_PONTOS = [
    "clube livelo", "clube smiles", "clube azul", "clube c6", 
    "assine o clube", "assinatura do clube", "bônus no clube", 
    "upgrade de clube", "milhas no clube", "pontos no clube",
    "adesão ao clube", "promoção do clube"
]

# 4. Outras ações fáceis e gratuitas relevantes (sem assinaturas comerciais)
TERMOS_MILHAS_FACEIS = [
    "cadastre-se", "cadastro", "inscreva-se", "registro",
    "grátis", "gratuito", "sem custo", "sem gastar", "sem compra",
    "ganhe pontos", "ganhe milhas", "receba pontos", "receba milhas", 
    "bônus de cadastro", "pontos de boas-vindas", "milhas de boas-vindas",
    "missão", "desafio", "campanha", "ative a oferta", "ative a promoção",
    "baixe o aplicativo", "instale o aplicativo", "faça login", "primeiro acesso",
    "pesquisa", "responda", "questionário", "confirme seus dados"
]

# Termos que devem ser ignorados para evitar ruído de varejo
TERMOS_BLOQUEADOS = [
    "streaming", "revista", "jornal", "vinho", "café", "pet", "curso", 
    "academia", "seguro", "consórcio", "cartão de crédito sem anuidade"
]

# Mapeamento de Programas e Ícones Visuais
PROGRAMAS = {
    "latam": ("🔴 LATAM PASS", ["latam", "latam pass"]),
    "smiles": ("🟠 SMILES", ["smiles", "gol"]),
    "azul": ("🔵 AZUL FIDELIDADE", ["azul", "tudoazul", "azul fidelidade"]),
    "livelo": ("🩷 LIVELO", ["livelo"]),
    "atomos": ("⚫ C6 ÁTOMOS", ["átomos", "atomos", "c6 bank", "c6"]),
    "esfera": ("🟢 ESFERA", ["esfera", "santander"]),
    "tap": ("⚪ TAP MILES&GO", ["tap miles", "miles&go", "tap"]),
    "accor": ("🏨 ALL ACCOR", ["all accor", "accor"])
}

BANCOS_RESTRITOS_COMPRA = ["livelo", "átomos", "atomos", "c6"]

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

def registrar_historico_csv(data_hora, categoria, programas, detalhe, titulo, link):
    arquivo_novo = not os.path.exists(ARQUIVO_HISTORICO_CSV)

    with open(ARQUIVO_HISTORICO_CSV, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        if arquivo_novo:
            writer.writerow(["Data", "Hora", "Categoria", "Programas", "Detalhe_Extraido", "Titulo", "Link"])
        
        writer.writerow([
            data_hora.strftime("%d/%m/%Y"),
            data_hora.strftime("%H:%M:%S"),
            categoria,
            programas,
            detalhe,
            titulo,
            link
        ])

def identificar_programas(texto):
    texto_lower = texto.lower()
    tags = []
    for chave, (tag_nome, sinonimos) in PROGRAMAS.items():
        if any(s in texto_lower for s in sinonimos):
            tags.append(tag_nome)
    return " | ".join(tags) if tags else "🌐 PROGRAMAS / PARCEIROS"

def classificar_e_validar(titulo):
    texto_lower = titulo.lower()
    
    # Se contiver termos bloqueados de serviços irrelevantes, descarta imediatamente
    if any(bloco in texto_lower for bloco in TERMOS_BLOQUEADOS):
        return None

    tem_transf = any(t in texto_lower for t in TERMOS_TRANSFERENCIA)
    tem_compra = any(c in texto_lower for c in TERMOS_COMPRA_VAREJO)
    tem_clube = any(cl in texto_lower for cl in TERMOS_CLUBES_PONTOS)
    tem_facil = any(f in texto_lower for f in TERMOS_MILHAS_FACEIS)

    # 1. Clube de Pontos e Assinaturas Estratégicas (Prioridade para Arbitragem)
    if tem_clube:
        return "🧩 CLUBE DE PONTOS & ASSINATURA ESTRATÉGICA"

    # 2. Transferência Bonificada
    if tem_transf and not tem_compra:
        return "🔄 TRANSFERÊNCIA BONIFICADA"

    # 3. Compra Bonificada (Restrita a Livelo / C6 Átomos)
    if tem_compra and not tem_transf:
        is_meu_banco = any(b in texto_lower for b in BANCOS_RESTRITOS_COMPRA)
        if is_meu_banco:
            return "🛍️ COMPRA BONIFICADA (PONTOS POR REAL)"
        else:
            return None

    # 4. Ações Gratuitas e Milhas Fáceis
    if tem_facil and not tem_compra:
        return "🎁 MILHAS FÁCEIS & BÔNUS GRATUITOS"

    return None

def extrair_detalhe(texto):
    match_bonus = re.search(r'(\d+)\s*%', texto)
    match_pts = re.search(r'(\d+)\s*(?:pontos|pts)', texto, re.IGNORECASE)
    
    if match_bonus:
        return f"Até {match_bonus.group(1)}% de bônus / Desconto"
    elif match_pts:
        return f"{match_pts.group(1)} pontos por R$ 1 / Adesão"
    return "Oportunidade Estratégica"

def enviar_telegram(titulo, link, categoria, programas, detalhe):
    mensagem = (
        f"<b>{categoria}</b>\n"
        f"🏷️ <i>{programas}</i>\n"
        f"🎁 <b>Detalhe:</b> {detalhe}\n\n"
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
    novos_enviados = 0

    for url_feed in FEEDS:
        try:
            feed = feedparser.parse(url_feed)
            for entry in feed.entries[:15]:
                titulo = entry.title
                link = entry.link

                if link not in enviados:
                    categoria = classificar_e_validar(titulo)
                    
                    if categoria:
                        programas = identificar_programas(titulo)
                        detalhe = extrair_detalhe(titulo)
                        
                        enviar_telegram(titulo, link, categoria, programas, detalhe)
                        salvar_enviado(link)
                        registrar_historico_csv(agora, categoria, programas, detalhe, titulo, link)
                        
                        enviados.add(link)
                        novos_enviados += 1
        except Exception as e:
            print(f"Erro ao processar feed {url_feed}: {e}")

    print(f"Execução concluída. {novos_enviados} novos alertas processados.")

if __name__ == "__main__":
    executar()

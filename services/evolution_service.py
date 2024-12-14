import os
import logging
import random
import requests
from datetime import datetime, timedelta
import openai
from database import (
    get_status, update_status, record_closure_time,
    get_daily_stats, get_weather_status, update_weather,
    redis_client
)
from config import BR_TIMEZONE, PICOS, WEATHER_API_KEY, CITY_ID

logger = logging.getLogger(__name__)
openai.api_key = os.getenv('OPENAI_API_KEY')

# Controle de publicidade
ultima_publicidade = None
INTERVALO_MINIMO_PUBLICIDADE = timedelta(minutes=30)

def get_current_time():
    """Retorna a hora atual no fuso horário do Brasil"""
    return datetime.now(BR_TIMEZONE)

def is_horario_pico():
    """Verifica se é horário de pico"""
    hora_atual = get_current_time().hour
    return any(inicio <= hora_atual <= fim for inicio, fim in PICOS.values())

def update_weather_info():
    """Atualiza informações do clima"""
    if not WEATHER_API_KEY:
        return None
        
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?id={CITY_ID}&appid={WEATHER_API_KEY}&units=metric&lang=pt_br"
        response = requests.get(url)
        data = response.json()
        
        if response.status_code == 200:
            condicao = data['weather'][0]['description']
            temp = data['main']['temp']
            
            alerta = None
            if 'rain' in data or 'thunderstorm' in data:
                alerta = "🌧️ Chuva na região - Dirija com cuidado!"
            elif temp > 35:
                alerta = "🌡️ Temperatura muito alta - Hidrate-se!"
            
            update_weather(condicao, alerta)
            return {'condicao': condicao, 'alerta': alerta}
            
    except Exception as e:
        logger.error(f"Erro ao atualizar clima: {e}")
    return None

def get_mensagem_publicidade():
    """Retorna uma mensagem de publicidade aleatória"""
    mensagens = [
        "☕ *PRADO CAFÉ*\n📍 Quarto Centenário\n• Café fresquinho\n• Salgados na hora\n📱 (44) 9164-7725",
        "🥐 *PRADO CAFÉ*\n• Cafés especiais\n• Lanches deliciosos\n📱 (44) 9164-7725",
        "⏰ *PRADO CAFÉ*\n• Café premium\n• Ambiente família\n📱 (44) 9164-7725"
    ]
    return random.choice(mensagens)

def pode_enviar_publicidade():
    """Verifica se pode enviar publicidade"""
    global ultima_publicidade
    agora = get_current_time()
    
    if not ultima_publicidade or (agora - ultima_publicidade) > INTERVALO_MINIMO_PUBLICIDADE:
        ultima_publicidade = agora
        return True
    return False

def get_time_since_update(ultima_atualizacao):
    """Calcula tempo desde última atualização"""
    agora = get_current_time()
    ultima = datetime.strptime(ultima_atualizacao, '%d/%m/%Y %H:%M')
    ultima = BR_TIMEZONE.localize(ultima)
    
    minutos = int((agora - ultima).total_seconds() / 60)
    
    if minutos < 60:
        return f"{minutos} minutos atrás"
    elif minutos < 1440:
        return f"{minutos // 60} horas atrás"
    else:
        return f"{minutos // 1440} dias atrás"

def get_current_status():
    """Retorna status atual detalhado da rodovia"""
    status, ultima_atualizacao = get_status('CENTER')
    tempo_desde = get_time_since_update(ultima_atualizacao)
    
    if int(tempo_desde.split()[0]) > 60:
        return (
            "⚠️ *Status Desatualizado*\n"
            f"Última atualização foi há {tempo_desde}\n"
            "Use *!alterna* para atualizar o status"
        )
    
    mensagem = (
        f"{'🚫' if status == 'FECHADO' else '✅'} *QC está {status}*\n"
        f"{'⏱ Tempo médio: 40 minutos' if status == 'FECHADO' else ''}\n"
        f"🕒 Atualizado: {ultima_atualizacao} ({tempo_desde})"
    ).strip()
    
    if is_horario_pico():
        mensagem += "\n⚠️ *Atenção*: Horário de pico!"
        
    weather = get_weather_status()
    if weather and weather.get('alerta'):
        mensagem += f"\n{weather['alerta']}"
        
    if pode_enviar_publicidade():
        mensagem += f"\n\n{get_mensagem_publicidade()}"
        
    return mensagem

def toggle_status(nome_remetente):
    """Alterna o status da rodovia"""
    status_atual, ultima_atualizacao = get_status('CENTER')
    novo_status = 'ABERTO' if status_atual == 'FECHADO' else 'FECHADO'
    
    if status_atual == 'FECHADO':
        try:
            ultima = datetime.strptime(ultima_atualizacao, '%d/%m/%Y %H:%M')
            ultima = BR_TIMEZONE.localize(ultima)
            tempo_fechado = int((get_current_time() - ultima).total_seconds() / 60)
            record_closure_time('CENTER', tempo_fechado)
        except Exception as e:
            logger.error(f"Erro ao registrar tempo: {e}")
    
    update_status('CENTER', novo_status)
    update_status('GOIO', 'ABERTO' if novo_status == 'FECHADO' else 'FECHADO')
    
    return get_current_status()

def get_stats_message():
    """Retorna estatísticas do dia"""
    stats = get_daily_stats()
    return (
        "📊 *Estatísticas do Dia*\n"
        f"• Fechamentos: {stats['total_fechamentos']}\n"
        f"• Tempo médio: {stats['tempo_medio']} min\n"
        f"• Pico: {stats['horario_pico']}"
    )

def get_mensagem_ajuda():
    """Retorna lista de comandos disponíveis"""
    return (
        "🚦 *Sistema PARE/SIGA*\n\n"
        "*!status* - Ver situação atual\n"
        "*!alterna* - Atualizar status\n"
        "*!stats* - Ver estatísticas\n"
        "*!ajuda* - Ver comandos"
    )

def process_command(mensagem, nome_remetente):
    """Processa comandos com !"""
    if mensagem in ['!sim', '!nao']:
        return process_confirmation(mensagem, nome_remetente)
        
    comandos = {
        '!status': get_current_status,
        '!alterna': lambda: toggle_status(nome_remetente),
        '!stats': get_stats_message,
        '!ajuda': get_mensagem_ajuda
    }
    return comandos.get(mensagem, lambda: None)()

def process_message(data):
    """Processa mensagens recebidas"""
    try:
        mensagem = data.get('text', '').lower()
        nome_remetente = data.get('sender', {}).get('pushName', 'Usuário')
        
        logger.info(f"Mensagem: {mensagem} | Remetente: {nome_remetente}")
        
        update_weather_info()
        
        if mensagem.startswith('!'):
            return process_command(mensagem, nome_remetente)
            
        return process_ai_message(mensagem, nome_remetente)
            
    except Exception as e:
        logger.error(f"Erro: {str(e)}")
        return "❌ Erro ao processar mensagem"

def process_ai_message(mensagem, nome_remetente):
    """Processa mensagens usando GPT e funções existentes"""
    try:
        status_atual, ultima_atualizacao = get_status('CENTER')
        
        system_prompt = """
        Você é um assistente que monitora o sistema PARE/SIGA na PR-180 entre Quarto Centenário e Goioerê.

        FUNÇÕES DISPONÍVEIS:
        1. get_current_status() - Retorna status atual
        2. update_road_status(status_type) - Atualiza status da rodovia
           - status_type pode ser: "LIBERACAO" ou "FECHAMENTO"
        3. get_stats_message() - Retorna estatísticas
        4. get_mensagem_ajuda() - Retorna comandos

        REGRAS PARA ALTERAÇÃO DE STATUS:
        - Palavras que indicam LIBERACAO:
          "liberou", "abriu", "tá passando", "está liberado"
        - Palavras que indicam FECHAMENTO:
          "fechou", "parou", "tá fechado", "está parado"
        
        IMPORTANTE:
        - Só atualize o status se a mensagem for clara e direta
        - Em caso de dúvida, sugira usar !alterna
        - Confirme com o usuário antes de alterar
        """

        user_context = f"""
        SITUAÇÃO ATUAL:
        Status: {get_current_status()}
        Última atualização: {ultima_atualizacao}
        
        MENSAGEM: {nome_remetente}: "{mensagem}"
        """

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_context}
            ],
            temperature=0.7,
            max_tokens=150,
            function_call="auto",
            functions=[
                {
                    "name": "update_road_status",
                    "description": "Atualiza o status da rodovia",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "status_type": {
                                "type": "string",
                                "enum": ["LIBERACAO", "FECHAMENTO"]
                            },
                            "confirmacao": {
                                "type": "string",
                                "description": "Mensagem pedindo confirmação"
                            }
                        },
                        "required": ["status_type", "confirmacao"]
                    }
                },
                {
                    "name": "get_current_status",
                    "description": "Retorna status atual da rodovia",
                    "parameters": {"type": "object", "properties": {}}
                },
                {
                    "name": "get_stats_message",
                    "description": "Retorna estatísticas do dia",
                    "parameters": {"type": "object", "properties": {}}
                },
                {
                    "name": "get_mensagem_ajuda",
                    "description": "Retorna lista de comandos",
                    "parameters": {"type": "object", "properties": {}}
                },
                {
                    "name": "is_horario_pico",
                    "description": "Verifica se é horário de pico",
                    "parameters": {"type": "object", "properties": {}}
                },
                {
                    "name": "get_weather_status",
                    "description": "Retorna condições climáticas",
                    "parameters": {"type": "object", "properties": {}}
                }
            ]
        )
        
        if response.choices[0].message.get("function_call"):
            func_name = response.choices[0].message["function_call"]["name"]
            
            if func_name == "update_road_status":
                args = json.loads(response.choices[0].message["function_call"]["arguments"])
                status_type = args["status_type"]
                confirmacao = args["confirmacao"]
                
                # Registra a intenção de alteração
                register_status_intent(nome_remetente, status_type, mensagem)
                
                # Retorna mensagem pedindo confirmação
                return (
                    f"{confirmacao}\n\n"
                    f"Para confirmar, responda com *!sim*\n"
                    f"Para cancelar, responda com *!nao*"
                )
            
            # ... processamento de outras funções ...
            
        return get_current_status()
        
    except Exception as e:
        logger.error(f"Erro IA: {e}")
        return None

def register_status_intent(nome_remetente, status_type, mensagem_original):
    """Registra intenção de alteração de status"""
    redis_client.setex(
        f"status_intent:{nome_remetente}",
        300,  # expira em 5 minutos
        json.dumps({
            "status_type": status_type,
            "mensagem": mensagem_original,
            "timestamp": get_current_time().strftime('%Y-%m-%d %H:%M:%S')
        })
    )

def process_confirmation(mensagem, nome_remetente):
    """Processa confirmação de alteração de status"""
    intent_key = f"status_intent:{nome_remetente}"
    intent_data = redis_client.get(intent_key)
    
    if not intent_data:
        return "⚠️ Nenhuma alteração pendente para confirmar"
        
    intent = json.loads(intent_data)
    redis_client.delete(intent_key)
    
    if mensagem == '!sim':
        novo_status = 'ABERTO' if intent["status_type"] == "LIBERACAO" else 'FECHADO'
        update_status('CENTER', novo_status)
        update_status('GOIO', 'FECHADO' if novo_status == 'ABERTO' else 'ABERTO')
        return get_current_status()
    else:
        return "❌ Alteração cancelada"
import os
import json
import logging
import random
import requests
import time
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

# Chave para armazenar última atualização do clima no Redis
WEATHER_UPDATE_KEY = 'last_weather_update'

# Chaves Redis para controle de concorrência
STATUS_LOCK_KEY = 'status_lock'
CONFIRMATION_KEY = 'confirmation_{user}'
LAST_ACTION_KEY = 'last_action_{user}'

def get_current_time():
    """Retorna a hora atual no fuso horário do Brasil"""
    return datetime.now(BR_TIMEZONE)

def is_horario_pico():
    """Verifica se é horário de pico"""
    hora_atual = get_current_time().hour
    return any(inicio <= hora_atual <= fim for inicio, fim in PICOS.values())

def acquire_lock(key, timeout=30):
    """Tenta adquirir um lock no Redis"""
    return redis_client.set(key, '1', ex=timeout, nx=True)

def release_lock(key):
    """Libera um lock no Redis"""
    redis_client.delete(key)

def toggle_status(nome_remetente):
    """
    Alterna o status da rodovia com proteção contra condições de corrida
    """
    try:
        # Tenta adquirir o lock
        if not acquire_lock(STATUS_LOCK_KEY, timeout=30):
            return (
                " ⚠️ *Atenção*\n"
                "Outra pessoa está alterando o status.\n"
                "⏳ Aguarde alguns segundos e tente novamente."
            )
        
        try:
            status_atual, ultima_atualizacao = get_status('CENTER')
            ultima = datetime.strptime(ultima_atualizacao, '%d/%m/%Y %H:%M')
            ultima = BR_TIMEZONE.localize(ultima)
            
            # Verificar última ação do usuário
            last_action = redis_client.get(LAST_ACTION_KEY.format(user=nome_remetente))
            if last_action:
                last_action_time = float(last_action)
                if (time.time() - last_action_time) < 5:  # 5 segundos entre ações
                    return (
                        " ⏳ *Aguarde*\n"
                        "Você precisa esperar alguns segundos\n"
                        "antes de tentar novamente."
                    )
            
            # Registrar ação do usuário
            redis_client.set(LAST_ACTION_KEY.format(user=nome_remetente), 
                           str(time.time()), 
                           ex=300)  # Expira em 5 minutos
            
            tempo_desde = int((get_current_time() - ultima).total_seconds())
            
            if tempo_desde < 30:
                # Registrar intenção de confirmação
                redis_client.set(
                    CONFIRMATION_KEY.format(user=nome_remetente),
                    json.dumps({
                        'action': 'toggle',
                        'timestamp': time.time(),
                        'current_status': status_atual
                    }),
                    ex=300  # Expira em 5 minutos
                )
                
                return (
                    " ⚠️ *Confirmação Necessária*\n\n"
                    "A última mudança foi há menos de 30 segundos.\n"
                    "Tem certeza que quer alterar o status?\n\n"
                    "📱 Responda com:\n"
                    "➡️ *!sim* - Para confirmar\n"
                    "➡️ *!nao* - Para cancelar"
                )
            
            if status_atual == ESTADO_ABERTO:
                update_status('CENTER', ESTADO_FECHADO)
                update_status('GOIO', ESTADO_ABERTO)
                
                if tempo_desde >= 60:
                    record_closure_time('CENTER', tempo_desde)
                    
                return (
                    " 🔄 *Status Atualizado*\n"
                    "🟢 Goioerê PASSANDO\n"
                    "❌ QC PARADO"
                )
                
            elif status_atual == ESTADO_FECHADO:
                update_status('CENTER', ESTADO_ABERTO)
                update_status('GOIO', ESTADO_FECHADO)
                
                if tempo_desde >= 60:
                    record_closure_time('GOIO', tempo_desde)
                    
                return (
                    " 🔄 *Status Atualizado*\n"
                    "🟢 QC PASSANDO\n"
                    "❌ Goioerê PARADO"
                )
                
            else:
                logger.error(f"Status inválido: {status_atual}")
                return (
                    " ❌ *Erro*\n"
                    "Não foi possível alterar o status.\n"
                    "Por favor, tente novamente."
                )
                
        finally:
            release_lock(STATUS_LOCK_KEY)
            
    except Exception as e:
        logger.error(f"Erro ao alternar status: {e}")
        # Garantir que o lock seja liberado mesmo em caso de erro
        release_lock(STATUS_LOCK_KEY)
        return (
            " ❌ *Erro*\n"
            "Não foi possível alterar o status.\n"
            "Por favor, tente novamente."
        )

def get_mensagem_publicidade():
    """Retorna uma mensagem de publicidade aleatória"""
    mensagens = [
        " *PRADO CAFÉ*\n Quarto Centenário\n• Café fresquinho\n• Salgados na hora\n (44) 9164-7725",
        " *PRADO CAFÉ*\n • Cafés especiais\n• Lanches deliciosos\n (44) 9164-7725",
        " *PRADO CAFÉ*\n • Café premium\n• Ambiente família\n (44) 9164-7725"
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
            " ⚠️ *Status Desatualizado*\n"
            f"Última atualização: {tempo_desde}\n\n"
            "📱 Para atualizar, use:\n"
            "➡️ *!alterna*"
        )
    
    # Obter informações do clima
    weather = get_weather_status()
    weather_info = ""
    if weather:
        weather_info = f"\n\n🌤️ *Clima*: {weather['condicao']}"
        if weather.get('alerta'):
            weather_info += f"\n⚠️ {weather['alerta']}"
    
    # Status principal
    if status == ESTADO_ABERTO:
        mensagem = (
            " 🟢 *QC PASSANDO* 🟢\n"
            f"↪️ Última atualização: {tempo_desde}\n"
            "❌ Goioerê PARADO"
        )
    else:
        mensagem = (
            " 🟢 *GOIOERÊ PASSANDO* 🟢\n"
            f"↪️ Última atualização: {tempo_desde}\n"
            "❌ QC PARADO"
        )
    
    return mensagem + weather_info

def get_mensagem_ajuda():
    """Retorna lista de comandos disponíveis"""
    return (
        " *Sistema PARE/SIGA* 🚦\n\n"
        "📱 *Comandos Disponíveis*\n"
        "➡️ *!status* - Ver situação atual\n"
        "➡️ *!alterna* - Atualizar status\n"
        "➡️ *!stats* - Ver estatísticas\n"
        "➡️ *!ajuda* - Ver comandos\n\n"
        "💡 _Você também pode escrever normalmente sobre a situação do trânsito_"
    )

# Constantes para estados
ESTADO_ABERTO = 'ABERTO'
ESTADO_FECHADO = 'FECHADO'
ESTADO_TRANSICAO = 'TRANSICAO'  # Novo estado para quando ambos estão fechados

INTENT_TYPES = {
    "LIBERACAO": "liberação",
    "FECHAMENTO": "fechamento",
    "TRANSICAO_COMPLETA": "transição completa"  # Nova intenção
}

def process_confirmation(mensagem, nome_remetente):
    """Processa confirmações com proteção contra timing issues"""
    try:
        # Verificar se existe uma confirmação pendente
        confirmation_data = redis_client.get(CONFIRMATION_KEY.format(user=nome_remetente))
        if not confirmation_data:
            return " Não há confirmação pendente para você."
            
        confirmation = json.loads(confirmation_data)
        
        # Verificar se a confirmação não expirou (5 minutos)
        if (time.time() - confirmation['timestamp']) > 300:
            redis_client.delete(CONFIRMATION_KEY.format(user=nome_remetente))
            return " ⚠️ Confirmação expirada. Por favor, tente a ação novamente."
            
        if mensagem.lower() == '!sim':
            # Limpar confirmação
            redis_client.delete(CONFIRMATION_KEY.format(user=nome_remetente))
            
            if confirmation['action'] == 'toggle':
                return toggle_status(nome_remetente)
        else:
            # Limpar confirmação
            redis_client.delete(CONFIRMATION_KEY.format(user=nome_remetente))
            return " Operação cancelada."
            
    except Exception as e:
        logger.error(f"Erro ao processar confirmação: {e}")
        return " Erro ao processar confirmação. Por favor, tente novamente."

def update_weather_info():
    """Atualiza informações do clima com retry e fallback"""
    if not WEATHER_API_KEY:
        return None
        
    max_retries = 3
    retry_delay = 1  # segundos
    
    for attempt in range(max_retries):
        try:
            url = f"http://api.openweathermap.org/data/2.5/weather?id={CITY_ID}&appid={WEATHER_API_KEY}&units=metric&lang=pt_br"
            response = requests.get(url, timeout=5)  # timeout de 5 segundos
            
            if response.status_code == 200:
                data = response.json()
                
                condicao = data['weather'][0]['description']
                temp = data['main']['temp']
                
                alerta = None
                if 'rain' in data or 'thunderstorm' in data:
                    alerta = " Chuva na região - Dirija com cuidado!"
                elif temp > 35:
                    alerta = " Temperatura muito alta - Hidrate-se!"
                elif temp < 10:
                    alerta = " Temperatura muito baixa - Cuidado com a pista!"
                
                # Cache dos dados do clima no Redis
                weather_data = {
                    'condicao': condicao,
                    'temp': temp,
                    'alerta': alerta,
                    'timestamp': time.time()
                }
                redis_client.set('weather_cache', 
                               json.dumps(weather_data),
                               ex=1800)  # Cache por 30 minutos
                
                return weather_data
                
        except requests.RequestException as e:
            logger.error(f"Tentativa {attempt + 1} falhou: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2  # Backoff exponencial
            continue
            
        except Exception as e:
            logger.error(f"Erro ao atualizar clima: {e}")
            break
            
    # Em caso de falha, tentar usar cache
    cached_weather = redis_client.get('weather_cache')
    if cached_weather:
        return json.loads(cached_weather)
        
    return None

def get_stats_message():
    """Retorna estatísticas do dia"""
    stats = get_daily_stats()
    return (
        " *Estatísticas do Dia*\n"
        f"• Fechamentos: {stats['total_fechamentos']}\n"
        f"• Tempo médio: {stats['tempo_medio']} min\n"
        f"• Pico: {stats['horario_pico']}"
    )

def process_message(data):
    """Processa mensagens recebidas"""
    try:
        logger.info(f"Dados recebidos: {json.dumps(data, indent=2)}")
        
        # Extrair mensagem do objeto data
        mensagem = ''
        nome_remetente = 'Usuário'
        
        if data.get('event') == 'messages.upsert':
            message_data = data.get('data', {})
            if message_data.get('message', {}).get('conversation'):
                mensagem = message_data['message']['conversation'].strip()
                nome_remetente = message_data.get('pushName', 'Usuário')
        
        logger.info(f"Processando mensagem: '{mensagem}' de {nome_remetente}")
        
        if not mensagem:
            return None
            
        # Verificar se é um comando
        if mensagem.startswith('!'):
            return process_command(mensagem, nome_remetente)
            
        # Processar com GPT
        return process_ai_message(mensagem, nome_remetente)
        
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}", exc_info=True)
        return None

def process_ai_message(mensagem, nome_remetente):
    """Processa mensagens usando GPT para entender a intenção do usuário"""
    try:
        # Avaliar relevância da mensagem
        relevance_prompt = f"""Avalie a relevância desta mensagem para um sistema de controle de trânsito:
        Mensagem: "{mensagem}"
        
        Classifique em uma escala de 0 a 1, onde:
        - 0 a 0.5: Irrelevante (conversas não relacionadas)
        - 0.5 a 0.7: Parcialmente relevante (pode ter relação com trânsito)
        - 0.7 a 1.0: Muito relevante (informação direta sobre trânsito)
        
        Categorize em: status, tempo, clima, pergunta, feedback
        
        Retorne em formato JSON:
        {{
            "relevance_score": float,
            "category": string,
            "explanation": string
        }}"""

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # Voltando para um modelo mais estável
            messages=[
                {"role": "system", "content": "Você é um assistente que analisa mensagens sobre trânsito."},
                {"role": "user", "content": relevance_prompt}
            ],
            response_format={ "type": "json_object" }
        )
        
        try:
            result = json.loads(response.choices[0].message.content)
            logger.info(f"Análise GPT: {json.dumps(result, indent=2)}")
            
            if result['relevance_score'] < 0.5:
                return None
                
            if result['relevance_score'] >= 0.7:
                # Processar mensagem relevante
                intent_prompt = f"""Analise a seguinte mensagem sobre trânsito:
                Mensagem: "{mensagem}"
                Remetente: {nome_remetente}
                
                Determine a intenção do usuário e retorne em formato JSON:
                {{
                    "intent": string (status|update|query|other),
                    "action": string,
                    "response": string
                }}"""
                
                intent_response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",  # Voltando para um modelo mais estável
                    messages=[
                        {"role": "system", "content": "Você é um assistente que analisa mensagens sobre trânsito."},
                        {"role": "user", "content": intent_prompt}
                    ],
                    response_format={ "type": "json_object" }
                )
                
                intent_result = json.loads(intent_response.choices[0].message.content)
                logger.info(f"Intenção detectada: {json.dumps(intent_result, indent=2)}")
                
                if intent_result['intent'] == 'status':
                    return get_current_status()
                elif intent_result['intent'] == 'query':
                    return intent_result['response']
                    
                return None
                
        except json.JSONDecodeError as e:
            logger.error(f"Erro ao decodificar resposta do GPT: {e}")
            logger.error(f"Resposta recebida: {response.choices[0].message.content}")
            return None
            
    except Exception as e:
        logger.error(f"Erro ao processar mensagem com GPT: {e}")
        return None

def format_detailed_weather(weather):
    """Formata informações detalhadas do clima"""
    if not weather:
        return " Informações do clima não disponíveis"
    
    return (
        f" Condições Atuais:\n"
        f"• Temperatura: {weather.get('temp', 'N/A')}°C\n"
        f"• Condição: {weather.get('condicao', 'N/A')}\n"
        f"{weather.get('alerta', '')}"
    )

def format_simple_weather(weather):
    """Formata informações simples do clima"""
    if not weather:
        return " Clima: informação não disponível"
    
    return f" {weather.get('condicao', '')} {weather.get('alerta', '')}"

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

def process_transition_status(mensagem, nome_remetente):
    """
    Processa mensagens relacionadas ao estado de transição
    quando ambos os lados estão temporariamente fechados
    """
    try:
        # Identificar se é uma mensagem sobre últimos carros passando
        ultimos_carros_patterns = [
            "últimos carros", "ultimos carros",
            "terminando de passar", "quase terminando",
            "falta pouco", "já tá acabando",
            "passou todo mundo", "todos passaram",
            "pista limpa", "não tem mais ninguém"
        ]
        
        status_atual, _ = get_status('CENTER')
        
        # Se estiver em transição e a mensagem indicar que os carros passaram
        if status_atual == ESTADO_TRANSICAO and any(pattern in mensagem.lower() for pattern in ultimos_carros_patterns):
            # Registrar intenção de completar a transição
            register_status_intent(nome_remetente, "TRANSICAO_COMPLETA", mensagem)
            return (
                " Você está confirmando que todos os carros terminaram de passar?\n\n"
                "Para confirmar, responda com *!sim*\n"
                "Para cancelar, responda com *!nao*"
            )
        
        return None
        
    except Exception as e:
        logger.error(f"Erro ao processar transição: {e}")
        return None

def ajustar_tempo_abertura(minutos):
    """
    Ajusta o tempo de abertura com base no feedback dos usuários
    e considera diferentes fatores como horário e fluxo
    """
    try:
        # Verificar se é horário de pico
        is_pico = is_horario_pico()
        
        # Obter condições climáticas
        weather = get_weather_status()
        
        # Definir tempos base de acordo com as condições
        tempo_base = 20  # tempo base em minutos
        if is_pico:
            tempo_base = 25  # aumenta em horário de pico
        
        if weather and weather.get('alerta'):
            tempo_base += 5  # aumenta em condições climáticas adversas
            
        # Ajustar com base no feedback recebido
        tempo_ajustado = (tempo_base + minutos) / 2
        
        # Limites de segurança
        tempo_minimo = 15
        tempo_maximo = 35
        tempo_final = max(tempo_minimo, min(tempo_ajustado, tempo_maximo))
        
        # Registrar o ajuste
        logger.info(
            f"Ajuste de tempo - Base: {tempo_base}, "
            f"Feedback: {minutos}, Final: {tempo_final}"
        )
        
        return tempo_final
        
    except Exception as e:
        logger.error(f"Erro ao ajustar tempo: {e}")
        return None

def should_send_weather_update():
    """Verifica se deve enviar atualização do clima"""
    try:
        last_update = redis_client.get(WEATHER_UPDATE_KEY)
        if not last_update:
            return True
            
        last_update = float(last_update)
        now = datetime.now(BR_TIMEZONE).timestamp()
        
        # Verifica se passaram 30 minutos desde a última atualização
        return (now - last_update) >= 1800  # 30 minutos em segundos
        
    except Exception as e:
        logger.error(f"Erro ao verificar última atualização do clima: {e}")
        return False

def get_weather_message():
    """Retorna mensagem com informações do clima"""
    try:
        weather_info = update_weather_info()
        if weather_info:
            # Atualiza timestamp da última mensagem
            now = datetime.now(BR_TIMEZONE).timestamp()
            redis_client.set(WEATHER_UPDATE_KEY, str(now))
            
            # Formata mensagem do clima
            mensagem = " *Atualização do Clima*\n"
            mensagem += f"• Condição: {weather_info['condicao'].title()}\n"
            
            if weather_info.get('temp'):
                mensagem += f"• Temperatura: {weather_info['temp']}°C\n"
                
            if weather_info.get('alerta'):
                mensagem += f"\n⚠️ {weather_info['alerta']}"
                
            return mensagem
            
    except Exception as e:
        logger.error(f"Erro ao gerar mensagem do clima: {e}")
    return None

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
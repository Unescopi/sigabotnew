import os
import json
import logging
import re
import time
import requests
from datetime import datetime, timedelta
import pytz
import random
import openai
from database import (
    get_status, update_status, record_closure_time,
    get_daily_stats, get_weather_status, update_weather,
    redis_client
)
from config import (
    BR_TIMEZONE, PICOS, WEATHER_API_KEY, CITY_ID,
    GROUP_ID, SERVER_URL, INSTANCE, APIKEY
)

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
            if not status_atual or not ultima_atualizacao:
                logger.error("Erro ao obter status atual")
                return (
                    " ❌ *Erro*\n"
                    "Não foi possível obter o status atual.\n"
                    "Por favor, tente novamente."
                )

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
            
            # Alternar status
            novo_status_center = ESTADO_ABERTO if status_atual == ESTADO_FECHADO else ESTADO_FECHADO
            novo_status_goio = ESTADO_FECHADO if status_atual == ESTADO_FECHADO else ESTADO_ABERTO
            
            try:
                update_status('CENTER', novo_status_center)
                update_status('GOIO', novo_status_goio)
            except Exception as e:
                logger.error(f"Erro ao atualizar status: {e}")
                return (
                    " ❌ *Erro*\n"
                    "Não foi possível atualizar o status.\n"
                    "Por favor, tente novamente."
                )
            
            if tempo_desde >= 60:
                local_fechado = 'CENTER' if novo_status_center == ESTADO_FECHADO else 'GOIO'
                record_closure_time(local_fechado, tempo_desde)
            
            local_passando = 'QC' if novo_status_center == ESTADO_ABERTO else 'Goioerê'
            local_parado = 'Goioerê' if novo_status_center == ESTADO_ABERTO else 'QC'
            
            return (
                " 🔄 *Status Atualizado*\n"
                f"🟢 {local_passando} PASSANDO\n"
                f"❌ {local_parado} PARADO"
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

def notify_group(mensagem, group_id=None):
    """Envia mensagem para o grupo"""
    try:
        if not group_id:
            group_id = GROUP_ID
            
        logger.info(f"Enviando notificação para o grupo {group_id}")
        logger.info(f"Mensagem: {mensagem}")
            
        headers = {
            'Content-Type': 'application/json',
            'apikey': APIKEY
        }
        
        payload = {
            'number': group_id,
            'text': mensagem,
            'options': {
                'delay': 1200,
                'presence': 'composing'
            }
        }
        
        logger.info(f"Fazendo requisição para {SERVER_URL}/message/sendText/{INSTANCE}")
        response = requests.post(
            f"{SERVER_URL}/message/sendText/{INSTANCE}",
            headers=headers,
            json=payload
        )
        
        if response.status_code != 200:
            logger.error(f"Erro ao enviar mensagem para o grupo: {response.text}")
            logger.error(f"Status code: {response.status_code}")
        else:
            logger.info("Notificação enviada com sucesso!")
            
    except Exception as e:
        logger.error(f"Erro ao notificar grupo: {e}", exc_info=True)

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

def process_message(data):
    """Processa mensagens recebidas"""
    try:
        mensagem = data.get('text', '').strip().lower()
        nome_remetente = data.get('sender', {}).get('pushName', 'Usuário')
        
        # Ignorar mensagens vazias
        if not mensagem:
            return None
            
        # Processar comandos
        if mensagem.startswith('!'):
            return process_command(mensagem, nome_remetente)
            
        # Processar confirmações
        if mensagem in ['!sim', '!nao']:
            return process_confirmation(mensagem, nome_remetente)
            
        # Ignorar outras mensagens
        return None
            
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")
        return (
            " ❌ *Erro*\n"
            "Ocorreu um erro ao processar sua mensagem.\n"
            "Por favor, tente novamente."
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

def get_status(local):
    """Retorna o status de um local específico"""
    try:
        # Obter status atual
        status_atual = redis_client.get("status_atual")
        if status_atual:
            status = json.loads(status_atual)
        else:
            status = {}
            
        # Obter última atualização
        ultima_atualizacao = redis_client.get("ultima_atualizacao")
        if not ultima_atualizacao:
            ultima_atualizacao = datetime.now().strftime("%d/%m/%Y %H:%M")
            
        # Obter status do local específico
        if local == "center":
            status_local = status.get("center", ESTADO_ABERTO)
        elif local == "goio":
            status_local = status.get("goio", ESTADO_ABERTO)
        else:
            status_local = ESTADO_ABERTO
            
        return {
            "status": status_local,
            "ultima_atualizacao": ultima_atualizacao.decode() if isinstance(ultima_atualizacao, bytes) else ultima_atualizacao
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter status: {e}")
        return {
            "status": ESTADO_ABERTO,
            "ultima_atualizacao": datetime.now().strftime("%d/%m/%Y %H:%M")
        }

def get_stats_message():
    """Retorna estatísticas do dia"""
    try:
        stats = get_daily_stats()
        return (
            f"📊 *Estatísticas do Dia*\n\n"
            f"🚗 Total de transições: {stats['total_transitions']}\n"
            f"⏱️ Tempo médio aberto: {stats['avg_open_time']} minutos\n"
            f"🔄 Última atualização: {stats['last_update']}"
        )
    except Exception as e:
        logger.error(f"Erro ao gerar estatísticas: {e}")
        return "Erro ao gerar estatísticas"

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
                
                # Salvar no banco SQLite
                update_weather(condicao, alerta)
                
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
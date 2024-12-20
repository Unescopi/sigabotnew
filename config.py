from dotenv import load_dotenv
import os
import sys
import pytz
from datetime import timedelta

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Configurações do bot
BOT_URL = os.getenv('BOT_URL')
BOT_PORT = int(os.getenv('BOT_PORT', '80'))
GROUP_ID = os.getenv('GROUP_ID')
MAPS_URL = os.getenv('MAPS_URL')

# Configurações da Evolution API
SERVER_URL = os.getenv('SERVER_URL')
INSTANCE = os.getenv('INSTANCE')
APIKEY = os.getenv('APIKEY')

# Configurações do OpenWeather
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
CITY_ID = os.getenv('CITY_ID')

# Validação das variáveis de ambiente
required_vars = [
    'BOT_URL', 'GROUP_ID', 'SERVER_URL', 'INSTANCE', 'APIKEY', 'WEATHER_API_KEY', 'CITY_ID'
]

# Primeiro verifica se as variáveis existem
missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    print(f"Erro: Variáveis de ambiente faltando: {', '.join(missing_vars)}")
    print("Por favor, configure todas as variáveis necessárias no arquivo .env")
    sys.exit(1)

# Depois verifica se os valores são válidos
invalid_vars = []

# Verifica se as URLs são válidas
for url_var in ['BOT_URL', 'SERVER_URL']:
    url = os.getenv(url_var)
    if not url.startswith(('http://', 'https://')):
        invalid_vars.append(f"{url_var} (deve começar com http:// ou https://)")

# Verifica se GROUP_ID é um número válido
try:
    # Formato do WhatsApp: número@g.us
    group_id_parts = GROUP_ID.split('@')
    if len(group_id_parts) != 2 or group_id_parts[1] != 'g.us':
        invalid_vars.append("GROUP_ID (formato inválido, deve ser número@g.us)")
    else:
        # Verifica se a parte numérica é válida
        int(group_id_parts[0])
except (ValueError, AttributeError):
    invalid_vars.append("GROUP_ID (formato inválido, deve ser número@g.us)")

# Verifica se APIKEY tem um tamanho mínimo
if len(APIKEY) < 10:
    invalid_vars.append("APIKEY (muito curta, verifique se está correta)")

if invalid_vars:
    print(f"Erro: Valores inválidos nas variáveis de ambiente: {', '.join(invalid_vars)}")
    print("Por favor, corrija os valores no arquivo .env")
    sys.exit(1)

# Configurações do Flask
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true' 

# Configuração do fuso horário
BR_TIMEZONE = pytz.timezone('America/Sao_Paulo')

# Configurações de publicidade
INTERVALO_MINIMO_PUBLICIDADE = timedelta(minutes=30)
CHANCE_PUBLICIDADE = 0.5  # 50% de chance

# Configurações de clima
WEATHER_UPDATE_INTERVAL = 1800  # 30 minutos em segundos
WEATHER_ALERT_THRESHOLDS = {
    'temp_max': 35,  # Alerta de calor acima de 35°C
    'temp_min': 10,  # Alerta de frio abaixo de 10°C
    'rain_threshold': 0.5  # Alerta de chuva acima de 0.5mm
}

# Horários de pico
PICOS = {
    'manha': (6, 8),    # 6:00 - 8:00
    'almoco': (11, 13), # 11:00 - 13:00
    'tarde': (17, 19)   # 17:00 - 19:00
}

# Configurações de relevância de mensagens
RELEVANCE_THRESHOLD_MIN = 0.5  # Mensagens abaixo de 50% são ignoradas
RELEVANCE_THRESHOLD_MAX = 0.7  # Mensagens acima de 70% são processadas normalmente
RELEVANCE_CATEGORIES = [
    'status_update',     # Atualizações de status do trânsito
    'time_info',         # Informações sobre horários
    'weather_alert',     # Alertas de clima
    'question',          # Perguntas sobre o trânsito
    'feedback'           # Feedback sobre condições
]

# Configurações de alertas
ALERTA_TEMPO_MEDIO = 1.5  # Alerta quando fechamento > 150% da média
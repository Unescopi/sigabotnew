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

# Validação das variáveis de ambiente
required_vars = ['BOT_URL', 'GROUP_ID', 'SERVER_URL', 'INSTANCE', 'APIKEY']
missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    print(f"Erro: Variáveis de ambiente faltando: {', '.join(missing_vars)}")
    print("Por favor, configure todas as variáveis necessárias no arquivo .env")
    sys.exit(1)

# Configurações do Flask
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true' 

# Configuração do fuso horário
BR_TIMEZONE = pytz.timezone('America/Sao_Paulo')

# Configurações de publicidade
INTERVALO_MINIMO_PUBLICIDADE = timedelta(minutes=30)
CHANCE_PUBLICIDADE = 0.5  # 50% de chance

# Configurações de clima
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
WEATHER_UPDATE_INTERVAL = timedelta(minutes=30)
CITY_ID = '3453186'  # ID de Quarto Centenário-PR

# Horários de pico
PICOS = {
    'manha': (6, 8),    # 6:00 - 8:00
    'almoco': (11, 13), # 11:00 - 13:00
    'tarde': (17, 19)   # 17:00 - 19:00
}

# Configurações de alertas
ALERTA_TEMPO_MEDIO = 1.5  # Alerta quando fechamento > 150% da média
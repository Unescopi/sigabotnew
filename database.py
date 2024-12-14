import sqlite3
from datetime import datetime, timedelta
import pytz
from config import BR_TIMEZONE, REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD, REDIS_SSL
import redis
import json
import sys

# Configuração do Redis
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    password=REDIS_PASSWORD,
    ssl=REDIS_SSL,
    decode_responses=True
)

# Testa conexão com Redis
try:
    redis_client.ping()
except redis.ConnectionError as e:
    print(f"Erro ao conectar ao Redis: {e}")
    print("Verifique as configurações de conexão no arquivo .env")
    sys.exit(1)

def connect_db():
    return sqlite3.connect('traffic.db')

def get_status(lado):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status, ultima_atualizacao FROM status_transito WHERE lado = ?", (lado,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        status, ultima_atualizacao = result
        try:
            ultima_atualizacao = datetime.strptime(ultima_atualizacao.split('.')[0], '%Y-%m-%d %H:%M:%S')
            ultima_atualizacao = BR_TIMEZONE.localize(ultima_atualizacao)
            ultima_atualizacao_str = ultima_atualizacao.strftime('%d/%m/%Y %H:%M')
            return status, ultima_atualizacao_str
        except Exception:
            return status, ultima_atualizacao
    return None, None

def update_status(lado, novo_status):
    conn = connect_db()
    cursor = conn.cursor()
    agora = datetime.now(BR_TIMEZONE)
    agora_str = agora.strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        "UPDATE status_transito SET status = ?, ultima_atualizacao = ? WHERE lado = ?",
        (novo_status, agora_str, lado)
    )
    conn.commit()
    conn.close()

def record_closure_time(lado, tempo_fechamento):
    """Registra tempo de fechamento"""
    # Ignorar tempos muito curtos (menos de 1 minuto) pois provavelmente são correções
    if tempo_fechamento < 60:  # 60 segundos
        return
        
    conn = connect_db()
    cursor = conn.cursor()
    agora = datetime.now(BR_TIMEZONE)
    agora_str = agora.strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute(
        "INSERT INTO fechamentos (lado, tempo_fechamento, timestamp) VALUES (?, ?, ?)",
        (lado, tempo_fechamento, agora_str)
    )
    conn.commit()
    conn.close()

def calculate_average_closure(lado, limit=5):
    """Calcula média móvel dos últimos fechamentos"""
    conn = connect_db()
    cursor = conn.cursor()
    
    # Pegar apenas fechamentos com duração significativa (mais de 1 minuto)
    cursor.execute("""
        SELECT tempo_fechamento 
        FROM fechamentos 
        WHERE lado = ? 
        AND tempo_fechamento >= 60
        ORDER BY id DESC
        LIMIT ?
    """, (lado, limit))
    
    tempos = cursor.fetchall()
    conn.close()
    
    if not tempos:
        return None
        
    # Remover outliers (tempos muito diferentes da média)
    tempos = [t[0] for t in tempos]
    media = sum(tempos) / len(tempos)
    desvio_padrao = (sum((x - media) ** 2 for x in tempos) / len(tempos)) ** 0.5
    
    # Considerar apenas tempos dentro de 2 desvios padrão da média
    tempos_filtrados = [t for t in tempos if abs(t - media) <= 2 * desvio_padrao]
    
    if not tempos_filtrados:
        return media  # Se todos forem outliers, retorna a média original
        
    return sum(tempos_filtrados) / len(tempos_filtrados)

def get_daily_stats():
    """Retorna estatísticas do dia atual"""
    conn = connect_db()
    cursor = conn.cursor()
    hoje = datetime.now(BR_TIMEZONE).strftime('%Y-%m-%d')
    
    # Total de fechamentos do dia
    cursor.execute(
        "SELECT COUNT(*) FROM fechamentos WHERE date(timestamp) = ?",
        (hoje,)
    )
    total_fechamentos = cursor.fetchone()[0]
    
    # Tempo médio de fechamento
    cursor.execute(
        "SELECT AVG(tempo_fechamento) FROM fechamentos WHERE date(timestamp) = ?",
        (hoje,)
    )
    tempo_medio = cursor.fetchone()[0] or 0
    
    # Horário mais movimentado
    cursor.execute("""
        SELECT strftime('%H:00', timestamp) as hora, COUNT(*) as total
        FROM fechamentos 
        WHERE date(timestamp) = ?
        GROUP BY hora
        ORDER BY total DESC
        LIMIT 1
    """, (hoje,))
    result = cursor.fetchone()
    horario_pico = result[0] if result else "Sem dados"
    
    conn.close()
    return {
        'total_fechamentos': total_fechamentos,
        'tempo_medio': int(tempo_medio),
        'horario_pico': horario_pico
    }

def get_weather_status():
    """Retorna o último status do clima registrado"""
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT condicao, alerta, ultima_atualizacao FROM clima ORDER BY id DESC LIMIT 1"
    )
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'condicao': result[0],
            'alerta': result[1],
            'ultima_atualizacao': result[2]
        }
    return None

def update_weather(condicao, alerta=None):
    """Atualiza o status do clima"""
    conn = connect_db()
    cursor = conn.cursor()
    agora = datetime.now(BR_TIMEZONE)
    cursor.execute(
        "INSERT INTO clima (condicao, alerta, ultima_atualizacao) VALUES (?, ?, ?)",
        (condicao, alerta, agora.strftime('%Y-%m-%d %H:%M:%S'))
    )
    conn.commit()
    conn.close() 
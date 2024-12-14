import sqlite3
from datetime import datetime, timedelta
import pytz
from config import BR_TIMEZONE
import redis
import json

# Inicializa cliente Redis
redis_client = redis.Redis(
    host='redis',  # nome do serviço no docker-compose
    port=6379,
    db=0,
    decode_responses=True
)

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
    conn = connect_db()
    cursor = conn.cursor()
    agora = datetime.now(BR_TIMEZONE)
    cursor.execute(
        "INSERT INTO tempos_fechamento (lado, tempo_fechamento, data_registro) VALUES (?, ?, ?)",
        (lado, tempo_fechamento, agora.strftime('%Y-%m-%d %H:%M:%S'))
    )
    conn.commit()
    conn.close()

def calculate_average_closure(lado, limit=5):
    """Calcula média móvel dos últimos fechamentos"""
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT tempo_fechamento FROM tempos_fechamento WHERE lado = ? ORDER BY id DESC LIMIT ?", 
        (lado, limit)
    )
    tempos = cursor.fetchall()
    conn.close()
    
    if not tempos:
        return 0
    return int(sum(t[0] for t in tempos) / len(tempos))

def get_daily_stats():
    """Retorna estatísticas do dia atual"""
    conn = connect_db()
    cursor = conn.cursor()
    hoje = datetime.now(BR_TIMEZONE).strftime('%Y-%m-%d')
    
    # Total de fechamentos do dia
    cursor.execute(
        "SELECT COUNT(*) FROM tempos_fechamento WHERE date(data_registro) = ?",
        (hoje,)
    )
    total_fechamentos = cursor.fetchone()[0]
    
    # Tempo médio de fechamento
    cursor.execute(
        "SELECT AVG(tempo_fechamento) FROM tempos_fechamento WHERE date(data_registro) = ?",
        (hoje,)
    )
    tempo_medio = cursor.fetchone()[0] or 0
    
    # Horário mais movimentado
    cursor.execute("""
        SELECT strftime('%H:00', data_registro) as hora, COUNT(*) as total
        FROM tempos_fechamento 
        WHERE date(data_registro) = ?
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
import sqlite3
from datetime import datetime
from config import BR_TIMEZONE

def create_database():
    conn = sqlite3.connect('traffic.db')
    cursor = conn.cursor()

    # Tabela de status do trânsito
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS status_transito (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lado TEXT NOT NULL,
        status TEXT NOT NULL,
        ultima_atualizacao TIMESTAMP NOT NULL
    )
    ''')

    # Tabela de tempos de fechamento
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tempos_fechamento (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lado TEXT NOT NULL,
        tempo_fechamento INTEGER NOT NULL,
        data_registro TIMESTAMP NOT NULL
    )
    ''')

    # Nova tabela para clima
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS clima (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        condicao TEXT NOT NULL,
        alerta TEXT,
        ultima_atualizacao TIMESTAMP NOT NULL
    )
    ''')

    # Insere dados iniciais se necessário
    cursor.execute("SELECT COUNT(*) FROM status_transito")
    if cursor.fetchone()[0] == 0:
        agora = datetime.now(BR_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            "INSERT INTO status_transito (lado, status, ultima_atualizacao) VALUES (?, ?, ?)",
            ('CENTER', 'ABERTO', agora)
        )
        cursor.execute(
            "INSERT INTO status_transito (lado, status, ultima_atualizacao) VALUES (?, ?, ?)",
            ('GOIO', 'ABERTO', agora)
        )

    conn.commit()
    conn.close()

if __name__ == '__main__':
    create_database()
    print("Banco de dados criado/atualizado com sucesso!") 
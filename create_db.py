import sqlite3

def create_database():
    conn = sqlite3.connect('traffic.db')
    cursor = conn.cursor()

    # Criação da tabela de status de trânsito
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS status_transito (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lado TEXT NOT NULL,
        status TEXT NOT NULL,
        ultima_atualizacao TEXT NOT NULL
    )
    ''')

    # Criação da tabela de tempos de fechamento
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tempos_fechamento (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lado TEXT NOT NULL,
        tempo_fechamento INTEGER NOT NULL,
        data_registro TEXT NOT NULL
    )
    ''')

    # Criação da tabela de clima
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS clima (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        condicao TEXT NOT NULL,
        alerta TEXT,
        ultima_atualizacao TEXT NOT NULL
    )
    ''')

    conn.commit()
    conn.close()

if __name__ == "__main__":
    create_database()
    print("Banco de dados e tabelas criados com sucesso!") 
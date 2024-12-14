from flask import Flask, request, jsonify
import os
import logging
from services.evolution_service import process_message, get_mensagem_ajuda
import requests
from waitress import serve
from dotenv import load_dotenv

# Carrega as variáveis de ambiente
load_dotenv()

# Configuração de logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Rota raiz para verificar se o servidor está online
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "online",
        "message": "Bot está funcionando!"
    })

# Rota webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        logger.info("=== NOVA REQUISIÇÃO RECEBIDA ===")
        logger.info(f"Headers: {dict(request.headers)}")
        logger.info(f"Dados: {data}")
        logger.info("================================")

        # Verifica se é uma mensagem do tipo messages.upsert
        if data.get('event') == 'messages.upsert':
            message_data = data.get('data', {})
            
            # Log detalhado da mensagem
            logger.info("=== DADOS DA MENSAGEM ===")
            logger.info(f"Tipo: {message_data.get('messageType')}")
            logger.info(f"Texto: {message_data.get('message', {}).get('conversation')}")
            logger.info(f"Remetente: {message_data.get('pushName')}")
            logger.info("========================")
            
            if message_data.get('messageType') in ['conversation', 'extendedTextMessage']:
                # Pega o texto da mensagem (suporta mensagens normais e respostas)
                text = (message_data.get('message', {}).get('conversation') or 
                       message_data.get('message', {}).get('extendedTextMessage', {}).get('text'))
                
                sender = message_data.get('pushName')
                group_id = message_data.get('key', {}).get('remoteJid')
                
                if text and group_id == os.getenv('GROUP_ID'):
                    response = process_message({
                        'text': text,
                        'sender': {
                            'pushName': sender,
                            'messageType': message_data.get('messageType'),
                            'quoted': bool(message_data.get('message', {}).get('extendedTextMessage', {}).get('contextInfo'))
                        }
                    })
                    
                    if response:
                        url = f"{data.get('server_url')}/message/sendText/{data.get('instance')}"
                        headers = {
                            "Content-Type": "application/json",
                            "apikey": data.get('apikey')
                        }
                        payload = {
                            "number": group_id,
                            "text": response,
                            "options": {
                                "delay": 1200,
                                "presence": "composing"
                            }
                        }
                        
                        logger.info(f"Enviando mensagem para: {url}")
                        logger.info(f"Headers: {headers}")
                        logger.info(f"Payload: {payload}")
                        
                        response = requests.post(url, json=payload, headers=headers)
                        logger.info(f"Resposta da API: {response.text}")
                        
                        return jsonify({"status": True}), 200
        
        return jsonify({"status": True}), 200
        
    except Exception as e:
        logger.error(f"Erro no webhook: {str(e)}")
        logger.error(f"Request data: {request.data}")
        return jsonify({
            "status": False,
            "error": str(e)
        }), 500

def start_server():
    """Inicia o servidor com Waitress"""
    try:
        port = int(os.getenv('PORT', 80))
        logger.info(f"Iniciando servidor na porta {port}")
        serve(app, host='0.0.0.0', port=port)
    except Exception as e:
        logger.error(f"Erro ao iniciar servidor: {e}")
        raise

if __name__ == '__main__':
    start_server() 
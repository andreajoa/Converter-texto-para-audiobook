from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import tempfile
import uuid
from datetime import datetime
import logging

# Para text-to-speech - você pode usar diferentes bibliotecas
try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    print("pyttsx3 não encontrado. Instale com: pip install pyttsx3")

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Permitir requisições do frontend

# Diretório para arquivos temporários
TEMP_DIR = tempfile.mkdtemp()
AUDIO_FILES = {}  # Armazenar referências dos arquivos gerados

@app.route('/')
def home():
    """Página inicial - serve o HTML"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Conversor de Texto para Audiobook - API</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
            .status { padding: 10px; margin: 10px 0; border-radius: 5px; }
            .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .info { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
        </style>
    </head>
    <body>
        <h1>🎧 Conversor de Texto para Audiobook - API</h1>
        <div class="status success">✅ API está funcionando!</div>
        <div class="status info">
            <strong>Endpoints disponíveis:</strong><br>
            • POST /convert - Converter texto para áudio<br>
            • GET /download/&lt;file_id&gt; - Baixar arquivo de áudio<br>
            • GET /status - Status da API
        </div>
        <p><strong>TTS Status:</strong> {'✅ Disponível' if TTS_AVAILABLE else '❌ Não disponível'}</p>
        <p><strong>Data/Hora:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
    </body>
    </html>
    """.format(datetime=datetime)

@app.route('/status')
def status():
    """Endpoint para verificar status da API"""
    return jsonify({
        'status': 'online',
        'tts_available': TTS_AVAILABLE,
        'timestamp': datetime.now().isoformat(),
        'temp_dir': TEMP_DIR,
        'active_files': len(AUDIO_FILES)
    })

@app.route('/convert', methods=['POST'])
def convert_text_to_audio():
    """Converter texto para áudio"""
    try:
        # Verificar se TTS está disponível
        if not TTS_AVAILABLE:
            return jsonify({
                'error': 'Text-to-Speech não está disponível. Instale pyttsx3: pip install pyttsx3'
            }), 500

        # Obter dados do request
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Dados JSON não fornecidos'}), 400

        text = data.get('text', '').strip()
        voice = data.get('voice', 'pt-BR-FranciscaNeural')
        speed = float(data.get('speed', 1.0))

        if not text:
            return jsonify({'error': 'Texto não fornecido'}), 400

        logger.info(f"Iniciando conversão: {len(text)} caracteres")

        # Gerar ID único para o arquivo
        file_id = str(uuid.uuid4())
        audio_filename = f"audiobook_{file_id}.wav"
        audio_path = os.path.join(TEMP_DIR, audio_filename)

        # Configurar TTS
        engine = pyttsx3.init()
        
        # Configurar velocidade
        rate = engine.getProperty('rate')
        engine.setProperty('rate', int(rate * speed))

        # Configurar voz (se disponível)
        voices = engine.getProperty('voices')
        if voices:
            # Para português brasileiro, tentar encontrar voz feminina
            for voice_obj in voices:
                if 'brazil' in voice_obj.name.lower() or 'portuguese' in voice_obj.name.lower():
                    engine.setProperty('voice', voice_obj.id)
                    break

        # Converter texto para áudio
        engine.save_to_file(text, audio_path)
        engine.runAndWait()

        # Verificar se o arquivo foi criado
        if not os.path.exists(audio_path):
            return jsonify({'error': 'Falha ao gerar arquivo de áudio'}), 500

        # Armazenar informações do arquivo
        AUDIO_FILES[file_id] = {
            'filename': audio_filename,
            'path': audio_path,
            'created_at': datetime.now().isoformat(),
            'text_length': len(text),
            'voice': voice,
            'speed': speed
        }

        logger.info(f"Conversão concluída: {audio_filename}")

        return jsonify({
            'success': True,
            'file_id': file_id,
            'filename': audio_filename,
            'download_url': f'/download/{file_id}',
            'file_size': os.path.getsize(audio_path),
            'text_length': len(text)
        })

    except Exception as e:
        logger.error(f"Erro na conversão: {str(e)}")
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@app.route('/download/<file_id>')
def download_audio(file_id):
    """Baixar arquivo de áudio gerado"""
    if file_id not in AUDIO_FILES:
        return jsonify({'error': 'Arquivo não encontrado'}), 404

    file_info = AUDIO_FILES[file_id]
    audio_path = file_info['path']

    if not os.path.exists(audio_path):
        return jsonify({'error': 'Arquivo não existe no sistema'}), 404

    try:
        return send_file(
            audio_path,
            as_attachment=True,
            download_name=file_info['filename'],
            mimetype='audio/wav'
        )
    except Exception as e:
        logger.error(f"Erro no download: {str(e)}")
        return jsonify({'error': f'Erro no download: {str(e)}'}), 500

@app.route('/convert-form', methods=['POST'])
def convert_form():
    """Endpoint para converter via form data (para integração com HTML forms)"""
    try:
        # Obter texto do form ou arquivo
        text = request.form.get('text', '').strip()
        
        # Se não há texto no form, tentar arquivo
        if not text and 'file' in request.files:
            file = request.files['file']
            if file.filename and file.filename.endswith('.txt'):
                text = file.read().decode('utf-8').strip()

        if not text:
            return jsonify({'error': 'Texto não fornecido'}), 400

        voice = request.form.get('voice', 'pt-BR-FranciscaNeural')
        speed = float(request.form.get('speed', 1.0))

        # Usar mesma lógica do endpoint /convert
        data = {'text': text, 'voice': voice, 'speed': speed}
        request.json = data
        
        return convert_text_to_audio()

    except Exception as e:
        logger.error(f"Erro no form: {str(e)}")
        return jsonify({'error': f'Erro no processamento: {str(e)}'}), 500

@app.route('/cleanup')
def cleanup():
    """Limpar arquivos temporários antigos"""
    cleaned = 0
    for file_id, file_info in list(AUDIO_FILES.items()):
        try:
            if os.path.exists(file_info['path']):
                os.remove(file_info['path'])
                cleaned += 1
            del AUDIO_FILES[file_id]
        except Exception as e:
            logger.error(f"Erro limpando {file_id}: {str(e)}")
    
    return jsonify({
        'cleaned_files': cleaned,
        'remaining_files': len(AUDIO_FILES)
    })

if __name__ == '__main__':
    print("🎧 Iniciando Conversor de Texto para Audiobook")
    print(f"📁 Diretório temporário: {TEMP_DIR}")
    print(f"🎤 TTS disponível: {'Sim' if TTS_AVAILABLE else 'Não'}")
    print("\n📋 Instalação de dependências:")
    print("pip install flask flask-cors pyttsx3")
    print("\n🚀 Para iniciar:")
    print("python app.py")
    print("\n🌐 Acesse: http://localhost:5000")
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import os
import tempfile
import uuid
from datetime import datetime
import logging
from werkzeug.utils import secure_filename
from gtts import gTTS

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configurações
TEMP_DIR = tempfile.mkdtemp()
AUDIO_FILES = {}
UPLOAD_FOLDER = os.path.join(TEMP_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Arquivos suportados
ALLOWED_EXTENSIONS = {'txt'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

# Vozes disponíveis para gTTS (focando em pt-BR)
VOICES_CONFIG = {
    'gtts': {
        'pt-BR': {'name': 'Google TTS Português Brasil (Feminina)', 'gender': 'Female', 'country': 'Brasil'},
        'pt': {'name': 'Google TTS Português (Feminina)', 'gender': 'Female', 'country': 'Portugal'}
    }
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    """Página inicial"""
    return render_template('index.html')

@app.route('/status')
def status():
    """Status da API"""
    return jsonify({
        'status': 'online',
        'tts_engine': 'gtts',
        'tts_type': 'online',
        'available_engines': {'gtts': True},
        'file_support': {'txt': True},
        'voices': VOICES_CONFIG.get('gtts', {}),
        'timestamp': datetime.now().isoformat(),
        'active_files': len(AUDIO_FILES)
    })

@app.route('/voices')
def get_voices():
    """Obter vozes disponíveis"""
    return jsonify({
        'engine': 'gtts',
        'voices': VOICES_CONFIG.get('gtts', {})
    })

@app.route('/convert', methods=['POST'])
def convert():
    """Converter texto ou arquivo para audiobook"""
    try:
        text = ""
        
        # Upload de arquivo txt
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(file_path)
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                os.remove(file_path)
        
        # Se não há arquivo, tenta pegar do JSON ou form
        if not text:
            if request.is_json:
                data = request.get_json()
                text = data.get('text', '').strip()
            else:
                text = request.form.get('text', '').strip()
        
        if not text:
            return jsonify({'error': 'Texto ou arquivo não fornecido'}), 400
        
        # Parâmetros
        if request.is_json:
            data = request.get_json()
            voice = data.get('voice', 'pt-BR')
            speed = float(data.get('speed', 1.0))
        else:
            voice = request.form.get('voice', 'pt-BR')
            speed = float(request.form.get('speed', 1.0))

        logger.info(f"Convertendo {len(text)} caracteres com voz {voice}")
        
        # Gerar arquivo de áudio (direto)
        file_id = str(uuid.uuid4())
        audio_filename = f"audiobook_{file_id}.mp3"
        audio_path = os.path.join(TEMP_DIR, audio_filename)

        # gTTS só aceita até ~5000 caracteres por vez, então corta se necessário
        max_gtts_chars = 4900
        chunks = [text[i:i+max_gtts_chars] for i in range(0, len(text), max_gtts_chars)]
        
        # Gera áudio por partes e salva como um único arquivo final
        with open(audio_path, "wb") as outfile:
            for part in chunks:
                tts = gTTS(text=part, lang=voice if voice in ["pt-BR", "pt"] else "pt-BR", slow=(speed < 0.8))
                temp_mp3 = os.path.join(TEMP_DIR, f"temp_{uuid.uuid4().hex}.mp3")
                tts.save(temp_mp3)
                with open(temp_mp3, "rb") as fin:
                    outfile.write(fin.read())
                os.remove(temp_mp3)

        AUDIO_FILES[file_id] = {
            'filename': audio_filename,
            'path': audio_path,
            'created_at': datetime.now().isoformat(),
            'text_length': len(text),
            'voice': voice,
            'speed': speed,
            'engine': 'gtts'
        }
        
        return jsonify({
            'success': True,
            'file_id': file_id,
            'filename': audio_filename,
            'download_url': f'/download/{file_id}',
            'file_size': os.path.getsize(audio_path),
            'text_length': len(text),
            'voice': voice,
            'engine': 'gtts'
        })
        
    except Exception as e:
        logger.error(f"Erro na conversão: {str(e)}")
        return jsonify({'error': f'Erro: {str(e)}'}), 500

@app.route('/download/<file_id>')
def download_audio(file_id):
    """Download do arquivo de áudio"""
    if file_id not in AUDIO_FILES:
        return jsonify({'error': 'Arquivo não encontrado'}), 404
    file_info = AUDIO_FILES[file_id]
    if not os.path.exists(file_info['path']):
        return jsonify({'error': 'Arquivo não existe'}), 404
    try:
        return send_file(
            file_info['path'],
            as_attachment=True,
            download_name=file_info['filename'],
            mimetype='audio/mpeg'
        )
    except Exception as e:
        return jsonify({'error': f'Erro no download: {str(e)}'}), 500

@app.route('/cleanup')
def cleanup():
    """Limpar arquivos temporários"""
    cleaned = 0
    for file_id, file_info in list(AUDIO_FILES.items()):
        try:
            if os.path.exists(file_info['path']):
                os.remove(file_info['path'])
                cleaned += 1
            del AUDIO_FILES[file_id]
        except Exception as e:
            logger.error(f"Erro limpando {file_id}: {str(e)}")
    return jsonify({'cleaned_files': cleaned})

if __name__ == '__main__':
    print("🎧 Conversor de Texto para Audiobook - Versão Simplificada com gTTS")
    print(f"📁 Diretório temporário: {TEMP_DIR}")
    print(f"🎤 Engine TTS: gTTS")
    print("📋 Para instalar as dependências: pip install flask flask-cors gtts")
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

from flask import Flask, request, jsonify, send_file, render_template_string
from flask_cors import CORS
import os
import tempfile
import uuid
from datetime import datetime
import logging
from werkzeug.utils import secure_filename
from gtts import gTTS

# PDF e DOCX só se instalados
try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

TEMP_DIR = tempfile.mkdtemp()
AUDIO_FILES = {}
UPLOAD_FOLDER = os.path.join(TEMP_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

VOICES_CONFIG = {
    'gtts': {
        'pt-BR': {'name': 'Google TTS Português Brasil (Feminina)', 'gender': 'Female', 'country': 'Brasil'},
        'pt': {'name': 'Google TTS Português (Feminina)', 'gender': 'Female', 'country': 'Portugal'}
    }
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_file(file_path, filename):
    ext = filename.lower().split('.')[-1]
    text = ""
    try:
        if ext == "txt":
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        elif ext == "pdf" and PDF_AVAILABLE:
            with open(file_path, "rb") as f:
                pdf = PyPDF2.PdfReader(f)
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text += t + "\n"
        elif ext == "docx" and DOCX_AVAILABLE:
            doc = Document(file_path)
            for p in doc.paragraphs:
                text += p.text + "\n"
        else:
            text = ""
    except Exception as e:
        logger.error(f"Erro ao extrair texto: {str(e)}")
        raise
    return text.strip()

@app.route('/')
def home():
    # Simples HTML sempre, nunca erro se não existir index.html
    return render_template_string("""
    <h1>Conversor de Texto para Audiobook</h1>
    <form method="post" action="/convert" enctype="multipart/form-data">
        <p>Texto: <textarea name="text" rows="6" cols="60"></textarea></p>
        <p>OU envie um arquivo: <input type="file" name="file" /></p>
        <p>
            Voz:
            <select name="voice">
                <option value="pt-BR">Português Brasil</option>
                <option value="pt">Português Portugal</option>
            </select>
        </p>
        <p>Velocidade: <input name="speed" value="1.0" size="2" /> (1.0 = normal, 0.7 = devagar)</p>
        <button type="submit">Converter</button>
    </form>
    """)

@app.route('/convert', methods=['POST'])
def convert():
    try:
        text = ""
        # Upload de arquivo
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(file_path)
                text = extract_text_from_file(file_path, filename)
                os.remove(file_path)
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

        # gTTS aceita até ~5000 caracteres
        max_gtts_chars = 4900
        chunks = [text[i:i+max_gtts_chars] for i in range(0, len(text), max_gtts_chars)]
        file_id = str(uuid.uuid4())
        audio_filename = f"audiobook_{file_id}.mp3"
        audio_path = os.path.join(TEMP_DIR, audio_filename)
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
        # Resposta para download
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
    print("🎧 Conversor de Texto para Audiobook - Versão Corrigida com gTTS")
    print(f"📁 Diretório temporário: {TEMP_DIR}")
    print(f"🎤 Engine TTS: gTTS")
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

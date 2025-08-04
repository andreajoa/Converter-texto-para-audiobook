from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import os
import tempfile
import uuid
from datetime import datetime
import logging
from werkzeug.utils import secure_filename
from gtts import gTTS
from pydub import AudioSegment

# Bibliotecas para leitura de diferentes formatos
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

try:
    import openpyxl
    from openpyxl import load_workbook
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

try:
    import pptx
    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False

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

# Configurações de arquivo
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt', 'rtf'}
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

def extract_text_from_file(file_path, filename):
    """Extrair texto de diferentes tipos de arquivo"""
    text = ""
    file_extension = filename.lower().split('.')[-1]
    
    try:
        if file_extension == 'txt':
            with open(file_path, 'r', encoding='utf-8') as file:
                text = file.read()
        
        elif file_extension == 'pdf' and PDF_AVAILABLE:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
        
        elif file_extension in ['docx', 'doc'] and DOCX_AVAILABLE:
            doc = Document(file_path)
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
        
        elif file_extension in ['xlsx', 'xls'] and EXCEL_AVAILABLE:
            workbook = load_workbook(file_path)
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                for row in sheet.iter_rows(values_only=True):
                    text += " ".join([str(cell) for cell in row if cell is not None]) + "\n"
        
        elif file_extension in ['pptx', 'ppt'] and PPTX_AVAILABLE:
            presentation = pptx.Presentation(file_path)
            for slide in presentation.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        text += shape.text + "\n"
        
        else:
            # Tentar ler como texto simples
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    text = file.read()
            except:
                with open(file_path, 'r', encoding='latin-1') as file:
                    text = file.read()
    
    except Exception as e:
        logger.error(f"Erro ao extrair texto de {filename}: {str(e)}")
        raise Exception(f"Não foi possível extrair texto do arquivo: {str(e)}")
    
    return text.strip()

def convert_text_to_speech(text, voice, speed, file_path):
    """Converter texto para fala usando gTTS, com suporte a textos longos"""
    try:
        lang = voice if voice in ['pt-BR', 'pt'] else 'pt-BR'
        # Dividir o texto em blocos de 4500 caracteres para evitar o limite do gTTS
        text_parts = [text[i:i+4500] for i in range(0, len(text), 4500)]
        
        # Gerar um arquivo de áudio para cada parte do texto
        audio_parts = []
        for i, part in enumerate(text_parts):
            part_file = os.path.join(TEMP_DIR, f"part_{i}.mp3")
            tts = gTTS(text=part, lang=lang, slow=(speed < 0.8))
            tts.save(part_file)
            audio_parts.append(AudioSegment.from_mp3(part_file))
        
        # Concatenar os arquivos de áudio
        combined_audio = sum(audio_parts)
        
        # Salvar o arquivo de áudio final
        combined_audio.export(file_path, format="mp3")
        
        # Limpar os arquivos de áudio parciais
        for part_file in os.listdir(TEMP_DIR):
            if part_file.startswith("part_"):
                os.remove(os.path.join(TEMP_DIR, part_file))

        return True
        
    except Exception as e:
        logger.error(f"Erro gTTS: {str(e)}")
        return False

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
        'available_engines': {
            'gtts': True
        },
        'file_support': {
            'pdf': PDF_AVAILABLE,
            'docx': DOCX_AVAILABLE,
            'excel': EXCEL_AVAILABLE,
            'pptx': PPTX_AVAILABLE
        },
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
        
        # Verificar se é upload de arquivo
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(file_path)
                
                # Extrair texto do arquivo
                text = extract_text_from_file(file_path, filename)
                os.remove(file_path)  # Limpar arquivo temporário
        
        # Se não há arquivo, tentar obter texto do JSON ou form
        if not text:
            if request.is_json:
                data = request.get_json()
                text = data.get('text', '').strip()
            else:
                text = request.form.get('text', '').strip()
        
        if not text:
            return jsonify({'error': 'Texto ou arquivo não fornecido'}), 400
        
        # Obter parâmetros
        if request.is_json:
            data = request.get_json()
            voice = data.get('voice', list(VOICES_CONFIG.get('gtts', {}).keys())[0])
            speed = float(data.get('speed', 1.0))
        else:
            voice = request.form.get('voice', list(VOICES_CONFIG.get('gtts', {}).keys())[0])
            speed = float(request.form.get('speed', 1.0))
        
        logger.info(f"Convertendo {len(text)} caracteres com voz {voice}")
        
        # Gerar arquivo de áudio
        file_id = str(uuid.uuid4())
        audio_filename = f"audiobook_{file_id}.mp3"
        audio_path = os.path.join(TEMP_DIR, audio_filename)
        
        # Converter texto para fala
        success = convert_text_to_speech(text, voice, speed, audio_path)
        
        if not success or not os.path.exists(audio_path):
            return jsonify({'error': 'Falha ao gerar áudio'}), 500
        
        # Armazenar informações
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
    print("🎧 Conversor de Texto para Audiobook - Versão Otimizada com gTTS")
    print(f"📁 Diretório temporário: {TEMP_DIR}")
    print(f"🎤 Engine TTS: gTTS")
    print(f"📚 Suporte a arquivos: TXT, PDF{'✓' if PDF_AVAILABLE else '✗'}, DOCX{'✓' if DOCX_AVAILABLE else '✗'}, XLSX{'✓' if EXCEL_AVAILABLE else '✗'}, PPTX{'✓' if PPTX_AVAILABLE else '✗'}")
    print("\n📋 Para instalar as dependências:")
    print("pip install flask flask-cors PyPDF2 python-docx openpyxl python-pptx gtts pydub")
    
    app.run(host='0.0.0.0', port=5000, debug=True)

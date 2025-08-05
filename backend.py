from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import os
import tempfile
import uuid
from datetime import datetime
import logging
from werkzeug.utils import secure_filename
from gtts import gTTS
import PyPDF2
import docx
import chardet
import zipfile
import xml.etree.ElementTree as ET

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializar Flask com template folder correto
app = Flask(__name__, 
            template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'),
            static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static'))
CORS(app)

# Diretório temporário seguro
TEMP_DIR = tempfile.gettempdir()
AUDIO_FILES = {}
UPLOAD_FOLDER = os.path.join(TEMP_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Extensões permitidas expandidas
ALLOWED_EXTENSIONS = {
    'txt', 'pdf', 'doc', 'docx', 'rtf', 'odt', 
    'csv', 'md', 'html', 'htm', 'xml', 'json'
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Vozes disponíveis no gTTS
VOICES = {
    'pt-BR': {
        'name': 'Português Brasil (Feminina)',
        'gender': 'Feminina',
        'country': 'Brasil'
    },
    'pt': {
        'name': 'Português Portugal (Feminina)',
        'gender': 'Feminina', 
        'country': 'Portugal'
    },
    'en': {
        'name': 'English (Female)',
        'gender': 'Female',
        'country': 'United States'
    },
    'es': {
        'name': 'Español (Femenina)',
        'gender': 'Femenina',
        'country': 'España'
    },
    'fr': {
        'name': 'Français (Féminin)',
        'gender': 'Féminin',
        'country': 'France'
    },
    'de': {
        'name': 'Deutsch (Weiblich)',
        'gender': 'Weiblich',
        'country': 'Deutschland'
    },
    'it': {
        'name': 'Italiano (Femminile)',
        'gender': 'Femminile',
        'country': 'Italia'
    },
    'ja': {
        'name': '日本語 (女性)',
        'gender': '女性',
        'country': '日本'
    },
    'ko': {
        'name': '한국어 (여성)',
        'gender': '여성',
        'country': '대한민국'
    },
    'zh': {
        'name': '中文 (女性)',
        'gender': '女性',
        'country': '中国'
    }
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def detect_encoding(file_path):
    """Detecta a codificação do arquivo"""
    with open(file_path, 'rb') as f:
        raw_data = f.read()
        result = chardet.detect(raw_data)
        return result['encoding'] or 'utf-8'

def extract_text_from_pdf(file_path):
    """Extrai texto de arquivo PDF"""
    try:
        text = ""
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"Erro ao ler PDF: {str(e)}")
        raise Exception(f"Erro ao processar PDF: {str(e)}")

def extract_text_from_docx(file_path):
    """Extrai texto de arquivo DOCX"""
    try:
        doc = docx.Document(file_path)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"Erro ao ler DOCX: {str(e)}")
        raise Exception(f"Erro ao processar DOCX: {str(e)}")

def extract_text_from_odt(file_path):
    """Extrai texto de arquivo ODT (OpenDocument Text)"""
    try:
        text = ""
        with zipfile.ZipFile(file_path, 'r') as odt_file:
            content_xml = odt_file.read('content.xml')
            root = ET.fromstring(content_xml)
            
            # Remove namespace prefixes para simplificar
            for elem in root.iter():
                if elem.text:
                    text += elem.text + " "
        
        return text.strip()
    except Exception as e:
        logger.error(f"Erro ao ler ODT: {str(e)}")
        raise Exception(f"Erro ao processar ODT: {str(e)}")

def extract_text_from_rtf(file_path):
    """Extrai texto de arquivo RTF (básico)"""
    try:
        encoding = detect_encoding(file_path)
        with open(file_path, 'r', encoding=encoding, errors='ignore') as file:
            content = file.read()
            
        # Remove comandos RTF básicos (muito simplificado)
        import re
        text = re.sub(r'\\[a-z]+\d*', '', content)
        text = re.sub(r'[{}]', '', text)
        text = re.sub(r'\\\*.*?;', '', text)
        
        return text.strip()
    except Exception as e:
        logger.error(f"Erro ao ler RTF: {str(e)}")
        raise Exception(f"Erro ao processar RTF: {str(e)}")

def extract_text_from_file(file_path, filename):
    """Extrai texto baseado na extensão do arquivo"""
    ext = filename.rsplit('.', 1)[1].lower()
    
    try:
        if ext == 'pdf':
            return extract_text_from_pdf(file_path)
        elif ext == 'docx':
            return extract_text_from_docx(file_path)
        elif ext == 'odt':
            return extract_text_from_odt(file_path)
        elif ext == 'rtf':
            return extract_text_from_rtf(file_path)
        elif ext in ['txt', 'md', 'csv', 'html', 'htm', 'xml', 'json']:
            encoding = detect_encoding(file_path)
            with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                content = f.read()
                
            # Para HTML, remove tags básicas
            if ext in ['html', 'htm']:
                import re
                content = re.sub(r'<[^>]+>', '', content)
                content = re.sub(r'&[a-zA-Z]+;', ' ', content)
            
            return content.strip()
        else:
            raise Exception(f"Tipo de arquivo não suportado: {ext}")
            
    except Exception as e:
        logger.error(f"Erro ao extrair texto de {filename}: {str(e)}")
        raise

# ROTAS DA APLICAÇÃO

@app.route('/')
def home():
    """Página principal com interface moderna"""
    return render_template('index.html')

@app.route('/status')
def status():
    """Status da API com informações completas"""
    return jsonify({
        'status': 'online',
        'tts_engine': 'gtts',
        'voices': VOICES,
        'supported_formats': list(ALLOWED_EXTENSIONS),
        'max_file_size_mb': MAX_FILE_SIZE // (1024 * 1024),
        'timestamp': datetime.now().isoformat(),
        'active_files': len(AUDIO_FILES)
    })

@app.route('/voices')
def get_voices():
    """Endpoint específico para carregar vozes"""
    return jsonify({
        'success': True,
        'voices': VOICES,
        'count': len(VOICES)
    })

@app.route('/convert', methods=['POST'])
def convert():
    """Conversão de texto/arquivo para audiobook"""
    try:
        text = ""
        
        # Processar arquivo enviado
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename and allowed_file(file.filename):
                # Verificar tamanho do arquivo
                file.seek(0, os.SEEK_END)
                file_size = file.tell()
                file.seek(0)
                
                if file_size > MAX_FILE_SIZE:
                    return jsonify({
                        'success': False,
                        'error': f'Arquivo muito grande. Máximo: {MAX_FILE_SIZE // (1024 * 1024)}MB'
                    }), 400
                
                filename = secure_filename(file.filename)
                file_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4().hex}_{filename}")
                file.save(file_path)
                
                try:
                    text = extract_text_from_file(file_path, filename)
                    logger.info(f"Texto extraído de {filename}: {len(text)} caracteres")
                finally:
                    # Limpar arquivo temporário
                    if os.path.exists(file_path):
                        os.remove(file_path)
            else:
                return jsonify({
                    'success': False,
                    'error': 'Arquivo inválido ou formato não suportado'
                }), 400
        else:
            # Processar texto direto
            if request.is_json:
                data = request.get_json()
                text = data.get('text', '').strip()
            else:
                text = request.form.get('text', '').strip()

        if not text:
            return jsonify({
                'success': False,
                'error': 'Nenhum texto encontrado para conversão'
            }), 400

        if len(text) < 10:
            return jsonify({
                'success': False,
                'error': 'Texto muito curto (mínimo 10 caracteres)'
            }), 400

        # Parâmetros de voz
        voice = 'pt-BR'
        speed = 1.0
        
        if request.is_json:
            data = request.get_json()
            voice = data.get('voice', 'pt-BR')
            speed = float(data.get('speed', 1.0))
        else:
            voice = request.form.get('voice', 'pt-BR')
            speed = float(request.form.get('speed', 1.0))

        # Validar voz
        if voice not in VOICES:
            voice = 'pt-BR'
            
        # Validar velocidade
        speed = max(0.5, min(2.0, speed))

        # Dividir texto em chunks para o gTTS
        max_chunk_size = 4900
        chunks = []
        
        # Tentar dividir por parágrafos primeiro
        paragraphs = text.split('\n\n')
        current_chunk = ""
        
        for paragraph in paragraphs:
            if len(current_chunk + paragraph) <= max_chunk_size:
                current_chunk += paragraph + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                
                # Se o parágrafo é muito grande, dividir por frases
                if len(paragraph) > max_chunk_size:
                    sentences = paragraph.split('. ')
                    temp_chunk = ""
                    for sentence in sentences:
                        if len(temp_chunk + sentence) <= max_chunk_size:
                            temp_chunk += sentence + ". "
                        else:
                            if temp_chunk:
                                chunks.append(temp_chunk.strip())
                            temp_chunk = sentence + ". "
                    if temp_chunk:
                        current_chunk = temp_chunk
                    else:
                        current_chunk = ""
                else:
                    current_chunk = paragraph + "\n\n"
        
        if current_chunk:
            chunks.append(current_chunk.strip())

        # Gerar áudio
        file_id = str(uuid.uuid4())
        audio_filename = f"audiobook_{file_id}.mp3"
        audio_path = os.path.join(TEMP_DIR, audio_filename)
        
        logger.info(f"Gerando áudio com {len(chunks)} chunks, voz: {voice}, velocidade: {speed}")
        
        with open(audio_path, "wb") as outfile:
            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                    
                try:
                    logger.info(f"Processando chunk {i+1}/{len(chunks)}")
                    tts = gTTS(
                        text=chunk.strip(), 
                        lang=voice, 
                        slow=(speed < 0.8),
                        tld='com.br' if voice == 'pt-BR' else 'com'
                    )
                    
                    temp_mp3 = os.path.join(TEMP_DIR, f"temp_{uuid.uuid4().hex}.mp3")
                    tts.save(temp_mp3)
                    
                    with open(temp_mp3, "rb") as fin:
                        outfile.write(fin.read())
                    
                    if os.path.exists(temp_mp3):
                        os.remove(temp_mp3)
                        
                except Exception as e:
                    logger.error(f"Erro no chunk {i+1}: {str(e)}")
                    continue

        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            return jsonify({
                'success': False,
                'error': 'Falha ao gerar o áudio'
            }), 500

        # Armazenar informações do arquivo
        AUDIO_FILES[file_id] = {
            'filename': audio_filename,
            'path': audio_path,
            'created_at': datetime.now().isoformat(),
            'text_length': len(text),
            'chunks_count': len(chunks),
            'voice': voice,
            'speed': speed,
        }

        file_size = os.path.getsize(audio_path)
        
        logger.info(f"Áudio gerado com sucesso: {file_size} bytes")

        return jsonify({
            'success': True,
            'file_id': file_id,
            'filename': audio_filename,
            'download_url': f'/download/{file_id}',
            'file_size': file_size,
            'file_size_mb': round(file_size / (1024 * 1024), 2),
            'text_length': len(text),
            'chunks_processed': len(chunks),
            'voice': voice,
            'engine': 'gtts',
            'speed': speed,
            'estimated_duration_minutes': round(len(text) / 1000, 1)
        })

    except Exception as e:
        logger.error(f"Erro na conversão: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erro interno: {str(e)}'
        }), 500

@app.route('/download/<file_id>')
def download_audio(file_id):
    """Download do arquivo de áudio gerado"""
    if file_id not in AUDIO_FILES:
        return jsonify({'error': 'Arquivo não encontrado'}), 404
        
    file_info = AUDIO_FILES[file_id]
    if not os.path.exists(file_info['path']):
        return jsonify({'error': 'Arquivo não existe no sistema'}), 404
        
    try:
        return send_file(
            file_info['path'],
            as_attachment=True,
            download_name=file_info['filename'],
            mimetype='audio/mpeg'
        )
    except Exception as e:
        logger.error(f"Erro no download: {str(e)}")
        return jsonify({'error': f'Erro no download: {str(e)}'}), 500

@app.route('/info/<file_id>')
def file_info(file_id):
    """Informações detalhadas do arquivo"""
    if file_id not in AUDIO_FILES:
        return jsonify({'error': 'Arquivo não encontrado'}), 404
    
    file_info = AUDIO_FILES[file_id].copy()
    if os.path.exists(file_info['path']):
        file_info['current_size'] = os.path.getsize(file_info['path'])
        file_info['status'] = 'available'
    else:
        file_info['current_size'] = 0
        file_info['status'] = 'file_missing'
    
    return jsonify(file_info)

@app.route('/cleanup')
def cleanup():
    """Limpeza de arquivos temporários"""
    cleaned = 0
    errors = 0
    
    for file_id, file_info in list(AUDIO_FILES.items()):
        try:
            if os.path.exists(file_info['path']):
                os.remove(file_info['path'])
                cleaned += 1
            del AUDIO_FILES[file_id]
        except Exception as e:
            logger.error(f"Erro limpando {file_id}: {str(e)}")
            errors += 1
    
    return jsonify({
        'success': True,
        'cleaned_files': cleaned,
        'errors': errors,
        'remaining_files': len(AUDIO_FILES)
    })

# TRATAMENTO DE ERROS
@app.errorhandler(413)
def too_large(e):
    return jsonify({'success': False, 'error': 'Arquivo muito grande'}), 413

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'success': False, 'error': 'Erro interno do servidor'}), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({'success': False, 'error': 'Endpoint não encontrado'}), 404

if __name__ == '__main__':
    print("🎧 API Conversor de Texto para Audiobook - Versão Completa")
    print(f"📁 Formatos suportados: {', '.join(ALLOWED_EXTENSIONS)}")
    print(f"🗣️ Vozes disponíveis: {len(VOICES)}")
    print(f"📊 Tamanho máximo: {MAX_FILE_SIZE // (1024 * 1024)}MB")
    print(f"📂 Templates: {app.template_folder}")
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)

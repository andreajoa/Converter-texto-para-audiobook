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
import io
from pydub import AudioSegment
from pydub.silence import split_on_silence

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializar Flask
app = Flask(__name__, 
            template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'),
            static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static'))
CORS(app)

# Configurações
TEMP_DIR = tempfile.gettempdir()
AUDIO_FILES = {}
UPLOAD_FOLDER = os.path.join(TEMP_DIR, 'audiobook_uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Extensões permitidas
ALLOWED_EXTENSIONS = {
    'txt', 'pdf', 'doc', 'docx', 'rtf', 'odt', 
    'csv', 'md', 'html', 'htm', 'xml', 'json'
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Vozes gTTS
VOICES = {
    'pt-BR': {
        'name': 'Português Brasil (Feminina)',
        'gender': 'Feminina',
        'country': 'Brasil',
        'tld': 'com.br'
    },
    'pt': {
        'name': 'Português Portugal (Feminina)',
        'gender': 'Feminina', 
        'country': 'Portugal',
        'tld': 'pt'
    },
    'en': {
        'name': 'English (Female)',
        'gender': 'Female',
        'country': 'United States',
        'tld': 'com'
    },
    'es': {
        'name': 'Español (Femenina)',
        'gender': 'Femenina',
        'country': 'España',
        'tld': 'es'
    },
    'fr': {
        'name': 'Français (Féminin)',
        'gender': 'Féminin',
        'country': 'France',
        'tld': 'fr'
    }
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def detect_encoding(file_path):
    """Detecta a codificação do arquivo"""
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read(10000)  # Lê apenas os primeiros 10KB
            result = chardet.detect(raw_data)
            return result.get('encoding', 'utf-8') or 'utf-8'
    except:
        return 'utf-8'

def extract_text_from_pdf(file_path):
    """Extrai texto de arquivo PDF"""
    try:
        text = ""
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text.strip():
                        text += page_text + "\n\n"
                except Exception as e:
                    logger.warning(f"Erro na página {page_num}: {e}")
                    continue
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
            if paragraph.text.strip():
                text += paragraph.text + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"Erro ao ler DOCX: {str(e)}")
        raise Exception(f"Erro ao processar DOCX: {str(e)}")

def extract_text_from_file(file_path, filename):
    """Extrai texto baseado na extensão do arquivo"""
    ext = filename.rsplit('.', 1)[1].lower()
    
    try:
        if ext == 'pdf':
            return extract_text_from_pdf(file_path)
        elif ext == 'docx':
            return extract_text_from_docx(file_path)
        elif ext in ['txt', 'md', 'csv', 'html', 'htm', 'xml', 'json']:
            encoding = detect_encoding(file_path)
            with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                content = f.read()
                
            # Para HTML, remove tags básicas
            if ext in ['html', 'htm']:
                import re
                content = re.sub(r'<[^>]+>', '', content)
                content = re.sub(r'&[a-zA-Z0-9]+;', ' ', content)
            
            return content.strip()
        else:
            raise Exception(f"Tipo de arquivo não suportado: {ext}")
            
    except Exception as e:
        logger.error(f"Erro ao extrair texto de {filename}: {str(e)}")
        raise

def split_text_intelligently(text, max_length=4500):
    """Divide o texto de forma inteligente para o gTTS"""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    
    # Primeiro, divide por parágrafos
    paragraphs = text.split('\n\n')
    current_chunk = ""
    
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
            
        # Se o parágrafo cabe no chunk atual
        if len(current_chunk + paragraph) <= max_length:
            current_chunk += paragraph + "\n\n"
        else:
            # Salva o chunk atual se não estiver vazio
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            
            # Se o parágrafo é muito grande, divide por frases
            if len(paragraph) > max_length:
                sentences = paragraph.replace('.', '.|').replace('!', '!|').replace('?', '?|').split('|')
                temp_chunk = ""
                
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                        
                    if len(temp_chunk + sentence) <= max_length:
                        temp_chunk += sentence + " "
                    else:
                        if temp_chunk.strip():
                            chunks.append(temp_chunk.strip())
                        temp_chunk = sentence + " "
                
                current_chunk = temp_chunk if temp_chunk.strip() else ""
            else:
                current_chunk = paragraph + "\n\n"
    
    # Adiciona o último chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return [chunk for chunk in chunks if chunk.strip()]

def generate_audio_gtts(text, voice='pt-BR', slow=False):
    """Gera áudio usando gTTS com tratamento de erros melhorado"""
    try:
        voice_config = VOICES.get(voice, VOICES['pt-BR'])
        tld = voice_config.get('tld', 'com')
        
        logger.info(f"Gerando áudio: voz={voice}, tld={tld}, slow={slow}, chars={len(text)}")
        
        # Limpar texto
        text = text.strip()
        if not text:
            raise Exception("Texto vazio para conversão")
        
        # Criar objeto gTTS
        tts = gTTS(
            text=text,
            lang=voice,
            slow=slow,
            tld=tld
        )
        
        # Salvar em buffer de memória primeiro
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        
        # Verificar se o áudio foi gerado
        audio_data = audio_buffer.getvalue()
        if len(audio_data) == 0:
            raise Exception("Áudio gerado está vazio")
        
        logger.info(f"Áudio gerado com sucesso: {len(audio_data)} bytes")
        return audio_data
        
    except Exception as e:
        logger.error(f"Erro no gTTS: {str(e)}")
        raise Exception(f"Erro na geração de áudio: {str(e)}")

@app.route('/')
def home():
    """Página principal"""
    return render_template('index.html')

@app.route('/status')
def status():
    """Status da API"""
    return jsonify({
        'status': 'online',
        'tts_engine': 'gtts',
        'voices': VOICES,
        'supported_formats': list(ALLOWED_EXTENSIONS),
        'max_file_size_mb': MAX_FILE_SIZE // (1024 * 1024),
        'timestamp': datetime.now().isoformat(),
        'active_files': len(AUDIO_FILES),
        'temp_dir': TEMP_DIR
    })

@app.route('/voices')
def get_voices():
    """Endpoint para carregar vozes"""
    return jsonify({
        'success': True,
        'voices': VOICES,
        'count': len(VOICES)
    })

@app.route('/convert', methods=['POST'])
def convert():
    """Conversão principal com correções"""
    try:
        logger.info("Iniciando conversão...")
        text = ""
        
        # Processar arquivo ou texto
        if 'file' in request.files and request.files['file'].filename:
            file = request.files['file']
            
            if not allowed_file(file.filename):
                return jsonify({
                    'success': False,
                    'error': 'Formato de arquivo não suportado'
                }), 400
            
            # Salvar arquivo temporário
            filename = secure_filename(file.filename)
            temp_filename = f"{uuid.uuid4().hex}_{filename}"
            file_path = os.path.join(UPLOAD_FOLDER, temp_filename)
            
            logger.info(f"Salvando arquivo: {file_path}")
            file.save(file_path)
            
            try:
                text = extract_text_from_file(file_path, filename)
                logger.info(f"Texto extraído: {len(text)} caracteres")
            finally:
                # Limpar arquivo
                if os.path.exists(file_path):
                    os.remove(file_path)
        else:
            # Processar texto direto
            if request.is_json:
                data = request.get_json()
                text = data.get('text', '').strip()
            else:
                text = request.form.get('text', '').strip()

        # Validar texto
        if not text:
            return jsonify({
                'success': False,
                'error': 'Nenhum texto encontrado'
            }), 400

        if len(text) < 5:
            return jsonify({
                'success': False,
                'error': 'Texto muito curto (mínimo 5 caracteres)'
            }), 400

        # Obter parâmetros
        if request.is_json:
            data = request.get_json()
            voice = data.get('voice', 'pt-BR')
            speed = float(data.get('speed', 1.0))
        else:
            voice = request.form.get('voice', 'pt-BR')
            speed = float(request.form.get('speed', 1.0))

        # Validar parâmetros
        if voice not in VOICES:
            voice = 'pt-BR'
        speed = max(0.5, min(2.0, speed))
        slow_speech = speed < 0.8

        logger.info(f"Parâmetros: voz={voice}, velocidade={speed}, slow={slow_speech}")

        # Dividir texto
        chunks = split_text_intelligently(text, 4500)
        logger.info(f"Texto dividido em {len(chunks)} chunks")

        if not chunks:
            return jsonify({
                'success': False,
                'error': 'Erro ao processar o texto'
            }), 400

        # Gerar áudio
        file_id = str(uuid.uuid4())
        audio_filename = f"audiobook_{file_id}.mp3"
        audio_path = os.path.join(TEMP_DIR, audio_filename)

        logger.info(f"Gerando áudio: {audio_path}")

        # Gerar e combinar áudios
        audio_segments = []
        
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
                
            try:
                logger.info(f"Processando chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
                
                audio_data = generate_audio_gtts(chunk, voice, slow_speech)
                
                # Converter para AudioSegment se pydub estiver disponível
                try:
                    audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_data))
                    audio_segments.append(audio_segment)
                except ImportError:
                    # Se pydub não estiver disponível, salvar diretamente
                    with open(audio_path, 'ab') as f:
                        f.write(audio_data)
                
            except Exception as e:
                logger.error(f"Erro no chunk {i+1}: {str(e)}")
                continue

        # Combinar segmentos se pydub estiver disponível
        if audio_segments:
            try:
                combined = AudioSegment.empty()
                for segment in audio_segments:
                    combined += segment
                    # Adicionar pequena pausa entre chunks
                    combined += AudioSegment.silent(duration=300)  # 300ms
                
                combined.export(audio_path, format="mp3")
                logger.info("Áudio combinado com pydub")
            except ImportError:
                logger.info("Pydub não disponível, usando concatenação simples")

        # Verificar se o arquivo foi criado
        if not os.path.exists(audio_path):
            return jsonify({
                'success': False,
                'error': 'Falha ao gerar arquivo de áudio'
            }), 500

        file_size = os.path.getsize(audio_path)
        if file_size == 0:
            return jsonify({
                'success': False,
                'error': 'Arquivo de áudio está vazio'
            }), 500

        # Armazenar informações
        AUDIO_FILES[file_id] = {
            'filename': audio_filename,
            'path': audio_path,
            'created_at': datetime.now().isoformat(),
            'text_length': len(text),
            'chunks_count': len(chunks),
            'voice': voice,
            'speed': speed,
            'file_size': file_size
        }

        logger.info(f"Conversão concluída: {file_size} bytes")

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
            'speed': speed,
            'estimated_duration_minutes': round(len(text) / 800, 1)  # ~800 chars/min
        })

    except Exception as e:
        logger.error(f"Erro na conversão: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erro interno: {str(e)}'
        }), 500

@app.route('/download/<file_id>')
def download_audio(file_id):
    """Download do arquivo de áudio"""
    try:
        if file_id not in AUDIO_FILES:
            return jsonify({'error': 'Arquivo não encontrado'}), 404
            
        file_info = AUDIO_FILES[file_id]
        
        if not os.path.exists(file_info['path']):
            return jsonify({'error': 'Arquivo não existe'}), 404
        
        # Verificar se o arquivo não está vazio
        if os.path.getsize(file_info['path']) == 0:
            return jsonify({'error': 'Arquivo está vazio'}), 404
            
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
    """Informações do arquivo"""
    if file_id not in AUDIO_FILES:
        return jsonify({'error': 'Arquivo não encontrado'}), 404
    
    file_info = AUDIO_FILES[file_id].copy()
    
    if os.path.exists(file_info['path']):
        file_info['current_size'] = os.path.getsize(file_info['path'])
        file_info['status'] = 'available'
    else:
        file_info['current_size'] = 0
        file_info['status'] = 'missing'
    
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

# Handlers de erro
@app.errorhandler(413)
def too_large(e):
    return jsonify({'success': False, 'error': 'Arquivo muito grande'}), 413

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'success': False, 'error': 'Erro interno'}), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({'success': False, 'error': 'Não encontrado'}), 404

if __name__ == '__main__':
    print("🎧 Conversor de Texto para Audiobook")
    print(f"📁 Formatos: {', '.join(ALLOWED_EXTENSIONS)}")
    print(f"🗣️ Vozes: {len(VOICES)}")
    print(f"📊 Max: {MAX_FILE_SIZE // (1024 * 1024)}MB")
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)

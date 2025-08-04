from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import os
import tempfile
import uuid
from datetime import datetime
import logging
from werkzeug.utils import secure_filename

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

# Para text-to-speech - múltiplas opções
TTS_ENGINE = None
TTS_TYPE = None

# Tentar Azure Cognitive Services (melhor qualidade)
try:
    import azure.cognitiveservices.speech as speechsdk
    TTS_ENGINE = 'azure'
    TTS_TYPE = 'azure'
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False

# Fallback para pyttsx3
if not TTS_ENGINE:
    try:
        import pyttsx3
        TTS_ENGINE = 'pyttsx3'
        TTS_TYPE = 'local'
        PYTTSX3_AVAILABLE = True
    except ImportError:
        PYTTSX3_AVAILABLE = False

# Fallback para gTTS (Google Text-to-Speech)
if not TTS_ENGINE:
    try:
        from gtts import gTTS
        import pygame
        TTS_ENGINE = 'gtts'
        TTS_TYPE = 'online'
        GTTS_AVAILABLE = True
    except ImportError:
        GTTS_AVAILABLE = False

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

# Vozes disponíveis por engine
VOICES_CONFIG = {
    'azure': {
        'pt-BR-FranciscaNeural': {'name': 'Francisca (Feminina - BR)', 'gender': 'Female', 'country': 'Brasil'},
        'pt-BR-AntonioNeural': {'name': 'Antonio (Masculina - BR)', 'gender': 'Male', 'country': 'Brasil'},
        'pt-BR-BrendaNeural': {'name': 'Brenda (Feminina - BR)', 'gender': 'Female', 'country': 'Brasil'},
        'pt-BR-DonatoNeural': {'name': 'Donato (Masculina - BR)', 'gender': 'Male', 'country': 'Brasil'},
        'pt-BR-ElzaNeural': {'name': 'Elza (Feminina - BR)', 'gender': 'Female', 'country': 'Brasil'},
        'pt-BR-FabioNeural': {'name': 'Fabio (Masculina - BR)', 'gender': 'Male', 'country': 'Brasil'},
        'pt-BR-GiovannaNeural': {'name': 'Giovanna (Feminina - BR)', 'gender': 'Female', 'country': 'Brasil'},
        'pt-BR-HumbertoNeural': {'name': 'Humberto (Masculina - BR)', 'gender': 'Male', 'country': 'Brasil'},
        'pt-BR-JulioNeural': {'name': 'Julio (Masculina - BR)', 'gender': 'Male', 'country': 'Brasil'},
        'pt-BR-LeilaNeural': {'name': 'Leila (Feminina - BR)', 'gender': 'Female', 'country': 'Brasil'},
        'pt-BR-LeticiaNeural': {'name': 'Leticia (Feminina - BR)', 'gender': 'Female', 'country': 'Brasil'},
        'pt-BR-ManuelaNeural': {'name': 'Manuela (Feminina - BR)', 'gender': 'Female', 'country': 'Brasil'},
        'pt-BR-NicolauNeural': {'name': 'Nicolau (Masculina - BR)', 'gender': 'Male', 'country': 'Brasil'},
        'pt-BR-ValerioNeural': {'name': 'Valerio (Masculina - BR)', 'gender': 'Male', 'country': 'Brasil'},
        'pt-BR-YaraNeural': {'name': 'Yara (Feminina - BR)', 'gender': 'Female', 'country': 'Brasil'}
    },
    'gtts': {
        'pt-BR': {'name': 'Google TTS Português Brasil', 'gender': 'Female', 'country': 'Brasil'},
        'pt': {'name': 'Google TTS Português', 'gender': 'Female', 'country': 'Portugal'}
    },
    'pyttsx3': {
        'default': {'name': 'Voz Padrão do Sistema', 'gender': 'Unknown', 'country': 'Sistema'}
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
    """Converter texto para fala usando diferentes engines"""
    
    if TTS_ENGINE == 'azure' and AZURE_AVAILABLE:
        return convert_with_azure(text, voice, speed, file_path)
    elif TTS_ENGINE == 'gtts' and GTTS_AVAILABLE:
        return convert_with_gtts(text, voice, speed, file_path)
    elif TTS_ENGINE == 'pyttsx3' and PYTTSX3_AVAILABLE:
        return convert_with_pyttsx3(text, voice, speed, file_path)
    else:
        raise Exception("Nenhum engine TTS disponível")

def convert_with_azure(text, voice, speed, file_path):
    """Converter usando Azure Speech Services"""
    try:
        # Configurar Azure Speech (você precisa definir sua chave e região)
        speech_key = os.environ.get('AZURE_SPEECH_KEY', 'YOUR_AZURE_KEY')
        service_region = os.environ.get('AZURE_SPEECH_REGION', 'eastus')
        
        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
        speech_config.speech_synthesis_voice_name = voice
        speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3)
        
        # Rate adjustment for Azure
        rate_percent = int((speed - 1.0) * 100)
        if rate_percent != 0:
            rate_adjustment = f"{rate_percent:+d}%"
        else:
            rate_adjustment = "0%"
        
        ssml = f"""
        <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="pt-BR">
            <voice name="{voice}">
                <prosody rate="{rate_adjustment}">
                    {text}
                </prosody>
            </voice>
        </speak>
        """
        
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
        result = synthesizer.speak_ssml_async(ssml).get()
        
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            with open(file_path, 'wb') as audio_file:
                audio_file.write(result.audio_data)
            return True
        else:
            logger.error(f"Azure TTS error: {result.reason}")
            return False
            
    except Exception as e:
        logger.error(f"Erro Azure TTS: {str(e)}")
        return False

def convert_with_gtts(text, voice, speed, file_path):
    """Converter usando Google Text-to-Speech"""
    try:
        lang = voice if voice in ['pt-BR', 'pt'] else 'pt-BR'
        tts = gTTS(text=text, lang=lang, slow=(speed < 0.8))
        
        # gTTS gera MP3, converter nome do arquivo
        mp3_path = file_path.replace('.wav', '.mp3')
        tts.save(mp3_path)
        
        # Se precisar converter para WAV, pode usar pydub aqui
        return True
        
    except Exception as e:
        logger.error(f"Erro gTTS: {str(e)}")
        return False

def convert_with_pyttsx3(text, voice, speed, file_path):
    """Converter usando pyttsx3"""
    try:
        engine = pyttsx3.init()
        
        # Configurar velocidade
        rate = engine.getProperty('rate')
        engine.setProperty('rate', int(rate * speed))
        
        # Configurar voz
        voices = engine.getProperty('voices')
        if voices:
            for voice_obj in voices:
                if 'brazil' in voice_obj.name.lower() or 'portuguese' in voice_obj.name.lower():
                    engine.setProperty('voice', voice_obj.id)
                    break
        
        engine.save_to_file(text, file_path)
        engine.runAndWait()
        
        return os.path.exists(file_path)
        
    except Exception as e:
        logger.error(f"Erro pyttsx3: {str(e)}")
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
        'tts_engine': TTS_ENGINE,
        'tts_type': TTS_TYPE,
        'available_engines': {
            'azure': AZURE_AVAILABLE,
            'gtts': GTTS_AVAILABLE if 'GTTS_AVAILABLE' in globals() else False,
            'pyttsx3': PYTTSX3_AVAILABLE if 'PYTTSX3_AVAILABLE' in globals() else False
        },
        'file_support': {
            'pdf': PDF_AVAILABLE,
            'docx': DOCX_AVAILABLE,
            'excel': EXCEL_AVAILABLE,
            'pptx': PPTX_AVAILABLE
        },
        'voices': VOICES_CONFIG.get(TTS_ENGINE, {}),
        'timestamp': datetime.now().isoformat(),
        'active_files': len(AUDIO_FILES)
    })

@app.route('/voices')
def get_voices():
    """Obter vozes disponíveis"""
    return jsonify({
        'engine': TTS_ENGINE,
        'voices': VOICES_CONFIG.get(TTS_ENGINE, {})
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
            voice = data.get('voice', list(VOICES_CONFIG.get(TTS_ENGINE, {}).keys())[0])
            speed = float(data.get('speed', 1.0))
        else:
            voice = request.form.get('voice', list(VOICES_CONFIG.get(TTS_ENGINE, {}).keys())[0])
            speed = float(request.form.get('speed', 1.0))
        
        logger.info(f"Convertendo {len(text)} caracteres com voz {voice}")
        
        # Gerar arquivo de áudio
        file_id = str(uuid.uuid4())
        audio_filename = f"audiobook_{file_id}.{'mp3' if TTS_ENGINE == 'gtts' else 'wav'}"
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
            'engine': TTS_ENGINE
        }
        
        return jsonify({
            'success': True,
            'file_id': file_id,
            'filename': audio_filename,
            'download_url': f'/download/{file_id}',
            'file_size': os.path.getsize(audio_path),
            'text_length': len(text),
            'voice': voice,
            'engine': TTS_ENGINE
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
            mimetype='audio/mpeg' if file_info['filename'].endswith('.mp3') else 'audio/wav'
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
    print("🎧 Conversor de Texto para Audiobook - Versão Completa")
    print(f"📁 Diretório temporário: {TEMP_DIR}")
    print(f"🎤 Engine TTS: {TTS_ENGINE}")
    print(f"📚 Suporte a arquivos: TXT, PDF{'✓' if PDF_AVAILABLE else '✗'}, DOCX{'✓' if DOCX_AVAILABLE else '✗'}, XLSX{'✓' if EXCEL_AVAILABLE else '✗'}, PPTX{'✓' if PPTX_AVAILABLE else '✗'}")
    print("\n📋 Para instalar todas as dependências:")
    print("pip install flask flask-cors PyPDF2 python-docx openpyxl python-pptx")
    print("pip install pyttsx3 gTTS pygame")  # TTS engines
    print("pip install azure-cognitiveservices-speech")  # Azure (opcional)
    
    app.run(host='0.0.0.0', port=5000, debug=True)

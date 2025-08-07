from flask import Flask, send_from_directory, request, jsonify
import os
import tempfile
import uuid

app = Flask(__name__)

# Rota principal que serve o HTML
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# Rota para conversão (por enquanto simulada)
@app.route('/convert', methods=['POST'])
def convert_text_to_audio():
    try:
        data = request.json
        text = data.get('text', '')
        voice = data.get('voice', 'pt-BR-FranciscaNeural')
        speed = data.get('speed', '1.0')
        
        if not text:
            return jsonify({'error': 'Texto não fornecido'}), 400
        
        # Aqui futuramente você integraria com APIs de TTS
        # Por enquanto, retorna sucesso simulado
        audio_filename = f"audiobook_{uuid.uuid4()}.wav"
        
        return jsonify({
            'success': True,
            'message': 'Conversão realizada com sucesso!',
            'audio_file': audio_filename
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Rota para servir arquivos estáticos
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('.', filename)

if __name__ == '__main__':
    # Pega a porta do ambiente (Render define automaticamente)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

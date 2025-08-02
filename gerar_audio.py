from bark import generate_audio, SAMPLE_RATE, preload_models
from scipy.io.wavfile import write as write_wav

# Carregar modelos
preload_models()

# Texto a ser lido
texto = "Olá! Essa é uma leitura automática feita com Bark, um modelo de voz realista."

# Gerar áudio com voz feminina brasileira
audio_array = generate_audio(texto, history_prompt="v2/pt_speaker_0")

# Salvar como arquivo .wav
write_wav("meu_audio.wav", SAMPLE_RATE, audio_array)

print("✅ Áudio gerado com sucesso: meu_audio.wav")



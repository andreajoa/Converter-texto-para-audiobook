import os
import numpy as np
import torch
from bark import SAMPLE_RATE, generate_audio, preload_models
from scipy.io.wavfile import write as write_wav

# 🔁 Carrega os modelos necessários
preload_models()

# 📝 Seu texto aqui
texto = """
Era uma vez uma menina chamada Maria Luíza. Ela tinha um sorriso doce, olhos curiosos e um coração enorme.
Mas um dia, tudo mudou. Veio um diagnóstico: Diabetes tipo 1. E a vida dela virou uma montanha-russa.
"""

# 🎤 Escolha de voz — 'v2/pt_speaker_0' é uma voz feminina brasileira
audio_array = generate_audio(texto, history_prompt="v2/pt_speaker_0")

# 💾 Salvar como WAV
write_wav("audio_maria.wav", SAMPLE_RATE, audio_array)

print("✅ Áudio gerado com sucesso: audio_maria.wav")

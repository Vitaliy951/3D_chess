import wave
import math
import struct
import os

def create_wav(filename, duration, freq_func):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    sample_rate = 44100
    num_samples = int(duration * sample_rate)
    
    with wave.open(filename, 'w') as wav_file:
        # Настройки: 1 канал (моно), 2 байта на семпл (16 бит), частота 44.1кГц
        wav_file.setparams((1, 2, sample_rate, num_samples, 'NONE', 'not compressed'))
        
        for i in range(num_samples):
            t = i / sample_rate
            # Получаем динамическую частоту из переданной функции
            frequency = freq_func(t, duration)
            # Генерируем синусоидальную волну
            value = math.sin(2 * math.pi * frequency * t)
            
            # Эффект затухания (Fade-out)
            fade = (1.0 - (t / duration))
            value *= fade
            
            # Переводим в 16-битное целое число
            packed_sample = struct.pack('<h', int(value * 32767))
            wav_file.writeframes(packed_sample)
    print(f"Файл успешно создан: {filename}")

# 1. Звук лазера (плавно падающая частота вниз - "пиууу")
def laser_freq(t, duration):
    return 1200 - (t / duration) * 800

# 2. Звук клика (очень короткий высокочастотный щелчок)
def click_freq(t, duration):
    return 800

# 3. Звук взрыва (низкочастотный шум и вибрация)
def explosion_freq(t, duration):
    return 150 * math.sin(t * 10) + 60

# Запуск генерации в вашу папку ассетов
if __name__ == "__main__":
    create_wav("assets/laser_beam.wav", 0.6, laser_freq)
    create_wav("assets/move_click.wav", 0.08, click_freq)
    create_wav("assets/quantum_explosion.wav", 1.2, explosion_freq)

"""Tom de voz real com FFmpeg local; sem modelos, rede ou dispositivo de áudio."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fala


class FalaTomTest(unittest.TestCase):
    def test_dois_semitons_preservam_duracao(self):
        taxa = 24000
        t = np.arange(taxa * 2) / taxa
        original = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        audio, sr = fala.ajustar_tom(original, taxa)
        miolo = audio[taxa // 4:-taxa // 4]
        espectro = np.abs(np.fft.rfft(miolo * np.hanning(len(miolo))))
        frequencia = np.fft.rfftfreq(len(miolo), 1 / sr)[np.argmax(espectro)]
        self.assertAlmostEqual(frequencia, 440 * 2 ** (2 / 12), delta=2)
        self.assertAlmostEqual(len(audio) / sr, len(original) / taxa, delta=.06)
        self.assertEqual(sr, taxa)
        self.assertTrue(np.isfinite(audio).all())

    def test_falha_de_processamento_mantem_voz_original(self):
        original = np.arange(100, dtype=np.float32) / 100
        with patch.object(fala.subprocess, 'run', side_effect=OSError('ffmpeg indisponível')):
            audio, sr = fala.ajustar_tom(original, 24000)
        np.testing.assert_array_equal(audio, original)
        self.assertEqual(sr, 24000)

    def test_audio_vazio_nao_abre_processo(self):
        with patch.object(fala.subprocess, 'run') as rodar:
            audio, sr = fala.ajustar_tom(np.array([], dtype=np.float32), 24000)
        self.assertEqual(audio.size, 0)
        rodar.assert_not_called()


if __name__ == '__main__':
    unittest.main()

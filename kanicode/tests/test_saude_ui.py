"""Aba Saúde do PC: hardware, manutenção rodando (cena da KaniBall) e relatório com decisões — API simulada."""
import json
import unittest
from pathlib import Path
import test_layout as layout

HW = {"ok": True, "geral": 69, "estado": "atenção", "alertas": ["Disco C: só 3% livre (o Windows fica lento com o C cheio)."],
      "pecas": [{"tipo": "cpu", "nome": "Intel Core i7-10700K", "sub": "8 núcleos", "nota": 100, "estado": "bom", "uso": 20, "mhz": 3792, "temp": None},
                {"tipo": "gpu", "nome": "RTX 3050", "sub": "driver 1", "nota": 100, "estado": "bom", "uso": 22, "temp": 47, "vram": [2e9, 8e9]},
                {"tipo": "disco", "nome": "WDC SSD", "sub": "SSD · NVMe · 466 GB", "nota": 55, "estado": "atenção", "saude": "Healthy",
                 "temp": 41, "desgaste": 3, "horas": 9000, "volumes": [{"l": "C", "nome": "SISTEMA", "livre": 15e9, "total": 499e9, "pct": 3.2}]},
                {"tipo": "ram", "nome": "32 GB de RAM", "sub": "2 pentes", "nota": 100, "estado": "bom", "pct": 60, "usada": 19e9, "total": 32e9,
                 "pentes": [{"gb": 16, "slot": "ChannelB-DIMM1"}]}],
      "sistema": {"so": {"nome": "Windows 11 Pro", "build": "26300"}, "defender": {"ligado": True, "assinatura": "2026-10-24T07:00:00", "rapida": "2026-10-23T16:00:00", "completa": {}},
                  "dias_boot": 0.4, "processos": 339}, "manutencao": None}
ETS = ["preparar", "sensores", "limpeza", "navegadores", "kanivete", "duplicados", "virus", "drivers", "reparo", "discos"]


def estado(sit):
    ets = [{"id": i, "nome": i.capitalize(), "estado": ("ok" if k < 3 else "rodando" if k == 3 else "espera") if sit == "rodando" else "ok",
            "detalhe": "12,8 GB" if k < 3 else "Slack/Cache", "progresso": 40, "liberado": 0} for k, i in enumerate(ETS)]
    return {"situacao": sit, "seco": False, "etapas": ets, "agora": "navegadores" if sit == "rodando" else None, "liberado": 26e9,
            "discos_antes": {"C": {"livre": 15e9, "total": 499e9}}, "discos_depois": {"C": {"livre": 40e9, "total": 499e9}},
            "ameacas": [{"id": "2147", "nome": "PUA:Win32/Presenoker", "nivel": "baixa", "recomendo": "avaliar", "recursos": "file:_C:/x.exe", "nova": True}] if sit != "rodando" else [],
            "drivers": [{"nome": "Intel - System - 1.2", "ok": True, "data": "2026-01-01"}],
            "duplicados": [{"tamanho": 5e6, "manter": "C:/Users/P/Pictures/a.jpg", "copias": ["C:/Users/P/Downloads/a (1).jpg"]}], "avisos": []}


@unittest.skipUnless(layout.sync_playwright, 'Playwright opcional não instalado')
class SaudeUITest(unittest.TestCase):
    setUpClass = layout.LayoutTest.__dict__["setUpClass"]

    def setUp(self):
        layout.LayoutTest.setUp(self)
        self.page.set_viewport_size({"width": 920, "height": 900})
        self.page.evaluate('''([hw]) => { window.saudeSit = 'nada'; window.saudeChamadas = [];
          const anterior = pywebview.api;
          pywebview.api = new Proxy(anterior, {get(alvo, nome) {
            if (nome === 'saude_ler') return async () => hw;
            if (nome === 'saude_estado') return async () => window.saudeEst || {situacao: 'nada'};
            if (nome.startsWith('saude_')) return async (...a) => { saudeChamadas.push([nome, a]); return {ok: true, movidos: 1, bytes: 5e6}; };
            if (nome === 'rosto_quadros') return async () => ({fps: 10, quadros: [Array(16).fill('....##....##....')]});
            return alvo[nome]; }}); }''', [HW])

    def test_hardware_manutencao_e_relatorio(self):
        p = self.page
        p.locator('#saude-trilho').click()
        p.wait_for_selector('#saude-painel .sd-card', state='visible')
        self.assertIn('69', p.locator('.sd-hero-n').inner_text())
        p.screenshot(path='D:/kanivete_testes/saude/ui_hardware.png')
        p.locator('#sd-op').click()
        p.locator('[data-op="seco"]').check()
        p.locator('#sd-iniciar').click()
        p.wait_for_function("saudeChamadas.some(c => c[0] === 'saude_iniciar' && c[1][0].seco)")
        p.evaluate('e => { window.saudeEst = e; }', estado('rodando'))
        p.wait_for_selector('.sd-mbox.on canvas', state='visible')
        p.wait_for_timeout(800)
        p.screenshot(path='D:/kanivete_testes/saude/ui_rodando.png')
        p.evaluate('e => { window.saudeEst = e; }', estado('decidir'))
        p.wait_for_selector('#sd-aplicar', state='visible')
        p.locator('.sd-esc button[data-v="remover"]').click()
        p.locator('#sd-aplicar').click()
        p.wait_for_function("saudeChamadas.some(c => c[0] === 'saude_decidir' && c[1][0]['2147'] === 'remover')")
        p.locator('#sd-dup-ir').click()
        p.wait_for_function("saudeChamadas.some(c => c[0] === 'saude_lixeira' && c[1][0][0].includes('a (1).jpg'))")
        p.screenshot(path='D:/kanivete_testes/saude/ui_relatorio.png', full_page=True)
        self.assertEqual(self.erros, [])


if __name__ == '__main__':
    unittest.main()

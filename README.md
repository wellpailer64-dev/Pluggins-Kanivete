# Plugins pessoais do KANIVETE

Ferramentas que moram só no PC do Pailer, fora do app e do release. O KANIVETE lê `D:\Kanivete\Plugins`, que é uma
junção (atalho de pasta) para esta pasta: `mklink /J "D:\Kanivete\Plugins" "<esta pasta>"`.

Cada plugin é uma pasta com um `kanivete.json` (nome, ícone, js/css do painel e o módulo Python). Formato e carregador:
`Functions/plugins_pessoais.py` e `Instructions/agente/plugins.md` › Plugins pessoais, no repositório do KANIVETE.

| Plugin | O que faz |
|---|---|
| `pandalab` | Demandas do Laboratório Panda: listar, baixar na pasta certa do cliente, status, comentários, entrega |
| `kanibrowser` | Chrome do KANIVETE por canal privado (pipe, sem porta), com os logins guardados |

## Não vão para o git (`.gitignore`)
- `pandalab/config.json`: endereço e chave do sistema. Copie `config.exemplo.json` e preencha.
- `pandalab/sessao.bin`: sessão cifrada pelo Windows (só este usuário neste PC abre).
- `pandalab/vinculos.json` e `pandalab/mapa_clientes.json`: dados de clientes e das pastas deste PC.

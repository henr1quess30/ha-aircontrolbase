# AirControlBase (CCM21) — Home Assistant Custom Integration

Integração nativa para o **AirControlBase / CCM21** (gateway centralizado de ar-condicionado). Substitui Node-RED + MQTT por uma integração de primeira classe com descoberta automática de ACs, controle de clima e bloqueios.

> Logbook, histórico e agendamento são feitos pelas próprias funcionalidades nativas do Home Assistant (Logbook, History, Automations, Scripts) — esta integração foca em expor os ACs como entidades reais.

## Recursos

- **Climate** por AC — on/off, modos (cool, heat, auto, dry, fan_only), velocidade do vento (low/mid/high/auto), temperatura alvo (17–30 °C), temperatura atual.
- **Sensores de resumo** — ACs em cada modo (cool/heat/fan/stop/lock/error), total.
- **Switches de lock** por AC — bloquear controle remoto, modo, modo cool, modo heat, ventilação.
- **Serviço** `aircontrolbase.refresh` — força poll imediato.
- **Auto re-login** — detecta `code: 40018` e refaz sessão automaticamente.
- **Polling** — 20 s.
- **i18n** — interface em pt-BR e en, com fan modes localizados ("mid" → "Médio" / "Medium").

## Instalação

### Via HACS (Custom Repository)

1. HACS → Integrações → menu (⋮) → **Custom repositories**
2. URL: `https://github.com/henr1quess30/ha-aircontrolbase`
3. Category: **Integration** → Add
4. Procure "AirControlBase (CCM21)" e clique **Download**
5. Reinicie o Home Assistant
6. Configurações → Dispositivos e Serviços → **Adicionar Integração** → "AirControlBase"

### Manual

1. Copie `custom_components/aircontrolbase/` para `<config>/custom_components/aircontrolbase/`.
2. Reinicie o Home Assistant.
3. Settings → Devices & Services → Add Integration → "AirControlBase".

## Configuração

Na adição da integração:

- **E-mail / conta**: o mesmo usado no [aircontrolbase.com](https://www.aircontrolbase.com).
- **Senha**: idem.

Se o `userId` não for detectado automaticamente do login, a integração pedirá manualmente. Para encontrá-lo:

1. Faça login no aircontrolbase.com.
2. Abra DevTools (F12) → aba **Network**.
3. Clique em qualquer página (ex.: "Controle de dispositivos").
4. Procure uma requisição `getDetails` → aba **Payload** → você verá `userId=<seu_id>`.

## Entidades criadas

Para cada AC:
- `climate.<nome_do_ac>`
- `switch.<nome_do_ac>_bloquear_controle_remoto`
- `switch.<nome_do_ac>_bloquear_modo`
- `switch.<nome_do_ac>_bloquear_modo_resfriar`
- `switch.<nome_do_ac>_bloquear_modo_aquecer`
- `switch.<nome_do_ac>_bloquear_ventilação`

Para o hub (1 vez):
- `sensor.acs_resfriando`
- `sensor.acs_aquecendo`
- `sensor.acs_em_ventilação`
- `sensor.acs_desligados`
- `sensor.acs_bloqueados`
- `sensor.acs_com_erro`
- `sensor.total_de_acs`

## Por que não tem histórico e agendamento?

O Home Assistant já oferece:

- **Logbook** + **History** — registra automaticamente todo comando e mudança de estado das entidades climate/switch.
- **Automations** e **Scripts** — substituem completamente o agendamento do AirControlBase, com mais flexibilidade (condições, gatilhos, integração com calendário, presença, etc.).

Manter essas features na integração seria duplicar o que o HA já faz melhor.

## Desenvolvimento

```
custom_components/aircontrolbase/
├── __init__.py        # setup/unload + registro do serviço refresh
├── api.py             # cliente HTTP async (aiohttp)
├── config_flow.py     # UI de login
├── const.py           # constantes e endpoints
├── coordinator.py     # DataUpdateCoordinator (poll 20s)
├── climate.py         # entidades climate por AC
├── sensor.py          # 7 sensores de resumo
├── switch.py          # 5 switches de lock por AC
├── services.py        # handler do refresh
├── services.yaml      # schema do serviço
├── manifest.json
└── translations/
    ├── en.json
    └── pt-BR.json
```

## Dashboard de exemplo

O arquivo [`examples/dashboard.yaml`](examples/dashboard.yaml) traz uma view pronta com seções "Grupos" (climates de área), sub-áreas internas e resumo. Como aplicar:

1. No HA: ⋮ no canto superior direito do dashboard → **Editar dashboard** → ⋮ → **Editor de configuração bruta**
2. Cole o conteúdo (substituindo ou como nova view)
3. Ajuste os `entity_id` se forem diferentes do seu setup

## Licença

MIT — veja `LICENSE`.

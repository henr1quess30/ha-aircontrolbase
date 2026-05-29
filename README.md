# AirControlBase (CCM21) — Home Assistant Custom Integration

Integração nativa para o **AirControlBase / CCM21** (gateway centralizado de ar-condicionado da Hitachi/HiSense). Substitui o fluxo Node-RED + MQTT Discovery por uma integração de primeira classe no Home Assistant, com config flow via UI, descoberta automática de devices, locks por AC e agendamento.

## Recursos

- **Climate** por AC — on/off, modos (cool, heat, auto, dry, fan_only), velocidade do vento (low/mid/high/auto), temperatura alvo (17–30 °C), temperatura atual.
- **Sensores de resumo** — contagem de ACs em cada modo (cool/heat/fan/stop/lock/error), total de ACs.
- **Switches de lock** por AC — bloquear controle remoto, modo, modo cool, modo heat, ventilação.
- **Serviços** — `aircontrolbase.create_schedule`, `aircontrolbase.update_schedule`, `aircontrolbase.refresh`.
- **Auto re-login** — detecta `code: 40018` e refaz sessão automaticamente.
- **Polling** — 20 s.

## Instalação

### Via HACS (Custom Repository)

1. HACS → Integrações → menu (⋮) → **Custom repositories**
2. URL: `https://github.com/henr1quess30/ha-aircontrolbase`
3. Category: **Integration** → Add
4. Instale "AirControlBase (CCM21)"
5. Reinicie o Home Assistant
6. Configurações → Dispositivos e Serviços → **Adicionar Integração** → "AirControlBase"

### Manual

1. Copie `custom_components/aircontrolbase/` para `<config>/custom_components/aircontrolbase/` no HA.
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
- `switch.<nome_do_ac>_bloquear_modo_cool`
- `switch.<nome_do_ac>_bloquear_modo_heat`
- `switch.<nome_do_ac>_bloquear_ventilação`

Para o hub (1 vez):
- `sensor.acs_em_modo_cool`
- `sensor.acs_em_modo_heat`
- `sensor.acs_em_modo_fan`
- `sensor.acs_desligados`
- `sensor.acs_travados`
- `sensor.acs_com_erro`
- `sensor.total_de_acs`

## Serviços

### `aircontrolbase.create_schedule`

```yaml
service: aircontrolbase.create_schedule
data:
  device_ids: ["40783271", "40783272"]
  timer: "08:00"
  mode: cool
  temperature: 22
  fan_mode: auto
  weeks: [1, 2, 3, 4, 5]   # seg–sex
  cycle: true
```

### `aircontrolbase.update_schedule`

Igual ao acima, mas exigindo `schedule_id` (sid) — obtido do endpoint interno `schedule/getAll`.

### `aircontrolbase.refresh`

Força um poll imediato.

## Limitações conhecidas

- Apenas ACs gerenciados pelo CCM21 são detectados (a API só lista esses).
- Deleção de agendamento ainda não suportada — endpoint não mapeado.
- Histórico (`controlLog`, `deviceLog`, `loginLog`) está implementado no cliente mas ainda não exposto como entidade no HA. Próxima versão.

## Desenvolvimento

Estrutura:

```
custom_components/aircontrolbase/
├── __init__.py        # setup/unload + registro de serviços
├── api.py             # cliente HTTP async (aiohttp)
├── config_flow.py     # UI de login
├── const.py           # constantes e endpoints
├── coordinator.py     # DataUpdateCoordinator
├── climate.py         # entidades climate por AC
├── sensor.py          # sensores de resumo
├── switch.py          # switches de lock
├── services.py        # handlers de serviços
├── services.yaml      # schema dos serviços
├── manifest.json
└── translations/
    ├── en.json
    └── pt-BR.json
```

## Créditos

Engenharia reversa baseada em flow original Node-RED + capturas de DevTools.

## Licença

MIT — veja `LICENSE`.

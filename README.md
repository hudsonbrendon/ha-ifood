# iFood para Home Assistant

Integração não oficial que acompanha os seus pedidos do iFood: status em tempo real, código de entrega,
previsão de chegada, histórico, gastos e um evento a cada mudança de status para notificações.

Usa a mesma API do site (`marketplace.ifood.com.br`). Detalhes em [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md).

## Instalação

Copie `custom_components/ifood` para `/config/custom_components/` (ou adicione o repositório no Marketplace/HACS)
e reinicie o Home Assistant.

## Configuração

1. Entre em <https://www.ifood.com.br> no navegador.
2. DevTools → Application → Cookies → `https://www.ifood.com.br`: copie `aRefreshToken` e `aDeviceId`
   (e, se quiser, `aAccessToken`).
3. Configurações → Dispositivos e serviços → Adicionar integração → **iFood** → cole os valores.

O token é renovado sozinho. Se a sessão for revogada, o HA abre um reparo pedindo cookies novos.

## Entidades (dispositivo "iFood")

| Entidade | O quê |
|---|---|
| `sensor.ifood_pedido_em_andamento` | status em português ("Confirmado", "Saiu para entrega"...) ou "Nenhum"; atributos com restaurante, itens, total, código de entrega, linha do tempo, rastreio |
| `sensor.ifood_previsao_de_entrega` | horário previsto (timestamp) |
| `sensor.ifood_codigo_de_entrega` | código que o entregador pede |
| `binary_sensor.ifood_pedido_aberto` | ligado com pedido aberto |
| `sensor.ifood_ultimo_pedido`, `..._data_do_ultimo_pedido`, `..._valor_do_ultimo_pedido` | último pedido |
| `sensor.ifood_gasto_no_mes`, `..._pedidos_no_mes`, `..._gasto_no_ano`, `..._pedidos_no_ano` | gastos (só pedidos concluídos) |
| `sensor.ifood_gasto_total`, `..._total_de_pedidos`, `..._ticket_medio`, `..._pedidos_recusados` | histórico disponível na API (~6 meses) |
| `sensor.ifood_economia_no_mes`, `..._economia_total`, `..._taxas_de_entrega_no_mes` | cupons/clube e taxas |
| `sensor.ifood_restaurante_favorito` | mais pedido (+ top 5) |
| `sensor.ifood_cliente_desde` | data de cadastro, nome e endereços |
| `calendar.ifood_pedidos` | um evento por pedido |

Polling: 30 s com pedido aberto, 10 min sem pedido.

## Evento `ifood_pedido_atualizado`

Disparado a cada passo novo da linha do tempo (`CONFIRMED`, `DISPATCHED`, `RECEIVED_BY_CUSTOMER`, `CONCLUDED`...).
Dados: `evento`, `descricao` (pt-BR), `momento`, `status_pedido`, `id`, `numero`, `restaurante`, `total`,
`previsao_entrega`, `codigo_entrega`, `itens`, `metadados`.

```yaml
automation:
  - alias: iFood - avisar status
    triggers:
      - trigger: event
        event_type: ifood_pedido_atualizado
    actions:
      - action: notify.notify
        data:
          title: "iFood: {{ trigger.event.data.restaurante }}"
          message: >-
            {{ trigger.event.data.descricao }}
            {% if trigger.event.data.codigo_entrega %}· código {{ trigger.event.data.codigo_entrega }}{% endif %}
```

## Teste

`python3 -I tests/test_logic.py`

<p align="center">
  <img src="custom_components/ifood/brand/icon@2x.png" width="128" alt="iFood">
</p>

# iFood para Home Assistant

Integração **não oficial** que traz a sua conta do iFood para o Home Assistant:

- **Pedido em andamento**: status em português ("Confirmado", "Saiu para entrega"...), previsão de chegada, código de entrega, itens e linha do tempo.
- **Notificações**: um evento a cada mudança de status do pedido e a cada cupom novo.
- **Histórico e gastos**: último pedido, gasto no mês/ano, ticket médio, economia com cupons, taxas de entrega, calendário de pedidos.
- **Cupons**: quantos você tem, quais vencem nos próximos 7 dias, maior desconto, calendário de vencimentos.
- **Clube iFood** e **saldo da carteira**.
- **Suas lojas favoritas ao vivo**: aberta agora, horários, tempo e taxa de entrega, distância, nota e o preço de hoje do prato que você sempre pede.

> [!WARNING]
> O iFood não tem API pública para clientes. Esta integração usa a mesma API do site www.ifood.com.br,
> descoberta por engenharia reversa ([REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md)). Ela pode parar de
> funcionar se o iFood mudar algo. Projeto pessoal, sem vínculo com o iFood. Use por sua conta e risco.
> A integração só **lê** dados: não faz pedidos, não aplica cupons e não mexe em pagamentos.

## Instalação

### Via HACS / Marketplace (recomendado)

[![Abrir no Home Assistant](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=hudsonbrendon&repository=ha-ifood&category=integration)

Ou manualmente:

1. No Home Assistant, abra **HACS** (no HA 2026.11+: **Marketplace**).
2. Menu ⋮ → **Repositórios personalizados**.
3. URL `https://github.com/hudsonbrendon/ha-ifood`, categoria **Integração** → **Adicionar**.
4. Procure **iFood**, clique em **Baixar**.
5. **Reinicie** o Home Assistant.

### Manual

1. Baixe a [última versão](https://github.com/hudsonbrendon/ha-ifood/releases/latest).
2. Copie a pasta `custom_components/ifood` para `/config/custom_components/ifood` no seu Home Assistant.
3. **Reinicie** o Home Assistant.

## Configuração

O login do iFood usa código por SMS/WhatsApp e às vezes pede selfie ou captcha, o que não dá para fazer de dentro
do Home Assistant. Por isso a integração usa a **sessão do site**: você entra no iFood pelo navegador uma vez e
copia 4 valores.

### 1. Pegue os valores no navegador (computador)

1. Abra <https://www.ifood.com.br> e **entre na sua conta**.
2. Abra o console do navegador: `F12` (ou `Cmd+Option+J` no Mac) → aba **Console**.
3. Cole o código abaixo e aperte Enter. Se o Chrome pedir, digite `allow pasting` antes.

```js
(() => {
  const c = Object.fromEntries(document.cookie.split('; ').map(s => {
    const i = s.indexOf('=');
    return [s.slice(0, i), decodeURIComponent(s.slice(i + 1))];
  }));
  const p = Object.keys(c).find(k => k.startsWith('x-ifood-device-payment-'));
  const out = {
    'Refresh token': c.aRefreshToken,
    'Device ID': c.aDeviceId,
    'Access token': c.aAccessToken,
    'Segredo de pagamento': p ? c[p] : '(não encontrado)',
  };
  console.log(Object.entries(out).map(([k, v]) => `${k}:\n${v}`).join('\n\n'));
})();
```

O código só lê os cookies do iFood e mostra na tela. Nada é enviado para lugar nenhum.

<details>
<summary>Prefere sem código? Pelo DevTools</summary>

`F12` → **Application** (Aplicativo) → **Cookies** → `https://www.ifood.com.br`. Copie o valor de:

| Cookie | Campo na integração |
|---|---|
| `aRefreshToken` | Refresh token |
| `aDeviceId` | Device ID |
| `aAccessToken` | Access token |
| `x-ifood-device-payment-…` (o nome termina com um código) | Segredo de pagamento |

</details>

### 2. Adicione a integração

1. **Configurações → Dispositivos e serviços → Adicionar integração → iFood**.
2. Cole os valores:

| Campo | Obrigatório | Para quê |
|---|---|---|
| Refresh token | sim | mantém você logado (vale ~6 meses e é renovado sozinho) |
| Device ID | sim | o iFood exige junto com o token |
| Access token | não, mas recomendado | evita gastar uma renovação logo na configuração (o iFood limita renovações) |
| Segredo de pagamento | não | libera o **saldo da carteira** |

Pronto. Os dados aparecem em alguns segundos.

### Sessão e renovação

- O token de uso dura 2 horas e é **renovado automaticamente** antes de vencer. Você não precisa fazer nada.
- O login (refresh token) dura ~6 meses e também é renovado a cada troca, então na prática não vence.
- Você pode continuar usando o site normalmente: navegador e Home Assistant convivem com a mesma sessão.
- Se você clicar em **Sair** no site, desconectar aparelhos no app ou trocar a senha, a sessão cai. O Home Assistant
  mostra um aviso de **reautenticação**. Repita o passo 1 e cole os valores novos.

## Entidades

### Dispositivo "iFood" (sua conta)

| Entidade | O quê |
|---|---|
| `sensor.ifood_pedido_em_andamento` | status em português ou "Nenhum". Atributos: restaurante, itens, total, previsão, código de entrega, linha do tempo, rastreio |
| `sensor.ifood_previsao_de_entrega` | horário previsto de chegada |
| `sensor.ifood_codigo_de_entrega` | código que o entregador pede na porta |
| `binary_sensor.ifood_pedido_aberto` | ligado enquanto há pedido em andamento |
| `sensor.ifood_ultimo_pedido` | restaurante do último pedido (+ detalhes nos atributos) |
| `sensor.ifood_data_do_ultimo_pedido`, `sensor.ifood_valor_do_ultimo_pedido` | |
| `sensor.ifood_gasto_no_mes`, `sensor.ifood_pedidos_no_mes` | só pedidos concluídos |
| `sensor.ifood_gasto_no_ano`, `sensor.ifood_pedidos_no_ano` | |
| `sensor.ifood_gasto_total`, `sensor.ifood_total_de_pedidos`, `sensor.ifood_ticket_medio` | dentro do histórico que a API devolve (~6 meses) |
| `sensor.ifood_pedidos_recusados` | recusados/cancelados |
| `sensor.ifood_economia_no_mes`, `sensor.ifood_economia_total` | descontos de cupom/clube |
| `sensor.ifood_taxas_de_entrega_no_mes` | |
| `sensor.ifood_restaurante_favorito` | o mais pedido (+ top 5) |
| `sensor.ifood_cliente_desde` | data de cadastro (+ nome e endereços) |
| `sensor.ifood_cupons_disponiveis` | cupons válidos. Atributos: lista com valor, categoria e vencimento; contagem por categoria |
| `sensor.ifood_cupons_vencendo_em_7_dias`, `sensor.ifood_cupons_do_clube` | |
| `sensor.ifood_proximo_cupom_vence` | quando vence o próximo cupom (+ qual) |
| `sensor.ifood_maior_cupom_de_restaurante` | maior desconto em restaurante (R$) |
| `binary_sensor.ifood_clube_ifood`, `sensor.ifood_plano_do_clube` | assinatura do Clube (estimada a partir de dados internos da conta) |
| `sensor.ifood_saldo_da_carteira` | saldo da conta iFood (precisa do segredo de pagamento) |
| `calendar.ifood_pedidos` | um evento por pedido |
| `calendar.ifood_cupons` | vencimento de cada cupom |

### Dispositivo "iFood &lt;loja&gt;" (as 3 lojas que você mais pede)

| Entidade | O quê |
|---|---|
| `binary_sensor.ifood_<loja>_aberto` | aceitando pedido agora. Atributos: horários da semana, aceita agendamento |
| `sensor.ifood_<loja>_tempo_de_entrega` | minutos até o endereço da sua última entrega |
| `sensor.ifood_<loja>_taxa_de_entrega` | R$ |
| `sensor.ifood_<loja>_distancia` | km |
| `sensor.ifood_<loja>_nota` | nota. Atributos: nº de avaliações e médias (embalagem, tempo de entrega...) |
| `sensor.ifood_<loja>_pedido_minimo` | R$ |
| `sensor.ifood_<loja>_preco_do_prato_de_sempre` | preço de hoje do item que você mais pede. Atributos: último preço pago, variação, quantas vezes pediu |

As lojas são escolhidas quando a integração carrega. Se o seu ranking mudar, recarregue a integração.

### Atualização

| O quê | Frequência |
|---|---|
| Pedidos (com pedido aberto) | 30 s |
| Pedidos (sem pedido aberto) | 10 min |
| Lojas ao vivo | 10 min |
| Cupons, Clube, carteira, horários e notas | 1 h |

## Eventos

### `ifood_pedido_atualizado`

Disparado a cada passo novo do pedido: `PLACED` (enviado ao restaurante), `CONFIRMED`, `DISPATCHED` (saiu para entrega),
`RECEIVED_BY_CUSTOMER` (entregue), `CONCLUDED`, `DECLINED`, `CANCELLED` e, com entregador do iFood, passos como
`ASSIGN_DRIVER`, `COLLECTED`, `ARRIVED_AT_DESTINATION`.

Dados: `evento`, `descricao` (pt-BR), `momento`, `status_pedido`, `id`, `numero`, `restaurante`, `total`,
`previsao_entrega`, `codigo_entrega`, `itens`, `metadados`.

### `ifood_cupom_novo`

Disparado quando aparece cupom novo na carteira. Dados: `descricao`, `valor_max`, `categoria`, `vence_em`, `clube`, `regras`.

## Exemplos de automação

**Avisar cada mudança de status do pedido**

```yaml
alias: iFood - status do pedido
triggers:
  - trigger: event
    event_type: ifood_pedido_atualizado
actions:
  - action: notify.notify
    data:
      title: "iFood: {{ trigger.event.data.restaurante }}"
      message: >-
        {{ trigger.event.data.descricao }}
        {%- if trigger.event.data.codigo_entrega %} · código {{ trigger.event.data.codigo_entrega }}{% endif %}
```

**Pedido saiu para entrega: acender a luz da entrada**

```yaml
alias: iFood - saiu para entrega
triggers:
  - trigger: event
    event_type: ifood_pedido_atualizado
    event_data:
      evento: DISPATCHED
actions:
  - action: light.turn_on
    target:
      entity_id: light.entrada
```

**Cupom novo**

```yaml
alias: iFood - cupom novo
triggers:
  - trigger: event
    event_type: ifood_cupom_novo
actions:
  - action: notify.notify
    data:
      title: "Cupom novo no iFood"
      message: "{{ trigger.event.data.descricao }} ({{ trigger.event.data.categoria }})"
```

**Avisar quando o restaurante abrir** (troque `<loja>` pelo nome da sua)

```yaml
alias: iFood - restaurante abriu
triggers:
  - trigger: state
    entity_id: binary_sensor.ifood_<loja>_aberto
    from: "off"
    to: "on"
actions:
  - action: notify.notify
    data:
      message: "Abriu! Entrega em {{ states('sensor.ifood_<loja>_tempo_de_entrega') }} min."
```

## Solução de problemas

| Sintoma | Causa e solução |
|---|---|
| "Token inválido ou expirado" ao configurar | A sessão do site caiu. Entre de novo em ifood.com.br e copie os valores outra vez |
| "O iFood limitou as renovações de token" | O iFood só aceita uma renovação a cada ~20 min. Preencha também o **Access token** ou espere alguns minutos |
| Aviso de reautenticação no HA | Você saiu da conta no site/app ou trocou a senha. Repita o passo 1 |
| Saldo da carteira vazio | Faltou o **Segredo de pagamento**. Remova e adicione a integração de novo com ele |
| Sensores da loja sem valor ("desconhecido") | A loja não entrega no endereço da sua última entrega, ou o iFood não informou o dado |
| Histórico menor do que o esperado | A API do iFood só devolve ~6 meses de pedidos |

Para logs detalhados, adicione ao `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.ifood: debug
```

## Privacidade

Os tokens ficam salvos só no seu Home Assistant (em `.storage/core.config_entries`, como em qualquer integração
de nuvem) e entram nos backups do HA. A integração fala apenas com servidores do iFood
(`marketplace.ifood.com.br`, `cw-marketplace.ifood.com.br`, `payment.ifood.com.br`).

## Desenvolvimento

```bash
python3 -I tests/test_logic.py
uv run --with aiohttp python -I tests/test_refresh.py
```

Detalhes da API em [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md).

## Licença

[MIT](LICENSE)

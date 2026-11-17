# iFood: engenharia reversa (site, nov/2026)

Fonte: bundles Next.js de `www.ifood.com.br` (`_app-*.js`, `Orders-*.js`) + chamadas reais com sessão logada.

## Hosts

| Host | Uso | Headless |
|---|---|---|
| `https://www.ifood.com.br/site-api/` | proxy do site (EXTERNAL_MARKETPLACE_URL) | **não**: Cloudflare "Just a moment" (403) + PerimeterX |
| `https://marketplace.ifood.com.br` | origem do marketplace | **sim**: só Bearer, sem desafio |
| `https://consumer-api.ifood.com.br` | outras rotas (`/ip`) | rotas de pedido = 404 |

Anti-bot no site: PerimeterX (`px-cloud.net`, headers `x-px-cookies`/`x-px-cookie`), Incognia (`icg-in.com`), fingerprint `fstr.rocks`. Nada disso é exigido no host de origem.

## Sessão

Cookies em `www.ifood.com.br` após login:

- `aAccessToken`: JWT, vida de ~2 h
- `aRefreshToken`: JWT (claims `did`, `sub`, `tenantId`, `refresh_token_type`, `wallet_type`), vida de ~6 meses
- `aDeviceId` (UUID, vai em `X-Ifood-Device-Id`), `aAccountId`, `aSessionId`

Renovação: `POST /v2/access_tokens` `{"refresh_token": ...}` + `X-Ifood-Device-Id` →
`201 {access_token, refresh_token}` (resposta gzip). Access novo vale 2 h; refresh novo vale 180 dias.
O refresh **gira**, mas o anterior continua aceito (testado: token antigo renovou de novo ~25 min depois),
então navegador e HA convivem com a mesma sessão. **Rate limit agressivo**: 429 `API rate limit exceeded`
por ~20 min depois de uma renovação; a integração só renova a menos de 10 min do `exp`.

Login (não usado pela integração): OTP via `POST v3/identity-providers/OTP/authorization-codes`
(`type` PHONE/WHATSAPP/EMAIL, header `X-Ifood-Auth-Context-Id`) → `v2/identity-providers/OTP/access-tokens`
→ `v3/identity-providers/OTP/authentications`. Pode responder 428 com `WWW-Authenticate` +
`x-ifood-auth-scope` (desafio: selfie/`match_face`, `identity_verification`, double OTP).

## Headers que o cliente manda

`Authorization: Bearer <access>`, `X-Ifood-Device-Id`, `platform: Desktop`, `app_version`, `country: br`.
Opcionais vistos: `X-Ifood-Session-Id`, `account_id`, `x-ifood-user-id`.

## Endpoints (Bearer)

| Rota | Resposta |
|---|---|
| `GET /v4/customers/me/orders?page=N&size=M` | lista (mais novo primeiro). Campos: `id, orderNumber, createdAt, closedAt, lastStatus, details{mode,scheduled}, delivery{address, estimatedTimeOfArrival{deliversAt,deliversEndAt}}, merchant{id,name,logo,type}, payments{methods[],total{value}}, bag{items[],subTotal,deliveryFee,total{value,valueWithDiscount},benefits[]}, fees[], verificationCodes[{name:DELIVERY_CODE,value}], deliveryOperation{executions[{lastState, deliveryParameters{logisticProvider}}]}, origin{platform,appVersion}`. Valores em centavos. Histórico visto: ~6 meses |
| `GET /v3/customers/me/orders/{id}` | mesmo formato, 1 pedido |
| `GET /v1/customers/me/orders/{id}/events` | timeline `[{eventId, timestamp, value, metadata}]` |
| `GET /v1/customers/me/orders/{id}/tracking` | rastreio do entregador; **404 quando a entrega é da loja** (`logisticProvider: MERCHANT`). Formato com entregador iFood não capturado ainda |
| `GET /v1/customers/me/orders/{id}/fallback` | detalhe alternativo |
| `GET /v1/customers/me/orders/{id}/reorder?lat=&lon=` | carrinho para repetir |
| `POST /v1/customers/me/orders:received {order_id}` | confirmar recebimento (não usado) |
| `GET /v1/customers/me/account` | `id, name, email, phone, registration_date, ...` |
| `GET /v1/customers/me/addresses` | endereços salvos |
| `GET /v1/customers/me/loyalty-cards`, `/chats/summary` | vazios na conta testada |

Logo da loja: `https://static.ifood-static.com.br/image/upload/t_thumbnail/logosgde/<merchant.logo>`.

## Status

`lastStatus`: `CREATED, PLACED, CONFIRMED, READY_FOR_PICKUP, DISPATCHED, CONCLUDED, DECLINED, CANCELLED`
(final = CONCLUDED/DECLINED/CANCELLED, igual ao site).

Timeline real de um pedido com entrega da loja:
`CREATED → PLACED → CONFIRMED → DELIVERY_DROP_CODE_REQUESTED (HANDSHAKE_CODE) → CHAT_MERCHANT_ENABLED →
DELIVERY_REQUEST_CREATED → DISPATCHED → DELIVERY_REQUEST_IN_PROGRESS → RECEIVED_BY_CUSTOMER → CONCLUDED →
DELIVERY_REQUEST_COMPLETED`.

Do bundle (logística iFood, não visto ao vivo): `ASSIGN_DRIVER, GOING_TO_ORIGIN, ARRIVED_AT_ORIGIN, COLLECTED,
GOING_TO_DESTINATION, ARRIVED_AT_DESTINATION, ORDER_PICKUP, DELIVERED`.

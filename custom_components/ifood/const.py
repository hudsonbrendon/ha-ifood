"""Constantes da integração iFood."""

from __future__ import annotations

import logging

DOMAIN = "ifood"
LOGGER = logging.getLogger(__package__)

CONF_REFRESH_TOKEN = "refresh_token"
CONF_ACCESS_TOKEN = "access_token"
CONF_DEVICE_ID = "device_id"

# Sem pedido aberto o histórico muda pouco; com pedido aberto o status muda em minutos.
IDLE_SCAN_INTERVAL_SECONDS = 600
ACTIVE_SCAN_INTERVAL_SECONDS = 30
# O histórico completo (todas as páginas) só é relido a cada hora ou quando um pedido fecha.
HISTORY_REFRESH_SECONDS = 3600

EVENT_ORDER_UPDATED = "ifood_pedido_atualizado"
EVENT_NEW_VOUCHER = "ifood_cupom_novo"
CONF_PAYMENT_SECRET = "payment_secret"

# Cupons, Clube, carteira e detalhes das lojas mudam devagar.
EXTRAS_REFRESH_SECONDS = 3600
# Loja ao vivo (aberta, tempo/taxa de entrega).
MERCHANT_REFRESH_SECONDS = 600
TOP_MERCHANTS = 3

# lastStatus do pedido (bundle do site + respostas reais).
FINAL_STATUSES = {"CONCLUDED", "DECLINED", "CANCELLED"}

STATUS_PT = {
    "CREATED": "Criado",
    "PLACED": "Enviado ao restaurante",
    "CONFIRMED": "Confirmado",
    "IN_PREPARATION": "Em preparo",
    "READY_FOR_PICKUP": "Pronto para retirada",
    "READY_TO_PICKUP": "Pronto para retirada",
    "DISPATCHED": "Saiu para entrega",
    "CONCLUDED": "Concluído",
    "DECLINED": "Recusado",
    "CANCELLED": "Cancelado",
    # Eventos da timeline (/events) e da logística.
    "RECEIVED_BY_CUSTOMER": "Entregue",
    "DELIVERED": "Entregue",
    "ASSIGN_DRIVER": "Entregador designado",
    "GOING_TO_ORIGIN": "Entregador indo ao restaurante",
    "ARRIVED_AT_ORIGIN": "Entregador no restaurante",
    "COLLECTED": "Pedido coletado",
    "GOING_TO_DESTINATION": "A caminho",
    "ARRIVED_AT_DESTINATION": "Entregador chegou",
    "DELIVERY_DROP_CODE_REQUESTED": "Código de entrega gerado",
    "DELIVERY_REQUEST_CREATED": "Entrega solicitada",
    "DELIVERY_REQUEST_IN_PROGRESS": "Entrega em andamento",
    "DELIVERY_REQUEST_COMPLETED": "Entrega finalizada",
    "CHAT_MERCHANT_ENABLED": "Chat com a loja liberado",
}

# Eventos de bastidor que não valem notificação.
SILENT_EVENTS = {
    "CREATED",  # PLACED chega 3 s depois e é o "pedido enviado"
    "CHAT_MERCHANT_ENABLED",
    "DELIVERY_REQUEST_CREATED",
    "DELIVERY_REQUEST_IN_PROGRESS",  # duplica DISPATCHED
    "DELIVERY_REQUEST_COMPLETED",
}

LOGO_URL = "https://static.ifood-static.com.br/image/upload/t_thumbnail/logosgde/{}"

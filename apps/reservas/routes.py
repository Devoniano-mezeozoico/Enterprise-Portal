from flask import Blueprint

# Este setor não define rotas próprias: o sistema de reservas de salas
# já é atendido pela rota principal "/reservas" em app.py. Mantemos o
# blueprint vazio apenas para que o app apareça no Hub de Apps.
bp = Blueprint(
    "reservas_app",
    __name__,
    url_prefix="/apps/reservas",
)

APP_INFO = {
    "nome": "Reserva de Salas",
    "descricao": "Agende salas de reunião da empresa.",
    "icone": "fa-solid fa-calendar-days",
    "url": "/reservas",
    "setor": "Administrativo",
}

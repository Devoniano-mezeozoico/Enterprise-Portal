document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("formReserva");
    if (!form) {
        return;
    }

    form.addEventListener("submit", function (evento) {
        const horaInicio = form.querySelector('input[name="hora_inicio"]').value;
        const horaFim = form.querySelector('input[name="hora_fim"]').value;

        if (horaInicio && horaFim && horaFim <= horaInicio) {
            evento.preventDefault();
            alert("A hora final deve ser depois da hora inicial.");
        }
    });
});

let toggle = document.getElementById("toggle");
let label_toggle = document.getElementById("label_toggle");

// Verifica si el modo oscuro estaba activado previamente
if (localStorage.getItem("darkMode") === "true") {
    document.body.classList.add("dark");
    toggle.checked = true;
    label_toggle.innerHTML = '<i class="fa-solid fa-sun"></i>';
    label_toggle.style.color = '#ffeb3b';
} else {
    label_toggle.innerHTML = '<i class="fa-solid fa-moon"></i>';
    label_toggle.style.color = '#ffffff';
}

// Escucha el cambio del interruptor
toggle.addEventListener("change", (event) => {
    let checked = event.target.checked;
    document.body.classList.toggle("dark");

    // Guarda el estado en localStorage
    localStorage.setItem("darkMode", checked);

    if (checked) {
        label_toggle.innerHTML = '<i class="fa-solid fa-sun"></i>';
        label_toggle.style.color = '#ffeb3b';
    } else {
        label_toggle.innerHTML = '<i class="fa-solid fa-moon"></i>';
        label_toggle.style.color = '#ffffff';
    }
});



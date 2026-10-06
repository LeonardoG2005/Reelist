/*
 * Estrategia del loader explicada :D 
 *  - showDelay:   ms que se espera antes de mostrar el loader. Con 0 se muestra al instante;
 *                 con >0 una carga rapida nunca lo muestra (util para recargas tras una accion).
 *  - minDuration: una vez visible, se queda al menos estos ms (evita el parpadeo).
 *  - Si los datos tardan mas que eso, el loader dura hasta que llegan.
 *
 * Los gifs se toman al azar de styles/assets/loaders (lista inyectada por el servidor).
 */
(function () {
  var DEFAULTS = { text: "Loading...", minDuration: 500, showDelay: 0 };

  var gifs = [];
  try {
    var listEl = document.getElementById("loader-gifs");
    if (listEl) gifs = JSON.parse(listEl.textContent) || [];
  } catch (error) {
    gifs = [];
  }

  // Un gif al azar y ya (puede salir el mismo dos veces seguidas, es parte del azar)
  function pickGif() {
    if (!gifs.length) return null;
    return gifs[Math.floor(Math.random() * gifs.length)];
  }

  function build(text, forcedSrc) {
    var box = document.createElement("div");
    box.className = "loader";
    box.setAttribute("role", "status");
    box.setAttribute("aria-live", "polite");

    var src = forcedSrc !== undefined ? forcedSrc : pickGif();
    if (src) {
      var img = document.createElement("img");
      img.className = "loader-gif";
      img.src = src;
      img.alt = "";
      img.decoding = "async";
      img.addEventListener("error", function () { img.remove(); });
      box.appendChild(img);
    }

    var label = document.createElement("div");
    label.className = "loader-text";
    label.textContent = text;
    box.appendChild(label);
    return box;
  }

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  async function run(container, task, options) {
    var o = Object.assign({}, DEFAULTS, options);
    var node = null;
    var shownAt = 0;
    var timer = null;

    function show() {
      node = build(o.text);
      container.replaceChildren(node);
      container.setAttribute("aria-busy", "true");
      shownAt = performance.now();
    }

    if (o.showDelay > 0) {
      timer = setTimeout(show, o.showDelay);
    } else {
      show();
    }

    try {
      var result = await (typeof task === "function" ? task() : task);
      if (node) {
        var remaining = o.minDuration - (performance.now() - shownAt);
        if (remaining > 0) await sleep(remaining);
      }
      return result;
    } finally {
      clearTimeout(timer);
      if (node) node.remove();
      container.removeAttribute("aria-busy");
    }
  }

  /*
   * Para navegaciones normales (un enlace o un formulario que recarga la pagina):
   * pone el loader en el contenedor si la pagina nueva tarda mas de showDelay ms
   * Y ADEMAS su gif ya termino de descargarse (asi nunca se ve un hueco vacio ni un
   * "Loading..." sin gif; si el gif falla, simplemente no se muestra el loader).
   * No hace falta quitarlo: al llegar la pagina nueva, la actual desaparece.
   * Devuelve restore() por si la navegacion se cancela o se vuelve con "Atras"
   * (el navegador puede restaurar esta pagina tal cual, con el loader puesto).
   */
  function showWhileNavigating(container, options) {
    var o = Object.assign({}, DEFAULTS, { showDelay: 400 }, options);
    var original = Array.prototype.slice.call(container.childNodes);
    var src = pickGif();
    var delayElapsed = false;
    var gifReady = !src; // sin gifs en la carpeta se muestra solo el texto
    var cancelled = false;
    var shown = false;
    var timer = null;
    var failsafe = null;

    function tryShow() {
      if (shown || cancelled || !delayElapsed || !gifReady) return;
      shown = true;
      container.replaceChildren(build(o.text, src));
      container.setAttribute("aria-busy", "true");
    }

    // el gif se empieza a bajar desde el clic, en paralelo a la navegacion
    if (src) {
      var probe = new Image();
      probe.onload = function () { gifReady = true; tryShow(); };
      probe.onerror = function () { cancelled = true; };
      probe.src = src;
    }
    timer = setTimeout(function () { delayElapsed = true; tryShow(); }, o.showDelay);

    function restore() {
      cancelled = true;
      clearTimeout(timer);
      clearTimeout(failsafe);
      container.replaceChildren.apply(container, original);
      container.removeAttribute("aria-busy");
      if (typeof o.onRestore === "function") o.onRestore();
    }

    function onPageShow(event) {
      if (!event.persisted) return;
      window.removeEventListener("pageshow", onPageShow);
      restore();
    }
    window.addEventListener("pageshow", onPageShow);
    failsafe = setTimeout(restore, 20000); // navegacion cancelada (Esc / parar): no dejar el loader pegado
    return restore;
  }

  function showError(container, message, onRetry) {
    var box = document.createElement("div");
    box.className = "loader loader-error";
    box.setAttribute("role", "alert");

    var label = document.createElement("div");
    label.className = "loader-text";
    label.textContent = message;
    box.appendChild(label);

    if (typeof onRetry === "function") {
      var retry = document.createElement("button");
      retry.type = "button";
      retry.textContent = "Try again";
      retry.addEventListener("click", onRetry);
      box.appendChild(retry);
    }
    container.replaceChildren(box);
  }

  window.Loader = { run: run, showWhileNavigating: showWhileNavigating, showError: showError, defaults: DEFAULTS };
})();

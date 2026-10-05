/*
 * Reelist - pantalla de carga reutilizable.
 *
 * Uso:
 *   const html = await Loader.run(contenedor, () => fetch(url).then(r => r.text()));
 *   contenedor.innerHTML = html;
 *
 * Estrategia:
 *  - showDelay:   ms que se espera antes de mostrar el loader. Con 0 se muestra al instante;
 *                 con >0 una carga rapida nunca lo muestra (util para recargas tras una accion).
 *  - minDuration: una vez visible, se queda al menos estos ms (evita el parpadeo).
 *  - Si los datos tardan mas que eso, el loader dura hasta que llegan.
 *
 * Los gifs se toman al azar de styles/assets/loaders (lista inyectada por el servidor).
 */
(function () {
  var DEFAULTS = { text: "Loading...", minDuration: 400, showDelay: 0 };

  var gifs = [];
  try {
    var listEl = document.getElementById("loader-gifs");
    if (listEl) gifs = JSON.parse(listEl.textContent) || [];
  } catch (error) {
    gifs = [];
  }

  var lastGif = null;
  var nextGif = null;

  function pickGif() {
    if (!gifs.length) return null;
    // evita repetir el gif anterior cuando hay mas de uno
    var pool = gifs.length > 1 ? gifs.filter(function (g) { return g !== lastGif; }) : gifs;
    return pool[Math.floor(Math.random() * pool.length)];
  }

  function preload(src) {
    if (!src) return;
    var img = new Image();
    img.src = src;
  }

  function takeGif() {
    var gif = nextGif || pickGif();
    lastGif = gif;
    nextGif = pickGif();
    preload(nextGif); // el siguiente ya queda en cache
    return gif;
  }

  function build(text) {
    var box = document.createElement("div");
    box.className = "loader";
    box.setAttribute("role", "status");
    box.setAttribute("aria-live", "polite");

    var src = takeGif();
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

  window.Loader = { run: run, showError: showError, preload: function () { nextGif = nextGif || pickGif(); preload(nextGif); }, defaults: DEFAULTS };
})();

/* ==========================================================================
   MERCADO MORCELLE - JavaScript do frontend
   Puro (sem frameworks). Melhora a experiência, mas o backend funciona sem JS.
   ========================================================================== */

document.addEventListener("DOMContentLoaded", function () {
  initMenuMobile();
  initSidebarMobile();
  initTogglePassword();
  initImagePreview();
  initConfirmModal();
  initFlashAutoClose();
  initCategoryFilterSubmit();
});

/* ---------------------------------------------------------------------- */
/* Menu mobile (site público)                                             */
/* ---------------------------------------------------------------------- */
function initMenuMobile() {
  var toggle = document.getElementById("menuToggle");
  var headerInner = document.getElementById("headerInner");
  if (!toggle || !headerInner) return;

  toggle.addEventListener("click", function () {
    headerInner.classList.toggle("menu-open");
  });
}

/* ---------------------------------------------------------------------- */
/* Sidebar mobile (painel admin)                                          */
/* ---------------------------------------------------------------------- */
function initSidebarMobile() {
  var toggle = document.getElementById("sidebarToggle");
  var sidebar = document.getElementById("adminSidebar");
  if (!toggle || !sidebar) return;

  toggle.addEventListener("click", function () {
    sidebar.classList.toggle("open");
  });

  document.addEventListener("click", function (event) {
    if (
      sidebar.classList.contains("open") &&
      !sidebar.contains(event.target) &&
      event.target !== toggle
    ) {
      sidebar.classList.remove("open");
    }
  });
}

/* ---------------------------------------------------------------------- */
/* Mostrar / ocultar senha                                                */
/* ---------------------------------------------------------------------- */
function initTogglePassword() {
  var buttons = document.querySelectorAll(".toggle-password");
  buttons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var targetId = btn.getAttribute("data-target");
      var input = document.getElementById(targetId);
      if (!input) return;

      if (input.type === "password") {
        input.type = "text";
        btn.textContent = "OCULTAR";
      } else {
        input.type = "password";
        btn.textContent = "MOSTRAR";
      }
    });
  });
}

/* ---------------------------------------------------------------------- */
/* Prévia de imagens ao selecionar arquivos                               */
/* ---------------------------------------------------------------------- */
function initImagePreview() {
  var input = document.getElementById("imagensInput");
  var previewGrid = document.getElementById("previewGrid");
  var fileLabel = document.getElementById("fileUploadLabel");
  if (!input || !previewGrid) return;

  input.addEventListener("change", function () {
    previewGrid.innerHTML = "";
    var files = Array.from(input.files || []);

    if (files.length === 0) {
      return;
    }

    if (fileLabel) {
      fileLabel.textContent =
        files.length === 1
          ? "1 imagem selecionada"
          : files.length + " imagens selecionadas";
    }

    files.forEach(function (file) {
      if (!file.type.startsWith("image/")) return;

      var reader = new FileReader();
      reader.onload = function (e) {
        var item = document.createElement("div");
        item.className = "preview-item";

        var img = document.createElement("img");
        img.src = e.target.result;
        img.alt = file.name;

        item.appendChild(img);
        previewGrid.appendChild(item);
      };
      reader.readAsDataURL(file);
    });
  });
}

/* ---------------------------------------------------------------------- */
/* Modal de confirmação de exclusão                                       */
/* ---------------------------------------------------------------------- */
function initConfirmModal() {
  var modal = document.getElementById("confirmModal");
  if (!modal) return;

  var formToSubmit = null;
  var messageEl = document.getElementById("confirmModalMessage");
  var confirmBtn = document.getElementById("confirmModalConfirmBtn");
  var cancelBtn = document.getElementById("confirmModalCancelBtn");

  document.querySelectorAll("[data-confirm-form]").forEach(function (trigger) {
    trigger.addEventListener("click", function (event) {
      event.preventDefault();
      var formId = trigger.getAttribute("data-confirm-form");
      var message = trigger.getAttribute("data-confirm-message");
      formToSubmit = document.getElementById(formId);

      if (messageEl && message) {
        messageEl.textContent = message;
      }

      modal.classList.add("open");
    });
  });

  if (confirmBtn) {
    confirmBtn.addEventListener("click", function () {
      if (formToSubmit) {
        formToSubmit.submit();
      }
      modal.classList.remove("open");
    });
  }

  if (cancelBtn) {
    cancelBtn.addEventListener("click", function () {
      modal.classList.remove("open");
      formToSubmit = null;
    });
  }

  modal.addEventListener("click", function (event) {
    if (event.target === modal) {
      modal.classList.remove("open");
      formToSubmit = null;
    }
  });
}

/* ---------------------------------------------------------------------- */
/* Fechar mensagens flash automaticamente / manualmente                   */
/* ---------------------------------------------------------------------- */
function initFlashAutoClose() {
  var alerts = document.querySelectorAll(".alert");
  alerts.forEach(function (alert) {
    var closeBtn = alert.querySelector(".alert-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", function () {
        alert.style.display = "none";
      });
    }

    setTimeout(function () {
      alert.style.transition = "opacity 0.4s ease";
      alert.style.opacity = "0";
      setTimeout(function () {
        alert.style.display = "none";
      }, 400);
    }, 6000);
  });
}

/* ---------------------------------------------------------------------- */
/* Filtro de categoria: envia o formulário de busca ao trocar categoria    */
/* ---------------------------------------------------------------------- */
function initCategoryFilterSubmit() {
  var select = document.getElementById("categoriaSelect");
  if (!select) return;

  select.addEventListener("change", function () {
    select.form.submit();
  });
}

/* ---------------------------------------------------------------------- */
/* Registro do Service Worker (PWA)                                       */
/* ---------------------------------------------------------------------- */
if ("serviceWorker" in navigator) {
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/service-worker.js").catch(function () {
      /* Falha silenciosa: PWA é um recurso opcional */
    });
  });
}

/* Mercado Morcelle - Service Worker
   Cache simples para permitir "Adicionar à tela inicial" e uso offline básico
   dos recursos estáticos. As páginas dinâmicas (produtos, admin) sempre
   buscam dados atualizados na rede. */

const CACHE_NAME = "morcelle-cache-v1";
const ARQUIVOS_ESTATICOS = [
  "/static/css/style.css",
  "/static/js/script.js",
  "/static/images/logo.png",
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(ARQUIVOS_ESTATICOS);
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (nomes) {
      return Promise.all(
        nomes
          .filter(function (nome) {
            return nome !== CACHE_NAME;
          })
          .map(function (nome) {
            return caches.delete(nome);
          })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", function (event) {
  const url = new URL(event.request.url);

  // Somente cacheia arquivos estáticos (CSS, JS, imagens). Páginas HTML
  // sempre vão para a rede para garantir dados atualizados.
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(event.request).then(function (respostaCache) {
        return (
          respostaCache ||
          fetch(event.request).then(function (respostaRede) {
            return caches.open(CACHE_NAME).then(function (cache) {
              cache.put(event.request, respostaRede.clone());
              return respostaRede;
            });
          })
        );
      })
    );
  }
});

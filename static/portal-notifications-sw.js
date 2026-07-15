self.addEventListener('notificationclick', event => {
  event.notification.close();
  const destino = (event.notification.data && event.notification.data.url) || '/comunicados';

  event.waitUntil((async () => {
    const todasJanelas = await clients.matchAll({type: 'window', includeUncontrolled: true});
    for (const janela of todasJanelas) {
      try {
        const url = new URL(janela.url);
        if (url.origin === self.location.origin) {
          await janela.focus();
          return janela.navigate(destino);
        }
      } catch (_) {}
    }
    return clients.openWindow(destino);
  })());
});

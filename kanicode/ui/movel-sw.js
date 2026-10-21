// KaniCode no celular: recebe o aviso do PC (aviso_movel.py) e mostra a notificação; tocar nela abre o KaniCode.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

self.addEventListener('push', e => {
  let d = {};
  try { d = e.data.json(); } catch (x) { d = { titulo: 'KaniCode', corpo: e.data ? e.data.text() : '' }; }
  e.waitUntil(self.registration.showNotification(d.titulo || 'KaniCode', {
    body: d.corpo || '', tag: d.tag || 'kc', renotify: true, icon: '/icone-192.png', badge: '/icone-badge.png',
    vibrate: [80, 60, 80], data: { url: '/' },
  }));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(lista => {
    for (const c of lista) if ('focus' in c) return c.focus();
    return self.clients.openWindow('/');
  }));
});

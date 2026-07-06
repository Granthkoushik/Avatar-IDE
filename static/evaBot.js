// AVATAR Bot Module - Clean Proxy to Active Virtual Pet
(() => {
  window.avatarBot = {
    init: () => {},
    setState: (newState, duration) => {
      if (typeof window.setVirtualPetState === 'function') {
        window.setVirtualPetState(newState, duration);
      }
    },
    speak: (message, type) => {
      if (typeof window.showVirtualPetBubble === 'function') {
        window.showVirtualPetBubble(message, type);
      }
    },
    processRequest: (req) => {
      if (typeof sendChat === 'function') {
        sendChat(req);
      } else {
        console.warn('sendChat not available');
      }
    },
    showBubble: (msg, timeout) => {
      if (typeof window.showVirtualPetBubble === 'function') {
        window.showVirtualPetBubble(msg, 'info', timeout);
      }
    },
    spawnParticles: (icon, count) => {
      if (typeof window.spawnVirtualPetParticles === 'function') {
        window.spawnVirtualPetParticles(icon, count);
      }
    }
  };
  window.evaBot = window.avatarBot; // Alias for backward compatibility
})();

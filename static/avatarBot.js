// Avatar Bot Module - Premium Intelligent Workspace Companion
// This script encapsulates the avatar behavior, state machine, persistence, and interactions.

(() => {
  const container = document.getElementById('virtualPetContainer');
  const pet = document.getElementById('virtualPet');
  const bubble = document.getElementById('petBubble');

  // LocalStorage keys
  const LS_POS_X = 'avatar_pos_x';
  const LS_POS_Y = 'avatar_pos_y';
  const LS_STATE = 'avatar_state';
  const LS_AFFECTION = 'avatar_affection';

  // Default values
  let posX = parseInt(localStorage.getItem(LS_POS_X), 10) || 20;
  let posY = parseInt(localStorage.getItem(LS_POS_Y), 10) || 20;
  let state = localStorage.getItem(LS_STATE) || 'idle';
  let affection = parseInt(localStorage.getItem(LS_AFFECTION), 10) || 0;

  // Apply initial position
  const applyPosition = () => {
    container.style.left = posX + 'px';
    container.style.top = posY + 'px';
  };
  applyPosition();

  // State handling – map states to CSS classes
  const STATE_CLASSES = {
    idle: [],
    happy: ['happy'],
    blush: ['blush'],
    thinking: ['thinking'],
    sleeping: ['sleeping'],
    excited: ['excited'],
    shocked: ['shocked'],
    confused: ['confused'],
    dragged: ['dragged']
  };

  const setState = (newState, duration = 0) => {
    if (state === newState) return;
    // Remove old state classes
    Object.values(STATE_CLASSES).flat().forEach(cls => pet.classList.remove(cls));
    // Add new state classes
    STATE_CLASSES[newState].forEach(cls => pet.classList.add(cls));
    state = newState;
    localStorage.setItem(LS_STATE, state);
    if (duration > 0) {
      clearTimeout(window._avatarStateTimer);
      window._avatarStateTimer = setTimeout(() => {
        setState('idle');
      }, duration);
    }
  };

  // Speech bubble utility
  const showBubble = (msg, timeout = 5000) => {
    bubble.innerHTML = `<div class="bubble-text">${msg}</div>`;
    bubble.style.display = 'block';
    clearTimeout(window._avatarBubbleTimer);
    window._avatarBubbleTimer = setTimeout(() => {
      bubble.style.display = 'none';
    }, timeout);
  };

  // Public speak method – replaces legacy window.avatarSpeak
  const speak = (msg, type = 'info') => {
    showBubble(msg);
    switch (type) {
      case 'success':
        setState('excited', 2500);
        spawnParticles('🎉', 5);
        affection += 2;
        break;
      case 'error':
        setState('shocked', 3000);
        spawnParticles('⚠️', 3);
        break;
      case 'thinking':
        setState('thinking', 4000);
        break;
      default:
        // info – keep idle
        break;
    }
    // Persist affection
    localStorage.setItem(LS_AFFECTION, affection);
  };

  // Simple particle effect using CSS pseudo‑elements
  const spawnParticles = (icon, count) => {
    for (let i = 0; i < count; i++) {
      const el = document.createElement('div');
      el.className = 'avatar-particle';
      el.textContent = icon;
      el.style.left = `${Math.random() * 40 - 20}px`;
      el.style.top = `${Math.random() * 40 - 20}px`;
      container.appendChild(el);
      // Remove after animation
      setTimeout(() => el.remove(), 1500);
    }
  };

  // Drag handling – pointer events for modern browsers
  let dragging = false;
  let dragOffsetX = 0;
  let dragOffsetY = 0;

  const onPointerDown = (e) => {
    dragging = true;
    dragOffsetX = e.clientX - container.offsetLeft;
    dragOffsetY = e.clientY - container.offsetTop;
    pet.classList.add('dragged');
  };

  const onPointerMove = (e) => {
    if (!dragging) return;
    posX = e.clientX - dragOffsetX;
    posY = e.clientY - dragOffsetY;
    applyPosition();
  };

  const onPointerUp = () => {
    if (!dragging) return;
    dragging = false;
    pet.classList.remove('dragged');
    // Persist position
    localStorage.setItem(LS_POS_X, posX);
    localStorage.setItem(LS_POS_Y, posY);
  };

  // Attach listeners to the container (excluding bubble clicks)
  container.addEventListener('pointerdown', onPointerDown);
  window.addEventListener('pointermove', onPointerMove);
  window.addEventListener('pointerup', onPointerUp);

  // Expose globally for legacy calls
  window.avatarBot = {
    init: () => {}, // placeholder for future init steps
    setState,
    speak,
    showBubble,
    spawnParticles
  };
})();

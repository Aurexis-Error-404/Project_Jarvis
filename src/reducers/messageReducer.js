function _uid() {
  return typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

export default function messageReducer(state, action) {
  switch (action.type) {
    case 'ADD_USER_MESSAGE':
      return [...state, { id: _uid(), role: 'user', text: action.text, timestamp: new Date() }];
    case 'ADD_JARVIS_MESSAGE':
      return [...state, { id: _uid(), role: 'jarvis', text: action.text, timestamp: new Date() }];
    case 'START_STREAM':
      return [...state, { id: action.id || _uid(), role: 'jarvis', text: '', timestamp: new Date(), streaming: true }];
    case 'APPEND_CHUNK':
      return state.map((msg, i) => i === state.length - 1 && msg.streaming ? { ...msg, text: msg.text + action.text } : msg);
    case 'FINISH_STREAM':
      return state.map((msg, i) => i === state.length - 1 && msg.streaming ? { ...msg, streaming: false } : msg);
    case 'REPLACE_RESPONSE':
      return state.map((msg, i) => i === state.length - 1 && msg.role === 'jarvis' ? { ...msg, text: action.text, streaming: false } : msg);
    case 'ADD_ERROR':
      return [...state, { id: _uid(), role: 'error', text: action.message, timestamp: new Date() }];
    case 'CLEAR':
      return [];
    default:
      return state;
  }
}
